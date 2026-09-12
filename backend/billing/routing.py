"""共享池路由決策樹 v6.0 Phase 2。"""
from __future__ import annotations

from typing import Any, Literal

from backend.billing.pool_store import get_pool_store
from backend.billing.shared_pool import list_shared_pool_keys, sort_keys_for_routing

RoutingMode = Literal[
    "single",
    "same_org_split",
    "relay",
    "parallel_split",
    "degrade",
    "public_pool",
    "queue_reject",
]


def _public_pool_available() -> bool:
    store = get_pool_store()
    paused = store.get_routing_runtime("public_pool_paused", False)
    return not bool(paused)


def route_key_selection(
    *,
    task_id: str,
    account_id: str,
    model: str,
    estimate_credits: float,
    org_id: str | None = None,
) -> dict[str, Any]:
    """
    決策樹：
    1. 單 Key
    2. 同 org 多 Key → relay 優先於 parallel
    3. 降級 / 公共池 / 排隊拒絕
    """
    raw = list_shared_pool_keys(
        model=model,
        estimate_credits=estimate_credits,
        account_id=account_id,
        org_id=org_id,
    )
    healthy = [k for k in raw if k.get("health_status") not in {"offline", "unhealthy"}]
    sorted_keys = sort_keys_for_routing(healthy, model=model, estimate_credits=estimate_credits)

    decision: dict[str, Any] = {
        "task_id": task_id,
        "account_id": account_id,
        "model": model,
        "estimate_credits": estimate_credits,
        "candidates_count": len(raw),
        "healthy_count": len(healthy),
    }

    if not sorted_keys:
        degraded = [k for k in raw if k.get("health_status") == "degraded"]
        if degraded:
            chosen = sort_keys_for_routing(degraded, model=model, estimate_credits=estimate_credits)[0]
            decision.update(
                _finalize_decision(
                    mode="degrade",
                    keys=[chosen],
                    reason="degraded_key_only",
                )
            )
        elif _public_pool_available():
            pub = _public_pool_key(model, estimate_credits)
            decision.update(_finalize_decision(mode="public_pool", keys=[pub], reason="no_contributor_keys"))
        else:
            decision.update(_finalize_decision(mode="queue_reject", keys=[], reason="no_eligible_keys"))
        _log_decision(decision)
        return decision

    contributor_keys = [
        k
        for k in sorted_keys
        if not k.get("is_platform_default") and not k.get("is_public_pool")
    ]
    if not contributor_keys and not _public_pool_available():
        decision.update(_finalize_decision(mode="queue_reject", keys=[], reason="public_pool_paused_no_contributors"))
        _log_decision(decision)
        return decision

    pool_keys = contributor_keys if contributor_keys else sorted_keys

    same_org = [k for k in pool_keys if k.get("same_org")]
    if len(same_org) == 1 and len(pool_keys) == 1:
        decision.update(_finalize_decision(mode="single", keys=[same_org[0]], reason="single_eligible_key"))
    elif len(same_org) >= 2:
        same_org_mode: RoutingMode = "relay" if _prefer_relay(same_org, estimate_credits) else "parallel_split"
        decision.update(
            _finalize_decision(
                mode="same_org_split" if same_org_mode == "parallel_split" else "relay",
                keys=same_org[: min(3, len(same_org))],
                reason=f"same_org_{same_org_mode}",
                split_mode=same_org_mode,
            )
        )
    elif len(pool_keys) >= 2:
        multi_mode: RoutingMode = "relay" if _prefer_relay(pool_keys, estimate_credits) else "parallel_split"
        decision.update(
            _finalize_decision(
                mode=multi_mode,
                keys=pool_keys[: min(3, len(pool_keys))],
                reason=f"multi_key_{multi_mode}",
                split_mode=multi_mode,
            )
        )
    else:
        decision.update(_finalize_decision(mode="single", keys=[pool_keys[0]], reason="best_single_key"))

    _log_decision(decision)
    return decision


def _prefer_relay(keys: list[dict[str, Any]], estimate_credits: float) -> bool:
    """Relay 優先：存在高 cache affinity 且配額足夠的 Key。"""
    for k in keys:
        if float(k.get("cache_affinity", 0)) >= 0.3 and float(k.get("quota_remaining", 0)) >= estimate_credits:
            return True
    return len(keys) >= 2 and any(float(k.get("cache_affinity", 0)) > 0.1 for k in keys)


def _public_pool_key(model: str, estimate_credits: float) -> dict[str, Any]:
    from backend.billing.vendor_configs import detect_vendor

    vid = detect_vendor(model)
    store = get_pool_store()
    vc = store.active_vendor_config().get("config", {}).get(vid, {})
    return {
        "key_id": "public_pool_premium",
        "vendor_id": vid,
        "vendor_tier": vc.get("tier", "标准"),
        "routing_weight": float(vc.get("routing_weight", 1.0)),
        "is_public_pool": True,
        "premium_multiplier": store.get_routing_runtime("public_pool_premium", 1.15),
        "quota_remaining": estimate_credits * 50,
        "cache_affinity": 0.0,
        "health_status": "healthy",
    }


def _finalize_decision(
    *,
    mode: RoutingMode,
    keys: list[dict[str, Any]],
    reason: str,
    split_mode: str | None = None,
) -> dict[str, Any]:
    primary = keys[0] if keys else None
    return {
        "routing_mode": mode,
        "binding_reason": reason,
        "split_mode": split_mode,
        "primary_key_id": primary["key_id"] if primary else None,
        "selected_keys": [
            {
                "key_id": k["key_id"],
                "org_id": k.get("org_id"),
                "vendor_id": k.get("vendor_id"),
                "routing_weight": k.get("routing_weight"),
                "cache_affinity": k.get("cache_affinity"),
                "health_status": k.get("health_status"),
            }
            for k in keys
        ],
        "vendor_id": primary.get("vendor_id") if primary else None,
        "vendor_tier": primary.get("vendor_tier") if primary else None,
        "routing_weight": primary.get("routing_weight") if primary else None,
        "rejected": mode == "queue_reject",
    }


def _log_decision(decision: dict[str, Any]) -> None:
    get_pool_store().log_routing_decision(decision)


def apply_routing_binding(task_id: str, decision: dict[str, Any]) -> dict[str, Any]:
    """將路由決策綁定至任務。"""
    if decision.get("rejected"):
        return {**decision, "bound": False, "error": "queue_reject"}

    store = get_pool_store()
    primary = decision.get("primary_key_id")
    if not primary:
        return {**decision, "bound": False, "error": "no_primary_key"}

    org_id = None
    selected = decision.get("selected_keys") or []
    if selected:
        org_id = selected[0].get("org_id")

    store.bind_task_key(
        task_id,
        primary,
        org_id=org_id,
        reason=str(decision.get("binding_reason", "routed")),
    )
    if len(selected) > 1:
        store.save_task_key_split(
            task_id,
            selected,
            split_mode=str(decision.get("split_mode") or decision.get("routing_mode") or ""),
        )
    return {**decision, "bound": True, "key_id": primary, "task_id": task_id}
