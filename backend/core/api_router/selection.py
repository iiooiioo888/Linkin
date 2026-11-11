"""API 路由的選路、failover 鏈與 inflight 標記（自 backend.core.api_router 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.core.llm_config import get_runtime_config

from .models import get_route_strategy, normalize_strategy
from .routes import (
    find_route_for_model,
    get_default_route,
    list_enabled_routes,
    list_routes,
    resolve_route_ref,
    route_as_cfg,
)
from .state import _inflight, _lock, _wrr_current


def _weighted_round_robin(routes: list[dict[str, Any]]) -> dict[str, Any]:
    with _lock:
        total = 0
        best: dict[str, Any] | None = None
        best_cur = -10**9
        for route in routes:
            rid = str(route["id"])
            weight = max(1, int(route.get("weight") or 1))
            _wrr_current[rid] = _wrr_current.get(rid, 0) + weight
            total += weight
            if _wrr_current[rid] > best_cur:
                best_cur = _wrr_current[rid]
                best = route
        if best is not None:
            _wrr_current[str(best["id"])] -= total
            return best
    return routes[0]


def _random_select(routes: list[dict[str, Any]]) -> dict[str, Any]:
    import random

    weights = [max(1, int(r.get("weight") or 1)) for r in routes]
    return random.choices(routes, weights=weights, k=1)[0]


def _least_loaded(routes: list[dict[str, Any]]) -> dict[str, Any]:
    """進行中請求最少者優先；並列時權重較高者優先。"""
    with _lock:
        return min(
            routes,
            key=lambda r: (
                int(_inflight.get(str(r.get("id") or ""), 0)),
                -max(1, int(r.get("weight") or 1)),
            ),
        )


def mark_route_start(route_id: str) -> None:
    rid = (route_id or "").strip()
    if not rid:
        return
    with _lock:
        _inflight[rid] = int(_inflight.get(rid) or 0) + 1


def mark_route_end(route_id: str) -> None:
    rid = (route_id or "").strip()
    if not rid:
        return
    with _lock:
        _inflight[rid] = max(0, int(_inflight.get(rid) or 0) - 1)


def route_inflight_snapshot() -> dict[str, int]:
    with _lock:
        return dict(_inflight)


def select_route(
    *,
    route_id: str | None = None,
    model: str | None = None,
    strategy: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """依角色指定 / 全域策略 / 模型歸屬挑一條路由。

    角色 `route_id` 永遠優先。`role_preferred` 依模型所屬 API；
    加權輪詢／隨機／最少負載會跨 API 分發（再 clamp 到該路由模型池）。
    """
    runtime = cfg or get_runtime_config()
    enabled = list_enabled_routes(runtime)
    if not enabled:
        enabled = list_routes(runtime)
    if not enabled:
        return None

    if route_id:
        hit = resolve_route_ref(route_id, runtime)
        if hit and hit.get("enabled", True):
            return hit

    chosen_strategy = normalize_strategy(strategy or get_route_strategy(runtime))
    if chosen_strategy == "role_preferred" and model:
        owned = find_route_for_model(model, runtime)
        if owned:
            return owned

    if chosen_strategy == "weighted_round_robin" and len(enabled) > 1:
        return _weighted_round_robin(enabled)
    if chosen_strategy == "random" and len(enabled) > 1:
        return _random_select(enabled)
    if chosen_strategy == "least_loaded" and len(enabled) > 1:
        return _least_loaded(enabled)
    if chosen_strategy == "failover":
        primary = get_default_route(runtime)
        if primary and primary.get("enabled", True):
            return primary
        non_fallback = [r for r in enabled if not r.get("fallback")]
        return (non_fallback or enabled)[0]

    if model:
        owned = find_route_for_model(model, runtime)
        if owned:
            return owned
    return get_default_route(runtime) or enabled[0]


def list_failover_chain(
    *,
    route_id: str | None = None,
    model: str | None = None,
    extra_models: list[str] | None = None,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """呼叫失敗時依序嘗試的路由：指定／預設 → 角色備援模型所屬 API → 標為備援 →（failover 策略）其餘。"""
    runtime = cfg or get_runtime_config()
    enabled = list_enabled_routes(runtime)
    if not enabled:
        enabled = list_routes(runtime)
    if not enabled:
        return []

    primary = select_route(route_id=route_id, model=model, cfg=runtime)
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(route: dict[str, Any] | None) -> None:
        if not route:
            return
        rid = str(route.get("id") or "")
        if not rid or rid in seen:
            return
        seen.add(rid)
        chain.append(route)

    _add(primary)
    for extra in extra_models or []:
        owned = find_route_for_model(str(extra), runtime)
        _add(owned)
    for route in enabled:
        if route.get("fallback"):
            _add(route)
    # 全域 failover 且未指定角色路由時，才把其餘 API 納入備援鏈
    if get_route_strategy(runtime) == "failover" and not route_id:
        for route in enabled:
            _add(route)
    return chain


def resolve_target(
    *,
    model: str | None = None,
    route_id: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """解析此次呼叫要用的憑證與模型。"""
    from backend.core.provider_pool import clamp_model

    runtime = cfg or get_runtime_config()
    route = select_route(route_id=route_id, model=model, cfg=runtime)
    if route is None:
        fallback_model = clamp_model(model, cfg=runtime)
        return {
            "route": None,
            "route_id": "",
            "model": fallback_model,
            "api_key": str(runtime.get("api_key") or ""),
            "api_base": str(runtime.get("api_base") or ""),
            "provider": str(runtime.get("provider_kind") or ""),
            "provider_routing": None,
            "cfg": runtime,
        }
    route_cfg = route_as_cfg(route)
    resolved = clamp_model(model or str(route.get("model") or ""), cfg=route_cfg)
    return {
        "route": route,
        "route_id": route.get("id") or "",
        "model": resolved,
        "api_key": str(route.get("api_key") or ""),
        "api_base": str(route.get("api_base") or ""),
        "provider": str(route.get("provider") or ""),
        "provider_routing": route.get("provider_routing"),
        "cfg": route_cfg,
    }
