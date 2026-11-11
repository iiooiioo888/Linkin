"""PoolStore 的池別餘額、grant、ledger 與扣款（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.billing.plans import get_plan
from backend.billing.pool_types import (
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_LOCKED,
    POOL_MONTHLY_GRANT,
    POOL_PURCHASED,
    SPEND_ORDER,
)

from .pricing import _PricingMixin
from .schema import _month_key, _utc_now


class _PoolsMixin(_PricingMixin):
    def ensure_pools(self, user_id: str, plan_id: str = "free") -> str:
        account_id = user_id.strip()
        now = _utc_now()
        with self._conn() as conn:
            for pool in (POOL_MONTHLY_GRANT, POOL_PURCHASED, POOL_CONTRIBUTION_UNLOCKED, POOL_CONTRIBUTION_LOCKED, POOL_LOCKED):
                conn.execute(
                    "INSERT OR IGNORE INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, 0, ?)",
                    (account_id, pool, now),
                )
            self._grant_monthly_if_needed(conn, account_id, plan_id, now)
        return account_id

    def _grant_monthly_if_needed(self, conn: sqlite3.Connection, account_id: str, plan_id: str, now: str) -> None:
        month = _month_key()
        source = f"subscription:{month}"
        exists = conn.execute(
            "SELECT 1 FROM grants WHERE account_id=? AND pool_type=? AND source=? LIMIT 1",
            (account_id, POOL_MONTHLY_GRANT, source),
        ).fetchone()
        if exists:
            return
        plan = get_plan(plan_id)
        amount = float(plan["monthly_credits"])
        if amount <= 0:
            return
        grant_id = f"g_{uuid.uuid4().hex[:12]}"
        end = datetime.now(timezone.utc).replace(day=28).isoformat()
        conn.execute(
            """INSERT INTO grants(grant_id, account_id, pool_type, amount, remaining, expires_at, source, origin, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (grant_id, account_id, POOL_MONTHLY_GRANT, amount, amount, end, source, f"plan:{plan_id}", now),
        )
        conn.execute(
            """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id, pool_type) DO UPDATE SET
               amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
            (account_id, POOL_MONTHLY_GRANT, amount, now),
        )

    def get_balances(self, account_id: str) -> dict[str, float]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT pool_type, amount FROM balances WHERE account_id = ?", (account_id.strip(),)
            ).fetchall()
        return {str(r["pool_type"]): float(r["amount"]) for r in rows}

    def total_spendable(self, account_id: str) -> float:
        bals = self.get_balances(account_id)
        return round(sum(bals.get(p, 0.0) for p in SPEND_ORDER), 4)

    def _append_ledger_conn(
        self,
        conn: sqlite3.Connection,
        account_id: str,
        entry_type: str,
        amount: float,
        balance_after: float,
        *,
        pool_type: str | None = None,
        source: str = "",
        description: str = "",
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        """寫 ledger 列；交易由呼叫端提供，讓餘額變動與帳目同進同出。"""
        entry_id = f"led_{uuid.uuid4().hex[:12]}"
        conn.execute(
                """INSERT INTO pool_ledger(entry_id, account_id, entry_type, amount, balance_after,
                   pool_type, source, description, task_id, meta_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    account_id,
                    entry_type,
                    amount,
                    balance_after,
                    pool_type,
                    source,
                    description,
                    task_id,
                    json.dumps(meta or {}, ensure_ascii=False),
                    _utc_now(),
                ),
            )
        return entry_id

    def append_ledger(
        self,
        account_id: str,
        entry_type: str,
        amount: float,
        balance_after: float,
        *,
        pool_type: str | None = None,
        source: str = "",
        description: str = "",
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> str:
        with self._conn() as conn:
            return self._append_ledger_conn(
                conn,
                account_id,
                entry_type,
                amount,
                balance_after,
                pool_type=pool_type,
                source=source,
                description=description,
                task_id=task_id,
                meta=meta,
            )

    def atomic_debit_pool(self, conn: sqlite3.Connection, account_id: str, pool_type: str, amount: float, now: str) -> bool:
        """原子扣款：UPDATE ... WHERE amount >= X。"""
        cur = conn.execute(
            """UPDATE balances SET amount = amount - ?, updated_at = ?
               WHERE account_id = ? AND pool_type = ? AND amount >= ?""",
            (amount, now, account_id, pool_type, amount),
        )
        return cur.rowcount > 0

    def spend_from_pools(
        self,
        account_id: str,
        amount: float,
        *,
        task_id: str | None = None,
        source: str = "usage",
    ) -> dict[str, float]:
        if amount <= 0:
            return {}
        remaining = round(float(amount), 4)
        breakdown: dict[str, float] = {}
        now = _utc_now()
        with self._conn() as conn:
            for pool in SPEND_ORDER:
                if remaining <= 0:
                    break
                row = conn.execute(
                    "SELECT amount FROM balances WHERE account_id=? AND pool_type=?",
                    (account_id, pool),
                ).fetchone()
                avail = float(row["amount"]) if row else 0.0
                if avail <= 0:
                    continue
                take = round(min(avail, remaining), 4)
                if not self.atomic_debit_pool(conn, account_id, pool, take, now):
                    row2 = conn.execute(
                        "SELECT amount FROM balances WHERE account_id=? AND pool_type=?",
                        (account_id, pool),
                    ).fetchone()
                    avail2 = float(row2["amount"]) if row2 else 0.0
                    if avail2 <= 0:
                        continue
                    take = round(min(avail2, remaining), 4)
                    if not self.atomic_debit_pool(conn, account_id, pool, take, now):
                        raise ValueError("INSUFFICIENT_CREDITS")
                if pool == POOL_MONTHLY_GRANT:
                    conn.execute(
                        """UPDATE grants SET remaining = MAX(0, remaining - ?)
                           WHERE account_id=? AND pool_type=? AND remaining > 0""",
                        (take, account_id, pool),
                    )
                breakdown[pool] = breakdown.get(pool, 0.0) + take
                remaining = round(remaining - take, 4)
            if remaining > 0:
                raise ValueError("INSUFFICIENT_CREDITS")
            # 餘額與帳目同一個交易：程序中途死掉不會留下「扣了錢、沒記帳」。
            rows = conn.execute(
                "SELECT pool_type, amount FROM balances WHERE account_id = ?", (account_id,)
            ).fetchall()
            total_after = round(
                sum(float(r["amount"]) for r in rows if str(r["pool_type"]) in SPEND_ORDER), 4
            )
            self._append_ledger_conn(
                conn,
                account_id,
                "debit",
                -amount,
                total_after,
                source=source,
                description=f"扣款 {amount:.4f}",
                task_id=task_id,
                meta={"breakdown": breakdown},
            )
        return breakdown

    def credit_pool(
        self,
        account_id: str,
        pool_type: str,
        amount: float,
        *,
        source: str,
        description: str = "",
        expires_at: str | None = None,
        task_id: str | None = None,
        origin: str = "",
        lock_days: int | None = None,
        lock_multiplier: float | None = None,
    ) -> None:
        if amount <= 0:
            return
        now = _utc_now()
        grant_origin = origin or source
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(account_id, pool_type) DO UPDATE SET
                   amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                (account_id, pool_type, amount, now),
            )
            if pool_type in (POOL_MONTHLY_GRANT, POOL_CONTRIBUTION_UNLOCKED, POOL_CONTRIBUTION_LOCKED):
                gid = f"g_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    """INSERT INTO grants(grant_id, account_id, pool_type, amount, remaining, expires_at,
                       source, origin, lock_days, lock_multiplier, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (gid, account_id, pool_type, amount, amount, expires_at, source, grant_origin, lock_days, lock_multiplier, now),
                )
            bal_row = conn.execute(
                "SELECT amount FROM balances WHERE account_id=? AND pool_type=?",
                (account_id, pool_type),
            ).fetchone()
            balance_after = float(bal_row["amount"]) if bal_row else amount
            self._append_ledger_conn(
                conn,
                account_id,
                "credit",
                amount,
                balance_after,
                pool_type=pool_type,
                source=source,
                description=description or f"入帳 {amount:.4f}",
                task_id=task_id,
                meta={"origin": grant_origin, "immutable": True},
            )
