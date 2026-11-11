"""PoolStore 的任務計費紀錄、用量事件與月結算（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from backend.billing.pool_types import POOL_MONTHLY_GRANT, POOL_PURCHASED

from .pools import _PoolsMixin
from .schema import _month_key, _utc_now


class _TaskBillingMixin(_PoolsMixin):
    def create_task_record(
        self,
        task_id: str,
        account_id: str,
        estimate: float,
        reserved: float,
        snapshot: dict[str, Any],
        *,
        run_mode: str = "normal",
        lock_multiplier: float = 1.0,
    ) -> None:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO tasks(task_id, account_id, estimate_credits, reserved_credits,
                   pricing_config_version, credit_policy_version, rollover_policy_version,
                   pricing_snapshot_json, run_mode, lock_multiplier, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    account_id,
                    estimate,
                    reserved,
                    snapshot.get("pricing_config_version"),
                    snapshot.get("credit_policy_version"),
                    snapshot.get("rollover_policy_version"),
                    json.dumps(snapshot, ensure_ascii=False),
                    run_mode,
                    lock_multiplier,
                    now,
                    now,
                ),
            )
            conn.execute(
                """INSERT INTO pool_reservations(reservation_id, task_id, account_id, amount, status, created_at)
                   VALUES (?, ?, ?, ?, 'held', ?)""",
                (f"rsv_{uuid.uuid4().hex[:12]}", task_id, account_id, reserved, now),
            )

    def bind_task_key(self, task_id: str, key_id: str, *, org_id: str | None = None, reason: str = "single_key") -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_key_binding(task_id, key_id, org_id, binding_reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (task_id, key_id, org_id, reason, _utc_now()),
            )

    def get_task_snapshot(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT pricing_snapshot_json FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row or not row["pricing_snapshot_json"]:
            return None
        return json.loads(row["pricing_snapshot_json"])

    def record_usage_event(
        self,
        *,
        account_id: str,
        task_id: str | None,
        event_type: str,
        source: str,
        tokens: int = 0,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
        cost_credits: float = 0,
        pricing_version: int | None = None,
        key_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        eid = f"ue_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO pool_usage_events(event_id, task_id, account_id, key_id, event_type, source,
                   tokens, cached_tokens, cache_write_tokens, cost_credits, pricing_version, meta_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    eid,
                    task_id,
                    account_id,
                    key_id,
                    event_type,
                    source,
                    tokens,
                    cached_tokens,
                    cache_write_tokens,
                    cost_credits,
                    pricing_version,
                    json.dumps(meta or {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )
        return eid

    def run_monthly_rollover(self, month_key: str | None = None) -> list[dict[str, Any]]:
        mk = month_key or _month_key()
        results: list[dict[str, Any]] = []
        with self._conn() as conn:
            user_ids = [r["user_id"] for r in conn.execute("SELECT user_id FROM accounts").fetchall()]
            for account_id in user_ids:
                plan_row = conn.execute("SELECT plan_id FROM accounts WHERE user_id=?", (account_id,)).fetchone()
                plan_id = str(plan_row["plan_id"]) if plan_row else "free"
                policy = self._policy_for_plan(conn, plan_id)
                ratio = float(policy["monthly_rollover_ratio"])
                cap = float(policy["rollover_cap"])
                row = conn.execute(
                    "SELECT amount FROM balances WHERE account_id=? AND pool_type=?",
                    (account_id, POOL_MONTHLY_GRANT),
                ).fetchone()
                unused = float(row["amount"]) if row else 0.0
                if unused <= 0:
                    continue
                # 本月（或之後）才發的月額度屬於「本月還沒用完」，不是上月餘額；
                # 沒有這道檢查，每次啟動跑 rollover 都會把當月額度清零。
                grant_row = conn.execute(
                    "SELECT MAX(created_at) AS last FROM grants WHERE account_id=? AND pool_type=?",
                    (account_id, POOL_MONTHLY_GRANT),
                ).fetchone()
                last_grant_month = str((grant_row["last"] if grant_row else "") or "")[:7]
                if last_grant_month and last_grant_month >= mk:
                    continue
                existing = conn.execute(
                    "SELECT 1 FROM rollover_records WHERE account_id=? AND month_key=?",
                    (account_id, mk),
                ).fetchone()
                if existing:
                    continue
                rolled = min(unused * ratio, cap)
                forfeited = unused - rolled
                now = _utc_now()
                conn.execute(
                    "UPDATE balances SET amount=0, updated_at=? WHERE account_id=? AND pool_type=?",
                    (now, account_id, POOL_MONTHLY_GRANT),
                )
                if rolled > 0:
                    conn.execute(
                        """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
                           ON CONFLICT(account_id, pool_type) DO UPDATE SET
                           amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                        (account_id, POOL_PURCHASED, rolled, now),
                    )
                rid = f"ro_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO rollover_records(record_id, account_id, month_key, unused_monthly,
                       rollover_ratio, rolled_to_purchased, forfeited, policy_version, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (rid, account_id, mk, unused, ratio, rolled, forfeited, policy["version"], now),
                )
                results.append({"account_id": account_id, "unused": unused, "rolled": rolled, "forfeited": forfeited})
        return results

    def list_grants(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT grant_id, pool_type, amount, remaining, expires_at, source, origin,
                   lock_days, lock_multiplier, created_at FROM grants
                   WHERE account_id=? ORDER BY created_at DESC LIMIT ?""",
                (account_id.strip(), max(1, min(limit, 200))),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_rollover_for_account(self, account_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM rollover_records WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
                (account_id.strip(), limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def upsert_subtask(
        self,
        *,
        subtask_id: str,
        task_id: str,
        account_id: str,
        estimate_credits: float = 0,
        key_id: str | None = None,
        parent_subtask_id: str | None = None,
        status: str = "pending",
        meta: dict[str, Any] | None = None,
    ) -> None:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO subtasks(subtask_id, task_id, account_id, parent_subtask_id, status,
                   estimate_credits, key_id, meta_json, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(subtask_id) DO UPDATE SET
                   status=excluded.status,
                   estimate_credits=excluded.estimate_credits,
                   key_id=COALESCE(excluded.key_id, subtasks.key_id),
                   meta_json=excluded.meta_json,
                   updated_at=excluded.updated_at""",
                (
                    subtask_id,
                    task_id,
                    account_id,
                    parent_subtask_id,
                    status,
                    estimate_credits,
                    key_id,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                    now,
                ),
            )
