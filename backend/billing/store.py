"""靈境積分計費 SQLite 持久層。"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.billing.plans import get_plan, normalize_plan_id
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import POOL_PURCHASED


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class BillingStore:
    def __init__(self, db_path: str | None = None) -> None:
        if db_path is None:
            override = os.getenv("LINKIN_BILLING_DB", "").strip() or os.getenv("LINKIN_WALLET_DB", "").strip()
            db_path = override or str(Path(__file__).resolve().parents[1] / "data" / "billing.sqlite3")
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        from backend.billing.pool_store import PoolStore, reset_pool_store

        reset_pool_store(PoolStore(db_path=self.db_path))
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS accounts (
                        user_id TEXT PRIMARY KEY,
                        balance_credits REAL NOT NULL DEFAULT 0 CHECK (balance_credits >= 0),
                        plan_id TEXT NOT NULL DEFAULT 'free',
                        byok INTEGER NOT NULL DEFAULT 0,
                        monthly_quota_credits REAL NOT NULL DEFAULT 0,
                        monthly_used_credits REAL NOT NULL DEFAULT 0,
                        period_key TEXT NOT NULL DEFAULT '',
                        concurrency_limit INTEGER NOT NULL DEFAULT 1,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS subscriptions (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        plan_id TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        started_at TEXT NOT NULL,
                        renews_at TEXT,
                        meta_json TEXT
                    );

                    CREATE TABLE IF NOT EXISTS price_plans (
                        id TEXT PRIMARY KEY,
                        config_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS usage_events (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        credits REAL NOT NULL,
                        quantity REAL NOT NULL DEFAULT 1,
                        unit TEXT NOT NULL DEFAULT 'credit',
                        task_id TEXT,
                        reference TEXT,
                        meta_json TEXT,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS ledger (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        amount_credits REAL NOT NULL,
                        balance_after_credits REAL NOT NULL,
                        kind TEXT NOT NULL CHECK (kind IN ('credit', 'debit')),
                        source TEXT NOT NULL,
                        reference TEXT,
                        meta_json TEXT,
                        created_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS reservations (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        estimated_credits REAL NOT NULL,
                        settled_credits REAL,
                        status TEXT NOT NULL DEFAULT 'open',
                        created_at TEXT NOT NULL,
                        settled_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS invoices (
                        id TEXT PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        period_key TEXT NOT NULL,
                        total_credits REAL NOT NULL DEFAULT 0,
                        total_usd REAL,
                        status TEXT NOT NULL DEFAULT 'draft',
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_usage_events_user_created
                        ON usage_events(user_id, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_ledger_user_created
                        ON ledger(user_id, created_at DESC);
                    """
                )
                conn.commit()
        get_pool_store()._init_schema()

    def ensure_account(self, user_id: str, plan_id: str = "free") -> dict[str, Any]:
        user_id = user_id.strip()
        plan_id = normalize_plan_id(plan_id)
        plan = get_plan(plan_id)
        now = _utc_now()
        period = _month_key()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
                if row:
                    if row["period_key"] != period:
                        conn.execute(
                            """
                            UPDATE accounts SET monthly_used_credits = 0, period_key = ?, updated_at = ?
                            WHERE user_id = ?
                            """,
                            (period, now, user_id),
                        )
                        conn.commit()
                else:
                    quota = float(plan["monthly_credits"])
                    conn.execute(
                        """
                        INSERT INTO accounts
                            (user_id, balance_credits, plan_id, byok, monthly_quota_credits,
                             monthly_used_credits, period_key, concurrency_limit, created_at, updated_at)
                        VALUES (?, 0, ?, 0, ?, 0, ?, ?, ?, ?)
                        """,
                        (user_id, plan_id, quota, period, int(plan["concurrency"]), now, now),
                    )
                    conn.execute(
                        """
                        INSERT INTO subscriptions (id, user_id, plan_id, status, started_at, meta_json)
                        VALUES (?, ?, ?, 'active', ?, ?)
                        """,
                        (uuid.uuid4().hex, user_id, plan_id, now, json.dumps({"seed": True}, ensure_ascii=False)),
                    )
                    conn.commit()
        pools = get_pool_store()
        pools.ensure_pools(user_id, plan_id)
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,)).fetchone()
                return self._row_account(row)

    def get_account(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id.strip(),)).fetchone()
                if row:
                    row = self._migrate_legacy_plan_row(conn, row)
                return self._row_account(row) if row else None

    def _migrate_legacy_plan_row(self, conn, row) -> Any:
        """將舊版 plan_id（如 team）寫回現行方案。"""
        raw = str(row["plan_id"] or "free")
        normalized = normalize_plan_id(raw)
        if normalized == raw:
            return row
        plan = get_plan(normalized)
        now = _utc_now()
        conn.execute(
            """
            UPDATE accounts SET plan_id = ?, monthly_quota_credits = ?, concurrency_limit = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (normalized, float(plan["monthly_credits"]), int(plan["concurrency"]), now, row["user_id"]),
        )
        conn.commit()
        return conn.execute("SELECT * FROM accounts WHERE user_id = ?", (row["user_id"],)).fetchone()

    def set_plan(self, user_id: str, plan_id: str) -> dict[str, Any]:
        plan_id = normalize_plan_id(plan_id)
        plan = get_plan(plan_id)
        now = _utc_now()
        self.ensure_account(user_id, plan_id)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE accounts SET plan_id = ?, monthly_quota_credits = ?, concurrency_limit = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (plan_id, float(plan["monthly_credits"]), int(plan["concurrency"]), now, user_id.strip()),
                )
                conn.execute(
                    """
                    INSERT INTO subscriptions (id, user_id, plan_id, status, started_at)
                    VALUES (?, ?, ?, 'active', ?)
                    """,
                    (uuid.uuid4().hex, user_id.strip(), plan_id, now),
                )
                conn.commit()
        return self.ensure_account(user_id, plan_id)

    def credit(self, user_id: str, credits: float, *, source: str, reference: str = "", meta: dict | None = None) -> dict:
        self.ensure_account(user_id)
        amount = abs(float(credits))
        pools = get_pool_store()
        pools.credit_pool(
            user_id.strip(),
            POOL_PURCHASED,
            amount,
            source=source,
            description=reference or source,
        )
        balance = pools.total_spendable(user_id)
        now = _utc_now()
        entry_id = uuid.uuid4().hex
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO ledger (id, user_id, amount_credits, balance_after_credits, kind, source, reference, meta_json, created_at)
                    VALUES (?, ?, ?, ?, 'credit', ?, ?, ?, ?)
                    """,
                    (entry_id, user_id.strip(), amount, balance, source, reference, json.dumps(meta or {}, ensure_ascii=False), now),
                )
                conn.commit()
        return {"id": entry_id, "amount_credits": amount, "balance_after_credits": balance, "kind": "credit", "source": source, "reference": reference, "created_at": now}

    def debit(self, user_id: str, credits: float, *, source: str, reference: str = "", meta: dict | None = None) -> dict:
        from backend.billing.errors import InsufficientCreditsError

        self.ensure_account(user_id)
        amount = abs(float(credits))
        pools = get_pool_store()
        available = pools.total_spendable(user_id)
        if available < amount:
            raise InsufficientCreditsError(balance_credits=available, required_credits=amount)
        try:
            breakdown = pools.spend_from_pools(user_id.strip(), amount, source=source)
        except ValueError:
            raise InsufficientCreditsError(balance_credits=available, required_credits=amount) from None
        balance = pools.total_spendable(user_id)
        now = _utc_now()
        entry_id = uuid.uuid4().hex
        payload = dict(meta or {})
        payload["breakdown"] = breakdown
        with self._lock:
            with self._connect() as conn:
                monthly_used = float(conn.execute("SELECT monthly_used_credits FROM accounts WHERE user_id=?", (user_id.strip(),)).fetchone()["monthly_used_credits"])
                conn.execute(
                    "UPDATE accounts SET monthly_used_credits=?, updated_at=? WHERE user_id=?",
                    (round(monthly_used + amount, 4), now, user_id.strip()),
                )
                conn.execute(
                    """
                    INSERT INTO ledger (id, user_id, amount_credits, balance_after_credits, kind, source, reference, meta_json, created_at)
                    VALUES (?, ?, ?, ?, 'debit', ?, ?, ?, ?)
                    """,
                    (entry_id, user_id.strip(), -amount, balance, source, reference, json.dumps(payload, ensure_ascii=False), now),
                )
                conn.commit()
        return {"id": entry_id, "amount_credits": -amount, "balance_after_credits": balance, "kind": "debit", "source": source, "reference": reference, "created_at": now}

    def _adjust(self, user_id: str, amount_signed: float, *, kind: str, source: str, reference: str, meta: dict | None) -> dict:
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                return self._adjust_tx(conn, user_id, amount_signed if kind == "credit" else -abs(amount_signed), kind=kind, source=source, reference=reference, meta=meta)

    def _adjust_tx(self, conn, user_id: str, amount_signed: float, *, kind: str, source: str, reference: str, meta: dict | None) -> dict:
        now = _utc_now()
        entry_id = uuid.uuid4().hex
        row = conn.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id.strip(),)).fetchone()
        balance = float(row["balance_credits"])
        new_balance = round(balance + amount_signed, 4)
        if new_balance < 0:
            from backend.billing.errors import InsufficientCreditsError
            conn.rollback()
            raise InsufficientCreditsError(balance_credits=balance, required_credits=abs(amount_signed))
        monthly_used = float(row["monthly_used_credits"])
        if amount_signed < 0:
            monthly_used = round(monthly_used + abs(amount_signed), 4)
        conn.execute(
            "UPDATE accounts SET balance_credits = ?, monthly_used_credits = ?, updated_at = ? WHERE user_id = ?",
            (new_balance, monthly_used, now, user_id.strip()),
        )
        conn.execute(
            """
            INSERT INTO ledger (id, user_id, amount_credits, balance_after_credits, kind, source, reference, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (entry_id, user_id.strip(), amount_signed, new_balance, kind, source, reference, json.dumps(meta or {}, ensure_ascii=False), now),
        )
        conn.commit()
        return {"id": entry_id, "amount_credits": amount_signed, "balance_after_credits": new_balance, "kind": kind, "source": source, "reference": reference, "created_at": now}

    def add_usage_event(
        self,
        user_id: str,
        event_type: str,
        credits: float,
        *,
        quantity: float = 1,
        unit: str = "credit",
        task_id: str = "",
        reference: str = "",
        meta: dict | None = None,
    ) -> dict:
        now = _utc_now()
        eid = uuid.uuid4().hex
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO usage_events
                        (id, user_id, event_type, credits, quantity, unit, task_id, reference, meta_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (eid, user_id.strip(), event_type, float(credits), float(quantity), unit, task_id or "", reference, json.dumps(meta or {}, ensure_ascii=False), now),
                )
                conn.commit()
        return {"id": eid, "event_type": event_type, "credits": credits, "created_at": now}

    def list_usage_events(self, user_id: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM usage_events WHERE user_id = ? ORDER BY created_at DESC LIMIT ?
                    """,
                    (user_id.strip(), limit),
                ).fetchall()
        return [self._row_usage(r) for r in rows]

    def list_ledger(self, user_id: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT * FROM ledger WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                    (user_id.strip(), limit),
                ).fetchall()
        return [self._row_ledger(r) for r in rows]

    def create_reservation(self, user_id: str, estimated_credits: float) -> str:
        rid = uuid.uuid4().hex
        now = _utc_now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO reservations (id, user_id, estimated_credits, status, created_at) VALUES (?, ?, ?, 'open', ?)",
                    (rid, user_id.strip(), float(estimated_credits), now),
                )
                conn.commit()
        return rid

    def settle_reservation(self, reservation_id: str, actual_credits: float) -> None:
        now = _utc_now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE reservations SET settled_credits = ?, status = 'settled', settled_at = ? WHERE id = ?",
                    (float(actual_credits), now, reservation_id),
                )
                conn.commit()

    @staticmethod
    def _row_account(row) -> dict[str, Any]:
        if not row:
            return {}
        plan = get_plan(row["plan_id"])
        quota = float(row["monthly_quota_credits"])
        used = float(row["monthly_used_credits"])
        pools = get_pool_store()
        pool_balances = pools.get_balances(row["user_id"])
        balance = pools.total_spendable(row["user_id"])
        pricing = pools.active_pricing_config()
        policy = pools.active_credit_policy(row["plan_id"])
        monthly_grant = pool_balances.get("monthly_grant", 0.0)
        return {
            "user_id": row["user_id"],
            "balance_credits": balance,
            "pool_balances": pool_balances,
            "plan_id": row["plan_id"],
            "plan_name_zh": plan.get("name_zh", row["plan_id"]),
            "byok": bool(row["byok"]),
            "monthly_quota_credits": quota,
            "monthly_used_credits": used,
            "monthly_remaining_credits": max(0.0, monthly_grant),
            "period_key": row["period_key"],
            "concurrency_limit": int(row["concurrency_limit"]),
            "low_balance": balance > 0 and balance < max(100.0, min(1000.0, monthly_grant * 0.1 if monthly_grant > 0 else 100.0)),
            "features": plan.get("features") or [],
            "transfer_allowed": False,
            "pricing_config_version": pricing["version"],
            "credit_policy_version": policy["version"],
        }

    @staticmethod
    def _row_usage(row) -> dict:
        meta = {}
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except json.JSONDecodeError:
            pass
        return {
            "id": row["id"],
            "event_type": row["event_type"],
            "credits": float(row["credits"]),
            "quantity": float(row["quantity"]),
            "unit": row["unit"],
            "task_id": row["task_id"] or "",
            "reference": row["reference"] or "",
            "meta": meta,
            "created_at": row["created_at"],
        }

    @staticmethod
    def _row_ledger(row) -> dict:
        meta = {}
        try:
            meta = json.loads(row["meta_json"] or "{}")
        except json.JSONDecodeError:
            pass
        return {
            "id": row["id"],
            "amount_credits": float(row["amount_credits"]),
            "balance_after_credits": float(row["balance_after_credits"]),
            "kind": row["kind"],
            "source": row["source"],
            "reference": row["reference"] or "",
            "meta": meta,
            "created_at": row["created_at"],
        }


_STORE: BillingStore | None = None
_LOCK = threading.Lock()


def get_billing_store() -> BillingStore:
    global _STORE
    if _STORE is None:
        with _LOCK:
            if _STORE is None:
                _STORE = BillingStore()
    return _STORE


def reset_billing_store(store: BillingStore | None = None) -> None:
    global _STORE
    with _LOCK:
        _STORE = store
    from backend.billing.pool_store import PoolStore, reset_pool_store

    from backend.billing.pools_service import reset_pools_service

    if store is None:
        reset_pool_store(None)
        reset_pools_service(None)
    else:
        reset_pool_store(PoolStore(db_path=store.db_path))
        reset_pools_service(None)
