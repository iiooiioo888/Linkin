"""任務級 API Key 綁定 v6.0 — 含廠商路由權重與 Key 健康追蹤。"""
from __future__ import annotations

import os
from typing import Any, Literal

from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import VENDOR_TIER_WEIGHTS
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS, detect_vendor

FailureKind = Literal["key_failure", "balance_exhausted"]


def _default_key_id() -> str:
    return os.environ.get("LINKIN_DEFAULT_API_KEY_ID", "platform_default")


def _candidate_keys(model: str) -> list[dict[str, Any]]:
    """Phase 1：平台預設 Key + 廠商權重排序。Phase 2 擴展多 Key 樹。"""
    vid = detect_vendor(model)
    vc = DEFAULT_VENDOR_CONFIGS.get(vid, DEFAULT_VENDOR_CONFIGS["self_host"])
    tier = vc.get("tier", "标准")
    weight = float(vc.get("routing_weight", VENDOR_TIER_WEIGHTS.get(tier, 1.0)))
    return [
        {
            "key_id": _default_key_id(),
            "vendor_id": vid,
            "vendor_tier": tier,
            "routing_weight": weight,
            "org_id": None,
        }
    ]


def select_and_bind_key(
    task_id: str,
    *,
    estimate_credits: float,
    model: str = "default",
) -> dict[str, Any]:
    """
    Key 排序：quota≥est×1.3 → model → cache affinity → price → quality → concurrency → vendor routing weight
    Phase 1：單 Key + 廠商權重記錄。
    """
    store = get_pool_store()
    candidates = sorted(_candidate_keys(model), key=lambda k: -k["routing_weight"])
    chosen = candidates[0]
    store.bind_task_key(
        task_id,
        chosen["key_id"],
        reason=f"vendor_weight_{chosen['routing_weight']}",
    )
    return {
        "task_id": task_id,
        "key_id": chosen["key_id"],
        "vendor_id": chosen["vendor_id"],
        "vendor_tier": chosen["vendor_tier"],
        "routing_weight": chosen["routing_weight"],
        "binding_reason": "single_key_vendor_weighted",
        "routing_mode": "single",
    }


def get_task_key(task_id: str) -> str | None:
    with get_pool_store()._conn() as conn:
        row = conn.execute("SELECT key_id FROM task_key_binding WHERE task_id=?", (task_id,)).fetchone()
    return str(row["key_id"]) if row else None


def record_key_event(
    key_id: str,
    failure_kind: FailureKind,
    *,
    task_id: str | None = None,
    contributor_id: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """記錄 Key 事件；僅 key_failure 觸發分期沒收，balance_exhausted 不追究貢獻者。"""
    store = get_pool_store()
    health = store.record_key_health_event(
        key_id,
        event=failure_kind,
        contributor_id=contributor_id,
        reason=reason,
    )
    forfeitures: list[dict[str, Any]] = []
    if failure_kind == "key_failure":
        forfeitures = store.forfeit_installments_for_key_failure(key_id, task_id=task_id)
    return {"health": health, "forfeitures": forfeitures, "failure_kind": failure_kind}


def mark_failover(
    task_id: str,
    new_key_id: str,
    *,
    failure_kind: FailureKind = "key_failure",
    old_key_id: str | None = None,
) -> dict[str, Any]:
    store = get_pool_store()
    failed_key = old_key_id or get_task_key(task_id)
    store.bind_task_key(task_id, new_key_id, reason=f"failover_{failure_kind}")
    result: dict[str, Any] = {"task_id": task_id, "new_key_id": new_key_id, "failure_kind": failure_kind}
    if failed_key and failure_kind == "key_failure":
        result["key_event"] = record_key_event(
            failed_key,
            "key_failure",
            task_id=task_id,
            reason="failover_abnormal",
        )
    elif failed_key:
        result["key_event"] = record_key_event(
            failed_key,
            "balance_exhausted",
            task_id=task_id,
            reason="consumer_balance_exhausted",
        )
    return result
