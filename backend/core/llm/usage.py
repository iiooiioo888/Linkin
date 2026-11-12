"""LLM 呼叫層（自 backend.core.llm 抽出）。

LiteLLM 回應的 token 用量擷取與錢包計費。
"""

from __future__ import annotations


def _usage_tokens(response: object, *, prompt: str, system: str | None, output_text: str) -> tuple[int, int, int, int]:
    """從 LiteLLM 回應擷取 token 用量；缺省時以字元粗估。返回 input, output, cached, cache_write。"""
    usage = getattr(response, "usage", None)
    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    cached_tokens = int(
        getattr(usage, "prompt_tokens_details", {}).get("cached_tokens", 0)
        if hasattr(getattr(usage, "prompt_tokens_details", None), "get")
        else getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    )
    cache_write_tokens = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
    if prompt_tokens <= 0:
        prompt_tokens = max(1, len(prompt) // 4 + len(system or "") // 4)
    if completion_tokens <= 0:
        completion_tokens = max(1, len(output_text) // 4)
    return prompt_tokens, completion_tokens, cached_tokens, cache_write_tokens


def _wallet_bill_llm(
    model: str,
    *,
    prompt: str,
    system: str | None,
    max_tokens: int | None,
    input_tokens: int,
    output_tokens: int,
    trace_label: str,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> None:
    from backend.billing.errors import FeatureNotEntitledError, InsufficientCreditsError
    from backend.billing.metering import meter_llm, precheck_llm

    try:
        if max_tokens and input_tokens <= 0:
            precheck_llm(model, max(1, len(prompt) // 4), int(max_tokens), cached_tokens=cached_tokens, cache_write_tokens=cache_write_tokens)
        else:
            precheck_llm(model, input_tokens, output_tokens, cached_tokens=cached_tokens, cache_write_tokens=cache_write_tokens)
        meter_llm(
            model,
            input_tokens,
            output_tokens,
            reference=trace_label or "call_llm",
            meta={"trace_label": trace_label or ""},
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
    except (InsufficientCreditsError, FeatureNotEntitledError) as exc:
        raise RuntimeError(exc.message) from exc
