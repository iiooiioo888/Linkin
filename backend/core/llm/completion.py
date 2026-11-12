"""LLM 呼叫層（自 backend.core.llm 抽出）。

單一模型呼叫（retry／計費）與 (route, model) 嘗試序列建構。
"""

from __future__ import annotations

import logging
import time

from litellm.exceptions import APIError, RateLimitError

from ._compat import (
    _ensure_provider_prefix,
    _llm_params,
    _message_visible_text,
    _openrouter_extra,
    _resolve_call_target,
    _truncate_prompt,
    _usage_tokens,
    _wallet_bill_llm,
    clamp_model,
    completion,
)
from .params import MAX_RETRIES, RETRY_BACKOFF_SECONDS

logger = logging.getLogger(__name__)


def _completion_once(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """單一模型 LLM 呼叫（含重試，不含池級 Failover）。"""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": _truncate_prompt(prompt, max_context_tokens)})

    try:
        target = _resolve_call_target(model, route_id)
    except Exception:
        target = None
    params = _llm_params(target)
    if model:
        params["model"] = model
    clamp_cfg = (target or {}).get("cfg")
    params["model"] = clamp_model(params.get("model"), cfg=clamp_cfg, route_id=route_id)
    if params.get("api_base"):
        params["model"] = _ensure_provider_prefix(params["model"])
    extra = _openrouter_extra(target or {})
    resolved_model = str(params.get("model") or model or "gpt-4o")

    retries = MAX_RETRIES if max_retries is None else max(1, int(max_retries))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = completion(
                model=params["model"],
                messages=messages,
                **{k: v for k, v in params.items() if k != "model"},
                **extra,
                **kwargs,
            )
            text = _message_visible_text(response.choices[0].message)
            in_tok, out_tok, cached_tok, cwrite_tok = _usage_tokens(
                response,
                prompt=prompt,
                system=system,
                output_text=text,
            )
            _wallet_bill_llm(
                resolved_model,
                prompt=prompt,
                system=system,
                max_tokens=kwargs.get("max_tokens"),
                input_tokens=in_tok,
                output_tokens=out_tok,
                trace_label=trace_label,
                cached_tokens=cached_tok,
                cache_write_tokens=cwrite_tok,
            )
            return text
        except RateLimitError as exc:
            last_error = exc
            wait = RETRY_BACKOFF_SECONDS * attempt
            logger.warning(
                "LLM 速率限制，%.1f 秒後重試（%d/%d）", wait, attempt, retries
            )
            time.sleep(wait)
        except APIError as exc:
            last_error = exc
            logger.warning("LLM 呼叫失敗：%s，重試（%d/%d）", exc, attempt, retries)
            time.sleep(RETRY_BACKOFF_SECONDS)
    raise RuntimeError(f"LLM 呼叫於 {retries} 次重試後仍失敗") from last_error


def _build_call_hops(
    route_id: str | None,
    model: str | None,
    extra_models: list[str],
) -> list[tuple[str | None, str | None]]:
    """(route_id, model) 嘗試序列：主路由 → 角色備援模型 → API 備援鏈。"""
    hops: list[tuple[str | None, str | None]] = []
    seen: set[tuple[str, str]] = set()

    def _add(rid: str | None, mid: str | None) -> None:
        key = ((rid or "").strip(), (mid or "").strip())
        if key in seen:
            return
        seen.add(key)
        hops.append((rid, mid))

    try:
        from backend.core.api_router import list_failover_chain

        chain = list_failover_chain(route_id=route_id, model=model, extra_models=extra_models)
    except Exception:
        chain = []
    if not chain:
        _add(route_id, model)
        return hops

    _add(str(chain[0].get("id") or route_id or "") or route_id, model)
    for extra in extra_models:
        try:
            from backend.core.api_router import find_route_for_model

            owned = find_route_for_model(extra)
        except Exception:
            owned = None
        _add((owned or {}).get("id") or None, extra)
    for route in chain[1:]:
        _add(str(route.get("id") or "") or None, str(route.get("model") or model or "") or model)
    return hops or [(route_id, model)]
