"""多池積分持久層 — balances / grants / pricing / tasks / ledger（account_id = user_id）。"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.billing.plans import get_plan
from backend.billing.pool_types import (
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_LOCKED,
    POOL_MONTHLY_GRANT,
    POOL_PURCHASED,
    SPEND_ORDER,
)
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS
from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG

_DB_LOCK = threading.Lock()
_DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "billing.sqlite3"
_POOL_SCHEMA = """
CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    amount REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (account_id, pool_type)
);

CREATE TABLE IF NOT EXISTS grants (
    grant_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    amount REAL NOT NULL,
    remaining REAL NOT NULL,
    expires_at TEXT,
    source TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT '',
    lock_days INTEGER,
    lock_multiplier REAL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vendor_configs (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS billing_appeals (
    appeal_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    task_id TEXT,
    reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    resolved_by TEXT,
    resolution_note TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_configs (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    config_json TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS credit_policies (
    version INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'draft',
    effective_at TEXT NOT NULL,
    monthly_rollover_ratio REAL NOT NULL DEFAULT 0.5,
    rollover_cap REAL NOT NULL DEFAULT 50000,
    by_tier_json TEXT NOT NULL DEFAULT '{}',
    created_by TEXT NOT NULL DEFAULT 'system',
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pricing_config_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    version INTEGER NOT NULL,
    operator TEXT NOT NULL,
    action TEXT NOT NULL,
    old_json TEXT,
    new_json TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rollover_records (
    record_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    month_key TEXT NOT NULL,
    unused_monthly REAL NOT NULL,
    rollover_ratio REAL NOT NULL,
    rolled_to_purchased REAL NOT NULL,
    forfeited REAL NOT NULL,
    policy_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(account_id, month_key)
);

CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    estimate_credits REAL NOT NULL DEFAULT 0,
    reserved_credits REAL NOT NULL DEFAULT 0,
    settled_credits REAL NOT NULL DEFAULT 0,
    pricing_config_version INTEGER,
    credit_policy_version INTEGER,
    rollover_policy_version INTEGER,
    pricing_snapshot_json TEXT,
    run_mode TEXT NOT NULL DEFAULT 'normal',
    lock_multiplier REAL NOT NULL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_key_binding (
    task_id TEXT PRIMARY KEY,
    key_id TEXT NOT NULL,
    org_id TEXT,
    binding_reason TEXT NOT NULL DEFAULT 'single_key',
    is_failover INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_ledger (
    entry_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    pool_type TEXT,
    amount REAL NOT NULL,
    balance_after REAL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_usage_events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT,
    account_id TEXT NOT NULL,
    key_id TEXT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    cost_credits REAL NOT NULL DEFAULT 0,
    pricing_version INTEGER,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pool_reservations (
    reservation_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'held',
    created_at TEXT NOT NULL,
    released_at TEXT
);

CREATE TABLE IF NOT EXISTS pool_ledger (
    entry_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    pool_type TEXT,
    source TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    task_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contributors (
    contributor_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    contributor_id TEXT,
    org_id TEXT,
    encrypted_key TEXT NOT NULL,
    limits_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    task_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lock_installments (
    installment_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    total_amount REAL NOT NULL,
    per_installment REAL NOT NULL,
    paid_installments INTEGER NOT NULL DEFAULT 0,
    lock_days INTEGER NOT NULL,
    lock_multiplier REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    next_due_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id TEXT,
    l3_hits INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    savings_credits REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_grants_account_pool ON grants(account_id, pool_type);
CREATE INDEX IF NOT EXISTS idx_pool_ledger_account ON pool_ledger(account_id, created_at);
CREATE INDEX IF NOT EXISTS idx_tasks_account ON tasks(account_id);
CREATE INDEX IF NOT EXISTS idx_pool_usage_task ON pool_usage_events(task_id);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _month_key(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y-%m")


class PoolStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            import os

            override = os.getenv("LINKIN_BILLING_DB", "").strip() or os.getenv("LINKIN_WALLET_DB", "").strip()
            db_path = override or str(_DEFAULT_DB)
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with _DB_LOCK:
            conn = sqlite3.connect(self.db_path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_POOL_SCHEMA)
            self._migrate_columns(conn)
            self._migrate_legacy_balance(conn)
            self._seed_defaults(conn)

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        """增量欄位（舊 DB 相容）。"""
        for stmt in (
            "ALTER TABLE grants ADD COLUMN origin TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE grants ADD COLUMN lock_days INTEGER",
            "ALTER TABLE grants ADD COLUMN lock_multiplier REAL",
            "ALTER TABLE tasks ADD COLUMN run_mode TEXT NOT NULL DEFAULT 'normal'",
            "ALTER TABLE tasks ADD COLUMN lock_multiplier REAL NOT NULL DEFAULT 1.0",
            "ALTER TABLE tasks ADD COLUMN rollover_policy_version INTEGER",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass

    def _migrate_legacy_balance(self, conn: sqlite3.Connection) -> None:
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        except sqlite3.OperationalError:
            return
        if "balance_credits" not in cols:
            return
        rows = conn.execute(
            "SELECT user_id, balance_credits FROM accounts WHERE balance_credits IS NOT NULL AND balance_credits > 0"
        ).fetchall()
        now = _utc_now()
        for row in rows:
            uid = str(row["user_id"])
            bal = float(row["balance_credits"])
            conn.execute(
                """INSERT INTO balances(account_id, pool_type, amount, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(account_id, pool_type) DO UPDATE SET
                   amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                (uid, POOL_PURCHASED, bal, now),
            )
        try:
            conn.execute("UPDATE accounts SET balance_credits = 0")
        except sqlite3.OperationalError:
            pass

    def _seed_defaults(self, conn: sqlite3.Connection) -> None:
        now = _utc_now()
        if conn.execute("SELECT COUNT(*) AS c FROM pricing_configs").fetchone()["c"] == 0:
            conn.execute(
                """INSERT INTO pricing_configs(status, effective_at, config_json, created_by, reason, created_at)
                   VALUES ('active', ?, ?, 'system', '初始定價', ?)""",
                (now, json.dumps(DEFAULT_PRICING_CONFIG, ensure_ascii=False), now),
            )
        if conn.execute("SELECT COUNT(*) AS c FROM credit_policies").fetchone()["c"] == 0:
            conn.execute(
                """INSERT INTO credit_policies(status, effective_at, monthly_rollover_ratio, rollover_cap,
                   by_tier_json, created_by, reason, created_at)
                   VALUES ('active', ?, ?, ?, ?, 'system', '初始積分政策', ?)""",
                (
                    now,
                    DEFAULT_CREDIT_POLICY["monthly_rollover_ratio"],
                    DEFAULT_CREDIT_POLICY["rollover_cap"],
                    json.dumps(DEFAULT_CREDIT_POLICY.get("by_tier", {}), ensure_ascii=False),
                    now,
                ),
            )
        if conn.execute("SELECT COUNT(*) AS c FROM vendor_configs").fetchone()["c"] == 0:
            conn.execute(
                """INSERT INTO vendor_configs(status, effective_at, config_json, created_by, reason, created_at)
                   VALUES ('active', ?, ?, 'system', '初始廠商配置', ?)""",
                (now, json.dumps(DEFAULT_VENDOR_CONFIGS, ensure_ascii=False), now),
            )

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

    def active_pricing_config(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, config_json FROM pricing_configs
                   WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, "config": DEFAULT_PRICING_CONFIG}
        return {"version": int(row["version"]), "config": json.loads(row["config_json"])}

    def active_credit_policy(self, plan_id: str = "free") -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, monthly_rollover_ratio, rollover_cap, by_tier_json
                   FROM credit_policies WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, **DEFAULT_CREDIT_POLICY}
        by_tier = json.loads(row["by_tier_json"] or "{}")
        tier = by_tier.get(plan_id, {})
        ratio = float(tier.get("monthly_rollover_ratio", row["monthly_rollover_ratio"]))
        cap = float(tier.get("rollover_cap", row["rollover_cap"]))
        return {"version": int(row["version"]), "monthly_rollover_ratio": ratio, "rollover_cap": cap, "by_tier": by_tier}

    def active_vendor_config(self) -> dict[str, Any]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT version, config_json FROM vendor_configs
                   WHERE status='active' ORDER BY version DESC LIMIT 1"""
            ).fetchone()
        if not row:
            return {"version": 0, "config": DEFAULT_VENDOR_CONFIGS}
        return {"version": int(row["version"]), "config": json.loads(row["config_json"])}

    def snapshot_pricing(self, plan_id: str = "free") -> dict[str, Any]:
        pc = self.active_pricing_config()
        cp = self.active_credit_policy(plan_id)
        vc = self.active_vendor_config()
        merged = dict(pc["config"])
        merged["vendor_configs"] = vc["config"]
        return {
            "pricing_config_version": pc["version"],
            "credit_policy_version": cp["version"],
            "rollover_policy_version": cp["version"],
            "vendor_config_version": vc["version"],
            "pricing_config": merged,
            "credit_policy": cp,
        }

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
        entry_id = f"led_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
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
        total_after = self.total_spendable(account_id)
        self.append_ledger(
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
        total = self.total_spendable(account_id)
        self.append_ledger(
            account_id,
            "credit",
            amount,
            total,
            pool_type=pool_type,
            source=source,
            description=description or f"入帳 {amount:.4f}",
            task_id=task_id,
        )

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

    def _policy_for_plan(self, conn: sqlite3.Connection, plan_id: str) -> dict[str, Any]:
        row = conn.execute(
            """SELECT version, monthly_rollover_ratio, rollover_cap, by_tier_json
               FROM credit_policies WHERE status='active' ORDER BY version DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return {"version": 0, **DEFAULT_CREDIT_POLICY}
        by_tier = json.loads(row["by_tier_json"] or "{}")
        tier = by_tier.get(plan_id, {})
        return {
            "version": int(row["version"]),
            "monthly_rollover_ratio": float(tier.get("monthly_rollover_ratio", row["monthly_rollover_ratio"])),
            "rollover_cap": float(tier.get("rollover_cap", row["rollover_cap"])),
        }

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

    def create_lock_installment(
        self,
        account_id: str,
        *,
        total: float,
        per_installment: float,
        lock_days: int,
        lock_multiplier: float,
    ) -> str:
        iid = f"ins_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO lock_installments(installment_id, account_id, total_amount, per_installment,
                   paid_installments, lock_days, lock_multiplier, status, next_due_at, created_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?, 'active', ?, ?)""",
                (iid, account_id, total, per_installment, lock_days, lock_multiplier, now, now),
            )
        return iid

    def list_lock_installments(self, account_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM lock_installments WHERE account_id=? ORDER BY created_at DESC",
                (account_id.strip(),),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["progress_zh"] = f"已解鎖 {d['paid_installments']}/3 期"
            out.append(d)
        return out

    def process_lock_installments(self, account_id: str | None = None) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        now = _utc_now()
        with self._conn() as conn:
            q = "SELECT * FROM lock_installments WHERE status='active' AND paid_installments < 3"
            params: tuple = ()
            if account_id:
                q += " AND account_id=?"
                params = (account_id.strip(),)
            rows = conn.execute(q, params).fetchall()
            for row in rows:
                aid = row["account_id"]
                pay = float(row["per_installment"])
                if not self.atomic_debit_pool(conn, aid, POOL_CONTRIBUTION_LOCKED, pay, now):
                    continue
                conn.execute(
                    """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
                       ON CONFLICT(account_id, pool_type) DO UPDATE SET
                       amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                    (aid, POOL_PURCHASED, pay, now),
                )
                paid = int(row["paid_installments"]) + 1
                status = "completed" if paid >= 3 else "active"
                conn.execute(
                    "UPDATE lock_installments SET paid_installments=?, status=?, next_due_at=? WHERE installment_id=?",
                    (paid, status, now, row["installment_id"]),
                )
                results.append({"installment_id": row["installment_id"], "paid": pay, "installment": paid})
        return results

    def record_cache_savings(self, account_id: str, cache_read_tokens: int, savings_credits: float, l3_hit: bool = False) -> None:
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO cache_stats(account_id, l3_hits, cache_read_tokens, savings_credits, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (account_id, 1 if l3_hit else 0, cache_read_tokens, savings_credits, now),
            )

    def cache_stats_summary(self, account_id: str | None = None) -> dict[str, Any]:
        with self._conn() as conn:
            if account_id:
                row = conn.execute(
                    """SELECT COALESCE(SUM(l3_hits),0) AS l3_hits,
                       COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
                       COALESCE(SUM(savings_credits),0) AS savings
                       FROM cache_stats WHERE account_id=?""",
                    (account_id.strip(),),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COALESCE(SUM(l3_hits),0) AS l3_hits,
                       COALESCE(SUM(cache_read_tokens),0) AS cache_read_tokens,
                       COALESCE(SUM(savings_credits),0) AS savings FROM cache_stats"""
                ).fetchone()
        return {
            "l3_hits": int(row["l3_hits"]),
            "cache_read_tokens": int(row["cache_read_tokens"]),
            "savings_credits": float(row["savings"]),
        }

    def ensure_contributor(self, account_id: str) -> str:
        cid = f"ctr_{account_id[:16]}"
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO contributors(contributor_id, account_id, status, created_at)
                   VALUES (?, ?, 'active', ?)""",
                (cid, account_id.strip(), now),
            )
        return cid

    def bind_contributor_key(self, account_id: str, encrypted_key: str, limits: dict | None = None) -> dict[str, Any]:
        import json

        cid = self.ensure_contributor(account_id)
        kid = f"key_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO api_keys(key_id, contributor_id, encrypted_key, limits_json, status, created_at)
                   VALUES (?, ?, ?, ?, 'active', ?)""",
                (kid, cid, encrypted_key, json.dumps(limits or {}, ensure_ascii=False), now),
            )
        return {"contributor_id": cid, "key_id": kid, "status": "active"}

    def contributor_earnings(self, account_id: str) -> dict[str, Any]:
        bals = self.get_balances(account_id)
        with self._conn() as conn:
            keys = conn.execute(
                """SELECT key_id, status, created_at FROM api_keys
                   WHERE contributor_id IN (SELECT contributor_id FROM contributors WHERE account_id=?)""",
                (account_id.strip(),),
            ).fetchall()
        return {
            "contributor_id": f"ctr_{account_id[:16]}",
            "unlocked_earnings": float(bals.get(POOL_CONTRIBUTION_UNLOCKED, 0)),
            "locked_earnings": float(bals.get(POOL_CONTRIBUTION_LOCKED, 0)),
            "keys": [dict(k) for k in keys],
        }

    def pools_detail(self, account_id: str, plan_id: str = "free") -> dict[str, Any]:
        policy = self.active_credit_policy(plan_id)
        return {
            "balances": self.get_balances(account_id),
            "spendable": self.total_spendable(account_id),
            "grants": self.list_grants(account_id),
            "rollover_records": self.list_rollover_for_account(account_id),
            "rollover_notice_zh": (
                f"月贈送積分將於每月初按 {int(policy['monthly_rollover_ratio']*100)}% 滾入已購買池，"
                f"上限 {policy['rollover_cap']:.0f}，剩餘作廢"
            ),
            "rollover_policy_version": policy["version"],
            "cache_stats": self.cache_stats_summary(account_id),
        }

    def list_pool_ledger(self, account_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM pool_ledger WHERE account_id=? ORDER BY created_at DESC LIMIT ?",
                (account_id.strip(), max(1, min(limit, 200))),
            ).fetchall()
        out = []
        for r in rows:
            meta = {}
            try:
                meta = json.loads(r["meta_json"] or "{}")
            except json.JSONDecodeError:
                pass
            out.append(
                {
                    "id": r["entry_id"],
                    "amount_credits": float(r["amount"]),
                    "balance_after_credits": float(r["balance_after"]),
                    "kind": "credit" if float(r["amount"]) >= 0 else "debit",
                    "source": r["source"],
                    "reference": r["description"],
                    "pool_type": r["pool_type"],
                    "meta": meta,
                    "created_at": r["created_at"],
                }
            )
        return out


_pool_store: PoolStore | None = None


def get_pool_store() -> PoolStore:
    global _pool_store
    if _pool_store is None:
        _pool_store = PoolStore()
    return _pool_store


def reset_pool_store(store: PoolStore | None = None) -> None:
    global _pool_store
    _pool_store = store
