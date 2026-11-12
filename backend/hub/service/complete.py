"""Hub chat completion 主流程與首 token 競速（自 backend.hub.service 抽出）。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from backend.hub.budget_guard import (
    actual_cost_usd,
    estimate_cost_usd,
    estimate_tokens,
)
from backend.hub.cache import semantic_key, should_bypass_cache
from backend.hub.catalog import (
    ALLOWED_STRATEGIES,
    HUB_CATALOG,
    provider_of,
    runtime_hub_whitelist,
    validate_model_id,
)
from backend.hub.errors import (
    MSG_ALL_DOWN,
    MSG_BUDGET,
    MSG_EGRESS,
    MSG_FAILOVER_OK,
    MSG_FILTER,
    MSG_TIMEOUT,
    MSG_UNSUPPORTED,
    HubError,
)
from backend.hub.router import (
    CONNECT_TIMEOUT_S,
    HubUpstreamError,
    Metrics,
    default_metrics,
    invoke_with_failover,
    pick_primary,
    race_sync,
    race_to_the_top,
)
from backend.hub.runtime import runtime
from backend.hub.safety import (
    contains_sensitive,
    content_is_multimodal,
    flatten_messages_text,
)
from backend.hub.store import (
    HubUser,
    new_chat_id,
    new_trace_id,
)

from .failover import _validate_messages, parse_failover_config
from .probe import _llm_probe, _record_circuit


def complete_chat(
    user: HubUser,
    body: dict[str, Any],
    *,
    strategy: str,
    region: str,
    failover_raw: str | None,
    request_id: str,
    sleeper: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    if strategy not in ALLOWED_STRATEGIES:
        raise HubError(400, "BAD_REQUEST", "x-routing-strategy 枚舉不合法")

    messages = _validate_messages(body.get("messages"))
    temperature = float(body.get("temperature", 0.7))
    if not 0.0 <= temperature <= 2.0:
        raise HubError(400, "BAD_REQUEST", "temperature 須在 0–2")
    max_tokens = int(body.get("max_tokens") or 2048)
    if not 1 <= max_tokens <= 32768:
        raise HubError(400, "BAD_REQUEST", "max_tokens 超出範圍")
    stream = bool(body.get("stream", False))
    session_id = ""
    meta = body.get("metadata") or {}
    if isinstance(meta, dict):
        session_id = str(meta.get("session_id") or "")
    session_id = session_id or str(body.get("user") or "")

    raw_model = body.get("model")
    if raw_model is not None and not isinstance(raw_model, str):
        raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED)
    try:
        model = validate_model_id(raw_model)
    except ValueError as exc:
        raise HubError(400, "UNSUPPORTED_MODEL", MSG_UNSUPPORTED) from exc

    failover = parse_failover_config(failover_raw)
    whitelist = failover.get("model_whitelist") or runtime_hub_whitelist()
    if model and whitelist and model not in whitelist:
        model = whitelist[0]
    multimodal = content_is_multimodal(messages)
    if multimodal and region.upper() == "CN":
        raise HubError(400, "MODALITY_NOT_ALLOWED_IN_REGION", MSG_EGRESS)

    metrics = {
        m: Metrics(
            latency_ms=float(row.get("latency_ewma_ms") or default_metrics(m).latency_ms),
            price_out_per_1m=float(row.get("price_out_per_1m") or default_metrics(m).price_out_per_1m),
        )
        for m, row in runtime.store.provider_metrics.items()
        if m in HUB_CATALOG
    }

    try:
        decision = pick_primary(
            strategy=strategy,
            region=region,
            whitelist=whitelist,
            metrics_by_model=metrics,
            manual_model=model,
            circuit_open=runtime.circuits.is_open,
        )
    except PermissionError as exc:
        raise HubError(403, "DATA_EGRESS_FORBIDDEN", MSG_EGRESS) from exc
    except ValueError as exc:
        raise HubError(400, "BAD_REQUEST", "manual 策略必須提供 model") from exc

    if multimodal and decision.model != "gemini-3.1-pro":
        if region.upper() == "CN":
            raise HubError(400, "MODALITY_NOT_ALLOWED_IN_REGION", MSG_EGRESS)
        decision.model = "gemini-3.1-pro"
        decision.provider = provider_of("gemini-3.1-pro")
        decision.reason = "multimodal"

    prompt_text = flatten_messages_text(messages)
    input_tokens = estimate_tokens(prompt_text)
    estimate = estimate_cost_usd(decision.model, input_tokens, max_tokens)
    if runtime.budget.would_exceed(str(user.id), estimate, user.daily_budget_limit_usd):
        runtime.store.append_log(
            {
                "id": new_chat_id(),
                "user_id": str(user.id),
                "provider": "none",
                "model_name": decision.model,
                "status": "budget_denied",
                "cost_usd": 0.0,
                "error_code": "BUDGET_EXCEEDED",
            }
        )
        raise HubError(403, "BUDGET_EXCEEDED", MSG_BUDGET)

    bypass = should_bypass_cache(temperature, stream, multimodal)
    cache_status = "BYPASS"
    chat_id = new_chat_id()
    trace_id = request_id.replace("-", "")[:32].ljust(32, "0") if request_id else new_trace_id()
    t0 = time.monotonic()
    hops = 0
    text = ""
    used_model = decision.model
    notice = ""

    if not bypass:
        key = semantic_key(str(user.id), strategy, messages)
        cached = runtime.cache.get(key)
        if cached:
            cache_status = "HIT"
            cached = dict(cached)
            cached["id"] = chat_id
            cached["cost_usd"] = 0.0
            cached["cache"] = "HIT"
            cached["chosen_provider"] = "cache"
            runtime.store.append_log(
                {
                    "id": chat_id,
                    "user_id": str(user.id),
                    "session_id": session_id,
                    "provider": "cache",
                    "model_name": "semantic-cache",
                    "status": "success",
                    "cost_usd": 0.0,
                    "latency_ms": int((time.monotonic() - t0) * 1000),
                    "trace_id": trace_id,
                }
            )
            return cached
        cache_status = "MISS"

    connect_s = float(failover.get("connect_timeout_ms", 25000)) / 1000.0
    read_s = float(failover.get("read_timeout_ms", 120000)) / 1000.0
    connect_s = min(max(connect_s, 1.0), CONNECT_TIMEOUT_S * 3)
    read_s = min(max(read_s, 1.0), 180.0)

    enable_race = bool(failover.get("enable_race")) or strategy == "speed_first"
    raced = False
    if enable_race and region.upper() != "CN" and not multimodal:
        try:
            used_model, text = race_sync(_llm_probe, messages)
            raced = True
        except TimeoutError:
            raced = False
            text = ""

    if not text:
        try:
            text, used_model, hops = invoke_with_failover(
                _llm_probe,
                messages,
                decision.model,
                region,
                whitelist,
                connect_s=connect_s,
                read_s=read_s,
                sleeper=sleeper or (lambda _s: None),
                circuit_open=runtime.circuits.is_open,
                on_result=_record_circuit,
            )
        except TimeoutError as exc:
            raise HubError(504, "UPSTREAM_TIMEOUT", MSG_TIMEOUT) from exc
        except HubUpstreamError as exc:
            raise HubError(503, "ALL_PROVIDERS_UNAVAILABLE", MSG_ALL_DOWN) from exc

    latency_ms = int((time.monotonic() - t0) * 1000)
    if contains_sensitive(text):
        runtime.store.append_log(
            {
                "id": chat_id,
                "user_id": str(user.id),
                "session_id": session_id,
                "provider": provider_of(used_model) if used_model in HUB_CATALOG else "unknown",
                "model_name": used_model,
                "status": "filtered",
                "cost_usd": 0.0,
                "error_code": "CONTENT_FILTER",
                "trace_id": trace_id,
            }
        )
        raise HubError(400, "CONTENT_FILTER", MSG_FILTER)

    out_tokens = estimate_tokens(text)
    cost = actual_cost_usd(used_model, input_tokens, out_tokens)
    runtime.budget.add(str(user.id), cost)
    if hops > 0:
        notice = MSG_FAILOVER_OK

    payload = {
        "id": chat_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": used_model,
        "chosen_provider": provider_of(used_model),
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
        "routing_strategy": strategy,
        "failover_hops": hops,
        "cache": cache_status,
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": text},
            }
        ],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": out_tokens,
            "total_tokens": input_tokens + out_tokens,
        },
    }
    if notice:
        payload["notice"] = notice
    if raced:
        payload["race"] = True

    if not bypass:
        runtime.cache.set(semantic_key(str(user.id), strategy, messages), payload)

    runtime.store.append_log(
        {
            "id": chat_id,
            "user_id": str(user.id),
            "session_id": session_id,
            "provider": payload["chosen_provider"],
            "model_name": used_model,
            "prompt_tokens": input_tokens,
            "completion_tokens": out_tokens,
            "cost_usd": cost,
            "status": "success",
            "latency_ms": latency_ms,
            "trace_id": trace_id,
        }
    )
    return payload


async def race_first_token(stream_factory) -> tuple[str, bytes]:
    return await race_to_the_top(stream_factory)
