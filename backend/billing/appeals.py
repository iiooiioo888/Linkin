"""申訴系統（v6.0 — 含 Key 故障沒收申訴）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.billing.pool_store import KEY_FAILURE_APPEAL_WINDOW_DAYS, get_pool_store


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def create_appeal(
    account_id: str,
    *,
    task_id: str | None = None,
    reason: str = "",
    detail: str = "",
    appeal_kind: str = "general",
    installment_id: str | None = None,
) -> dict[str, Any]:
    store = get_pool_store()
    appeal_id = f"apl_{uuid.uuid4().hex[:12]}"
    forfeiture_amount = None
    appeal_deadline = None
    if appeal_kind == "key_failure_forfeiture":
        if not installment_id:
            raise ValueError("Key 故障申訴須提供 installment_id")
        inst = store.get_lock_installment(installment_id)
        if not inst or inst.get("account_id") != account_id.strip():
            raise ValueError("分期不存在或不屬於此帳戶")
        if inst.get("failure_reason") != "key_failure" and inst.get("status") != "forfeited_key_failure":
            raise ValueError("此分期非 Key 故障沒收，無法申訴")
        appeal_deadline = inst.get("appeal_deadline")
        if appeal_deadline and _parse_iso(str(appeal_deadline)) < datetime.now(timezone.utc):
            raise ValueError(f"申訴窗口已過（{KEY_FAILURE_APPEAL_WINDOW_DAYS} 天）")
        forfeiture_amount = float(inst.get("forfeited_amount") or 0)
        reason = reason or "key_failure_forfeiture"
    with store._conn() as conn:
        conn.execute(
            """INSERT INTO billing_appeals(
                   appeal_id, account_id, task_id, reason, detail, status, appeal_kind,
                   installment_id, forfeiture_amount, appeal_deadline, created_at)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (
                appeal_id,
                account_id.strip(),
                task_id,
                reason,
                detail,
                appeal_kind,
                installment_id,
                forfeiture_amount,
                appeal_deadline,
                _utc_now(),
            ),
        )
    return {
        "appeal_id": appeal_id,
        "status": "pending",
        "appeal_kind": appeal_kind,
        "forfeiture_amount": forfeiture_amount,
        "appeal_deadline": appeal_deadline,
    }


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


def resolve_appeal(
    appeal_id: str,
    status: str = "resolved",
    operator: str = "admin",
    note: str = "",
    *,
    restore_credits: bool = False,
) -> dict[str, Any]:
    store = get_pool_store()
    now = _utc_now()
    with store._conn() as conn:
        row = conn.execute("SELECT * FROM billing_appeals WHERE appeal_id=?", (appeal_id,)).fetchone()
        if not row:
            raise ValueError("申訴不存在")
        conn.execute(
            """UPDATE billing_appeals SET status=?, resolved_at=?, resolved_by=?, resolution_note=?
               WHERE appeal_id=?""",
            (status, now, operator, note, appeal_id),
        )
    restored = 0.0
    if restore_credits and status in {"resolved", "approved"} and row["appeal_kind"] == "key_failure_forfeiture":
        installment_id = row["installment_id"]
        amount = float(row["forfeiture_amount"] or 0)
        if installment_id and amount > 0:
            store.restore_key_failure_forfeiture(str(installment_id), amount)
            restored = amount
    return {"appeal_id": appeal_id, "status": status, "restored_credits": restored}
