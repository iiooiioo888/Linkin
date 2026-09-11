"""申訴系統（v6.0 Phase 1 基礎）。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.billing.pool_store import get_pool_store


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_appeal(account_id: str, *, task_id: str | None = None, reason: str = "", detail: str = "") -> dict[str, Any]:
    appeal_id = f"apl_{uuid.uuid4().hex[:12]}"
    with get_pool_store()._conn() as conn:
        conn.execute(
            """INSERT INTO billing_appeals(appeal_id, account_id, task_id, reason, detail, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
            (appeal_id, account_id.strip(), task_id, reason, detail, _utc_now()),
        )
    return {"appeal_id": appeal_id, "status": "pending"}


def list_appeals(account_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    with get_pool_store()._conn() as conn:
        if account_id:
            rows = conn.execute(
                "SELECT * FROM billing_appeals WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
                (account_id.strip(), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM billing_appeals ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


def resolve_appeal(appeal_id: str, status: str = "resolved", operator: str = "admin", note: str = "") -> dict[str, Any]:
    now = _utc_now()
    with get_pool_store()._conn() as conn:
        conn.execute(
            """UPDATE billing_appeals SET status=?, resolved_at=?, resolved_by=?, resolution_note=?
               WHERE appeal_id=?""",
            (status, now, operator, note, appeal_id),
        )
    return {"appeal_id": appeal_id, "status": status}
