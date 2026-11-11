"""模型池查詢與 failover：public_pool、refresh 間隔設定、備援鏈。

health 的函式一律以模組屬性呼叫（health.*），讓 patch 目標可落在
backend.core.provider_pool.health 子模組。
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from . import health
from .catalog import refresh_interval_sec
from .constants import CRAWL_KINDS, KIND_LABELS, logger
from .health import POOL_FAILURE_THRESHOLD, POOL_OPEN_DURATION_S
from .helpers import (
    _bare,
    clamp_model,
    classify_provider,
    pool_failover_enabled,
    pool_failover_slow_s,
    pool_failover_timeout_s,
)


def public_pool(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    kind = str(runtime.get("provider_kind") or classify_provider(
        str(runtime.get("api_base") or ""), str(runtime.get("model") or "")
    ))
    fetched = str(runtime.get("catalog_fetched_at") or "")
    interval = refresh_interval_sec(runtime)
    stale = False
    if fetched:
        try:
            ts = datetime.fromisoformat(fetched)
            age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
            stale = age > interval * 2
        except ValueError:
            stale = True
    else:
        stale = True
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    router_state: dict[str, Any] = {}
    try:
        from backend.core.api_router import public_router_state, union_allowed_models

        router_state = public_router_state(runtime)
        union = router_state.get("allowed_models") or union_allowed_models(runtime)
        if union:
            allowed = union
    except Exception:
        router_state = {}
    route_count = len(router_state.get("api_routes") or [])
    models = runtime.get("catalog_models") or [{"id": m, "name": m, "owned_by": kind} for m in allowed]
    if route_count >= 2:
        merged: list[dict[str, str]] = []
        seen: set[str] = set()
        for route in router_state.get("api_routes") or []:
            label = str(route.get("name") or route.get("id") or "")
            for item in route.get("catalog") or []:
                if isinstance(item, dict):
                    mid = str(item.get("id") or "").strip()
                    row = {
                        "id": mid,
                        "name": str(item.get("name") or mid),
                        "owned_by": str(item.get("owned_by") or route.get("provider") or ""),
                        "route_id": str(route.get("id") or ""),
                        "route_name": label,
                    }
                else:
                    mid = str(item).strip()
                    row = {"id": mid, "name": mid, "owned_by": str(route.get("provider") or ""), "route_id": str(route.get("id") or ""), "route_name": label}
                key = mid.lower()
                if not mid or key in seen:
                    continue
                seen.add(key)
                merged.append(row)
        if merged:
            models = merged
    return {
        "provider_kind": kind,
        "provider_label": KIND_LABELS.get(kind, kind),
        "single_vendor": route_count <= 1 and (
            (kind not in CRAWL_KINDS) or (kind == "openai" and not str(runtime.get("api_base") or ""))
        ),
        "lock_message": _lock_message(kind, allowed, route_count=route_count, router_state=router_state),
        "model": runtime.get("model") or "",
        "api_base": runtime.get("api_base") or "",
        "configured": bool(runtime.get("api_key")),
        "allowed_models": allowed,
        "route_strategy": router_state.get("route_strategy") or "role_preferred",
        "default_route_id": router_state.get("default_route_id") or "",
        "api_routes": router_state.get("api_routes") or [],
        "models_by_provider": router_state.get("models_by_provider") or [],
        "route_strategies": router_state.get("strategies") or [],
        "provider_presets": router_state.get("presets") or [],
        "model_token_hints": router_state.get("model_token_hints") or {},
        "model_rate_cards": router_state.get("model_rate_cards") or {},
        "catalog": models,
        "catalog_source": runtime.get("catalog_source") or "",
        "catalog_url": runtime.get("catalog_url") or "",
        "catalog_fetched_at": fetched,
        "catalog_error": runtime.get("catalog_error") or "",
        "ops": {
            "refresh_interval_sec": interval,
            "last_ok_at": runtime.get("ops_last_ok_at") or "",
            "last_error": runtime.get("ops_last_error") or "",
            "last_latency_ms": int(runtime.get("ops_last_latency_ms") or 0),
            "last_reason": runtime.get("ops_last_reason") or "",
            "consecutive_fail": int(runtime.get("ops_consecutive_fail") or 0),
            "stale": stale,
            "enabled": os.getenv("EVOL_LLM_OPS_ENABLED", "true").lower() not in {"0", "false", "no"},
            "next_check_at": _next_check_at(fetched, interval),
            "pool_failover": {
                "enabled": pool_failover_enabled(),
                "timeout_s": pool_failover_timeout_s(),
                "slow_call_s": pool_failover_slow_s(),
                "fail_threshold": POOL_FAILURE_THRESHOLD,
                "open_duration_s": POOL_OPEN_DURATION_S,
                "models": health.pool_health_snapshot(),
                "active_probe": health.pool_probe_snapshot(),
            },
        },
    }


def _next_check_at(fetched: str, interval: int) -> str:
    if not fetched:
        return ""
    try:
        ts = datetime.fromisoformat(fetched)
        nxt = ts.astimezone(timezone.utc) + timedelta(seconds=interval)
        return nxt.isoformat()
    except ValueError:
        return ""


def _lock_message(
    kind: str,
    allowed: list[str],
    *,
    route_count: int = 0,
    router_state: dict[str, Any] | None = None,
) -> str:
    n = len(allowed)
    routes = list((router_state or {}).get("api_routes") or [])
    enabled = [r for r in routes if r.get("enabled") and r.get("configured")]
    if len(enabled) >= 2:
        names = "、".join(str(r.get("name") or r.get("id")) for r in enabled[:6])
        return f"已配置 {len(enabled)} 組 API（{names}），共 {n} 個可用模型；角色可各自指定供應商與模型"
    if kind == "openrouter":
        return f"OpenRouter 通用目錄：已載入 {n} 個可用模型（已排除 Claude）"
    if kind in CRAWL_KINDS:
        return f"通用端點已鎖定 {n} 個爬取模型；Agent 不得改用其他廠商"
    label = KIND_LABELS.get(kind, kind)
    return f"目前只配置了 {label}，Agent 只能使用該廠商模型（{n}）"


def set_refresh_interval(seconds: int) -> dict[str, Any]:
    from backend.core.llm_config import merge_runtime_config

    snapshot = merge_runtime_config({"ops_refresh_interval_sec": max(60, min(3600, int(seconds)))})
    return public_pool(snapshot)


def _model_cost_score(model: str) -> float:
    try:
        from backend.company.budget import get_model_costs

        costs = get_model_costs()
        bare = _bare(model)
        for key, prices in costs.items():
            if key == model or _bare(key) == bare:
                return float(prices[0]) + float(prices[1])
    except Exception:
        pass
    return 999.0


def failover_models(requested: str | None, cfg: dict[str, Any] | None = None) -> list[str]:
    """依可用池與健康狀態產生 Failover 鏈：首選 → 其餘（成本由低到高）。"""
    from backend.core.llm_config import get_runtime_config

    runtime = cfg or get_runtime_config()
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    if cfg is None:
        try:
            from backend.core.api_router import find_route_for_model, route_as_cfg

            owned = find_route_for_model(requested or str(runtime.get("model") or ""), runtime)
            if owned:
                runtime = route_as_cfg(owned)
                allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
        except Exception:
            pass
    primary = clamp_model(requested or str(runtime.get("model") or ""), cfg=runtime)
    if not allowed:
        return [primary]

    healthy_primary = primary if not health.is_pool_model_open(primary) else None
    others = [m for m in allowed if m != primary and not health.is_pool_model_open(m)]
    others.sort(key=_model_cost_score)
    chain: list[str] = []
    if healthy_primary:
        chain.append(healthy_primary)
    chain.extend(others)
    if not chain:
        return [primary, *others] if primary not in others else allowed
    return chain


def _should_failover(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"TimeoutError", "RateLimitError", "APIError"}:
        return True
    text = str(exc).lower()
    return any(token in text for token in ("429", "503", "timeout", "rate limit", "unavailable"))


def invoke_with_pool_failover(
    call_fn: Any,
    *,
    prompt: str,
    system: str | None = None,
    models: list[str],
    max_retries: int | None = None,
    **kwargs: Any,
) -> tuple[str, str, int]:
    """在模型池內依序嘗試，回傳 (text, used_model, hops)。"""
    import time

    hops = 0
    last_error: Exception | None = None
    per_model_timeout = pool_failover_timeout_s()
    retries = max(1, int(max_retries or 1))

    for model in models:
        if health.is_pool_model_open(model):
            hops += 1
            continue
        t0 = time.monotonic()
        try:
            result = call_fn(
                prompt=prompt,
                system=system,
                model=model,
                max_retries=retries,
                timeout=per_model_timeout,
                **kwargs,
            )
            health.record_pool_call(model, False, time.monotonic() - t0)
            return str(result), model, hops
        except Exception as exc:
            duration = time.monotonic() - t0
            health.record_pool_call(model, True, duration, str(exc))
            last_error = exc
            if _should_failover(exc) or duration >= per_model_timeout:
                hops += 1
                logger.warning(
                    "模型 %s 呼叫失敗（%.1fs），切換備援：%s",
                    model,
                    duration,
                    exc,
                )
                continue
            raise
    raise RuntimeError("模型池全部不可用") from last_error
