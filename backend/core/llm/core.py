"""LLM 呼叫層（自 backend.core.llm 抽出）。

call_llm 公開入口、核心派送（hop／pool failover）與單路由呼叫（快取／計費）。
"""

from __future__ import annotations

import logging
import time

from ._compat import (
    _build_call_hops,
    _completion_once,
    _ensure_provider_prefix,
    _llm_params,
    _resolve_call_target,
    _truncate_prompt,
    clamp_model,
    failover_models,
    get_llm_cache,
    invoke_with_pool_failover,
    pool_failover_enabled,
)
from ._compat import (
    _call_llm_on_route as _pkg_call_llm_on_route,
)

logger = logging.getLogger(__name__)


def call_llm(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    role_failover_models: list[str] | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """呼叫 LLM 並回傳回應文字（統一軌跡鉤子點）。

    若處於任務上下文（llm_trace.trace_task_id 已綁定），自動記錄本調用的
    prompt/system/response/耗時 進任務軌跡，供角色 I/O 全監使用；
    trace_label 可附加語義標籤（如 execute/review/grill）。
    """
    from backend.core import llm_trace

    started = time.monotonic()
    try:
        result = _call_llm_core(
            prompt,
            system=system,
            model=model,
            max_retries=max_retries,
            route_id=route_id,
            max_context_tokens=max_context_tokens,
            role_failover_models=role_failover_models,
            trace_label=trace_label,
            **kwargs,
        )
    except Exception as exc:
        if llm_trace.current_context()["task_id"]:
            llm_trace.emit({
                "label": trace_label,
                "prompt": prompt,
                "system": system,
                "model": model,
                "response": "",
                "error": str(exc),
                "duration_ms": round((time.monotonic() - started) * 1000, 1),
            })
        raise
    if llm_trace.current_context()["task_id"]:
        llm_trace.emit({
            "label": trace_label,
            "prompt": prompt,
            "system": system,
            "model": model,
            "response": result,
            "duration_ms": round((time.monotonic() - started) * 1000, 1),
        })
    return result


def _call_llm_core(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
    *,
    route_id: str | None = None,
    max_context_tokens: int | None = None,
    role_failover_models: list[str] | None = None,
    trace_label: str = "",
    **kwargs,
) -> str:
    """呼叫 LLM 並回傳回應文字。

    內建指數退避重試，處理速率限制（RateLimitError）
    與暫時性 API 錯誤。

    max_retries 預設 3（與 MAX_RETRIES 相同），以保持反思閉環行為；
    Hub 路由器切模型前應傳 max_retries=1，避免 3×3 放大延遲。
    啟用 EVOL_LLM_POOL_FAILOVER 時，主模型逾時或限流會自動切換池內備援。
    多 API 路由時依 route_id / 模型歸屬選擇憑證；max_tokens / temperature
    可經 kwargs 傳入（角色 Token 限制）。主路由失敗且有備援路由時會跨 API 切換。
    """
    # ModelGW 可降級掛載（MODELGW_WIRE_MODE=off|shadow|enforce，預設 off）
    entry = kwargs.pop("modelgw_entry", None)
    try:
        from backend.modelgw.runtime import precheck_model

        gate_model = model
        if not gate_model:
            gate_model = _llm_params().get("model")
        precheck_model(gate_model, entry=entry)
    except ImportError:
        pass

    extras = role_failover_models or kwargs.pop("role_failover_models", None) or []
    extras = [str(item).strip() for item in extras if str(item).strip()]
    hops = _build_call_hops(route_id, model, extras)

    if len(hops) <= 1:
        hop_route, hop_model = hops[0] if hops else (route_id, model)
        return _pkg_call_llm_on_route(
            prompt,
            system=system,
            model=hop_model,
            max_retries=max_retries,
            route_id=hop_route,
            max_context_tokens=max_context_tokens,
            trace_label=trace_label,
            **kwargs,
        )

    last_error: Exception | None = None
    for hop, (hop_route_id, hop_model) in enumerate(hops):
        hop_retries = max_retries if hop == 0 else 1
        try:
            return _pkg_call_llm_on_route(
                prompt,
                system=system,
                model=hop_model,
                max_retries=hop_retries,
                route_id=hop_route_id,
                max_context_tokens=max_context_tokens,
                trace_label=trace_label,
                **kwargs,
            )
        except Exception as exc:
            last_error = exc
            if hop + 1 < len(hops):
                nxt = hops[hop + 1][0]
                logger.warning("API 路由 %s 失敗，切換備援 %s：%s", hop_route_id, nxt, exc)
                continue
            raise
    if last_error:
        raise last_error
    return _pkg_call_llm_on_route(
        prompt,
        system=system,
        model=model,
        max_retries=max_retries,
        route_id=route_id,
        max_context_tokens=max_context_tokens,
        trace_label=trace_label,
        **kwargs,
    )


def _call_llm_on_route(
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
    kwargs.pop("role_failover_models", None)
    tracked = ""
    try:
        target = _resolve_call_target(model, route_id)
        clamp_cfg = target.get("cfg")
        resolved_model = clamp_model(model or target.get("model"), cfg=clamp_cfg, route_id=route_id)
        params = _llm_params(target)
        tracked = str(route_id or target.get("route_id") or "")
    except Exception:
        params = _llm_params()
        clamp_cfg = None
        resolved_model = clamp_model(model or params.get("model"))
        target = None
        tracked = str(route_id or "")
    if params.get("api_base"):
        resolved_model = _ensure_provider_prefix(resolved_model)

    try:
        from backend.core.api_router import mark_route_end, mark_route_start

        mark_route_start(tracked)
    except Exception:
        mark_route_end = None  # type: ignore[assignment]

    try:
        prompt = _truncate_prompt(prompt, max_context_tokens)

        cache = get_llm_cache()
        cached = cache.get(prompt, system, resolved_model)
        if cached is not None:
            return cached

        call_kw = dict(kwargs)
        call_kw["route_id"] = route_id or (target or {}).get("route_id")
        call_kw["max_context_tokens"] = max_context_tokens

        if pool_failover_enabled():
            chain = failover_models(resolved_model, cfg=clamp_cfg)
            if len(chain) > 1:
                text, used_model, hops = invoke_with_pool_failover(
                    _completion_once,
                    prompt=prompt,
                    system=system,
                    models=chain,
                    max_retries=max_retries,
                    trace_label=trace_label,
                    **call_kw,
                )
                if hops > 0:
                    logger.info(
                        "模型池 Failover：%s → %s（跳過 %d 個）",
                        resolved_model,
                        used_model,
                        hops,
                    )
                cache.put(prompt, system, used_model, text)
                return text

        result = _completion_once(
            prompt=prompt,
            system=system,
            model=resolved_model,
            max_retries=max_retries,
            trace_label=trace_label,
            **call_kw,
        )
        cache.put(prompt, system, resolved_model, result)
        return result
    finally:
        if mark_route_end is not None:
            try:
                mark_route_end(tracked)
            except Exception:
                pass
