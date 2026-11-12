"""LLM 呼叫層（自 backend.core.llm 抽出）。

call_llm_stream 串流入口（retry／billing／thinking 標記）。
"""

from __future__ import annotations

import logging
import time

from litellm.exceptions import APIError, RateLimitError

from ._compat import (
    _delta_reasoning,
    _ensure_provider_prefix,
    _llm_params,
    _openrouter_extra,
    _resolve_call_target,
    _truncate_prompt,
    clamp_model,
    completion,
)
from .params import MAX_RETRIES, RETRY_BACKOFF_SECONDS

logger = logging.getLogger(__name__)


def call_llm_stream(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    trace_label: str = "",
    **kwargs,
):
    """呼叫 LLM 並串流回傳回應片段（生成器）。

    與 call_llm 相同的重試邏輯，但逐塊 yield 文字。
    P4-S1：掛 ModelGW ``precheck_model``（entry=stream；shadow 只觀測）。
    """
    # ModelGW 可降級掛載（對齊 _call_llm_core；ImportError 可降級）
    entry = kwargs.pop("modelgw_entry", None) or "stream"
    try:
        from backend.modelgw.runtime import precheck_model

        gate_model = model
        if not gate_model:
            gate_model = _llm_params().get("model")
        precheck_model(gate_model, entry=entry)
    except ImportError:
        pass

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

    from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
    from backend.billing.metering import meter_llm, precheck_llm

    retries = MAX_RETRIES if max_retries is None else max(1, int(max_retries))
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            try:
                precheck_llm(
                    resolved_model,
                    max(1, len(prompt) // 4 + len(system or "") // 4),
                    int(kwargs.get("max_tokens") or 2048),
                )
            except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
                raise RuntimeError(exc.message) from exc
            response = completion(
                model=params["model"],
                messages=messages,
                stream=True,
                **{k: v for k, v in params.items() if k != "model"},
                **extra,
                **kwargs,
            )
            in_think = False
            collected: list[str] = []
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                reasoning = _delta_reasoning(delta)
                content = getattr(delta, "content", None) if delta else None
                if reasoning:
                    if not in_think:
                        yield "<think>"
                        in_think = True
                    collected.append(reasoning)
                    yield reasoning
                if content:
                    if in_think:
                        yield "</think>"
                        in_think = False
                    collected.append(content)
                    yield content
            if in_think:
                yield "</think>"
            output_text = "".join(collected)
            in_tok = max(1, len(prompt) // 4 + len(system or "") // 4)
            out_tok = max(1, len(output_text) // 4)
            try:
                meter_llm(
                    resolved_model,
                    in_tok,
                    out_tok,
                    reference=trace_label or "stream",
                    meta={"trace_label": trace_label or "stream"},
                )
            except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
                raise RuntimeError(exc.message) from exc
            return
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
