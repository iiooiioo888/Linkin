"""任務級 API Key 綁定 — Phase 1 單 Key，Phase 2 路由擴展。"""
from __future__ import annotations

import os
import uuid
from typing import Any

from backend.billing.pool_store import get_pool_store


def _default_key_id() -> str:
    return os.environ.get("LINKIN_DEFAULT_API_KEY_ID", "platform_default")


def select_and_bind_key(
    task_id: str,
    *,
    estimate_credits: float,
    model: str = "default",
    org_id: str | None = None,
) -> dict[str, Any]:
    """
    Phase 1：單一平台 Key 綁定。
    Phase 2 stub：多 Key 路由、relay、split 決策樹。
    """
    store = get_pool_store()
    key_id = _default_key_id()
    store.bind_task_key(task_id, key_id, org_id=org_id, reason="single_key_sufficient")
    return {
        "task_id": task_id,
        "key_id": key_id,
        "binding_reason": "single_key_sufficient",
        "routing_mode": "single",
    }


def get_task_key(task_id: str) -> str | None:
    with get_pool_store()._conn() as conn:
        row = conn.execute("SELECT key_id FROM task_key_binding WHERE task_id=?", (task_id,)).fetchone()
    return str(row["key_id"]) if row else None


def mark_failover(task_id: str, new_key_id: str) -> None:
    """異常 failover：標記並切換 Key（成本進 fault_pool — Phase 2）。"""
    store = get_pool_store()
    store.bind_task_key(task_id, new_key_id, reason="failover_abnormal")
