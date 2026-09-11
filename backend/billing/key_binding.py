"""任務級 API Key 綁定 v6.0 — 含廠商路由權重。"""
from __future__ import annotations

import os
from typing import Any

from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import VENDOR_TIER_WEIGHTS
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS, detect_vendor


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


def mark_failover(task_id: str, new_key_id: str) -> None:
    store = get_pool_store()
    store.bind_task_key(task_id, new_key_id, reason="failover_abnormal")
