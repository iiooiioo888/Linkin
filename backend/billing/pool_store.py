"""多池積分持久層 — balances / grants / pricing / tasks / ledger（account_id = user_id）。"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from backend.billing.plans import get_plan
from backend.billing.pool_types import (
    CONTRIBUTION_UNLOCKED_DECAY,
    CONTRIBUTION_UNLOCKED_HALF_LIFE_MONTHS,
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_LOCKED,
    POOL_MONTHLY_GRANT,
    POOL_PURCHASED,
    SPEND_ORDER,
)
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS
from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG

_DB_LOCK = threading.RLock()
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

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    email TEXT,
    display_name TEXT,
    kyc_status TEXT NOT NULL DEFAULT 'none',
    kyc_level INTEGER NOT NULL DEFAULT 0,
    kyc_meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_health (
    key_id TEXT PRIMARY KEY,
    contributor_id TEXT,
    health_score REAL NOT NULL DEFAULT 1.0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_failure_at TEXT,
    last_failure_reason TEXT,
    balance_exhausted_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'healthy',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subtasks (
    subtask_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    parent_subtask_id TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    estimate_credits REAL NOT NULL DEFAULT 0,
    settled_credits REAL NOT NULL DEFAULT 0,
    key_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_prefixes (
    prefix_id TEXT PRIMARY KEY,
    account_id TEXT,
    key_id TEXT,
    prefix_hash TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 0,
    savings_credits REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_cache_profile (
    key_id TEXT PRIMARY KEY,
    cache_prefix_count INTEGER NOT NULL DEFAULT 0,
    total_hits INTEGER NOT NULL DEFAULT 0,
    affinity_score REAL NOT NULL DEFAULT 0,
    profile_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount REAL NOT NULL,
    reason TEXT NOT NULL,
    account_id TEXT,
    task_id TEXT,
    installment_id TEXT,
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
    key_id TEXT,
    interval_days INTEGER NOT NULL DEFAULT 30,
    forfeited_amount REAL NOT NULL DEFAULT 0,
    failure_reason TEXT,
    appeal_deadline TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contribution_decay_log (
    account_id TEXT PRIMARY KEY,
    last_decay_at TEXT NOT NULL
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
CREATE INDEX IF NOT EXISTS idx_subtasks_task ON subtasks(task_id);
CREATE INDEX IF NOT EXISTS idx_cache_prefixes_key ON cache_prefixes(key_id);
CREATE INDEX IF NOT EXISTS idx_lock_installments_account ON lock_installments(account_id, status);

CREATE TABLE IF NOT EXISTS fault_pool_ledger (
    entry_id TEXT PRIMARY KEY,
    entry_type TEXT NOT NULL,
    amount REAL NOT NULL,
    balance_after REAL NOT NULL,
    reason TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    account_id TEXT,
    task_id TEXT,
    installment_id TEXT,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fault_pool_alerts (
    alert_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    message_zh TEXT NOT NULL,
    balance REAL NOT NULL DEFAULT 0,
    acknowledged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_runtime (
    key TEXT PRIMARY KEY,
    value_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS routing_decisions (
    decision_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    account_id TEXT,
    routing_mode TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_key_splits (
    task_id TEXT PRIMARY KEY,
    split_mode TEXT NOT NULL,
    keys_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS key_daily_usage (
    key_id TEXT NOT NULL,
    day_key TEXT NOT NULL,
    tokens_used INTEGER NOT NULL DEFAULT 0,
    credits_used REAL NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (key_id, day_key)
);

CREATE INDEX IF NOT EXISTS idx_routing_decisions_task ON routing_decisions(task_id);
CREATE INDEX IF NOT EXISTS idx_fault_pool_ledger_created ON fault_pool_ledger(created_at);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _month_key(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y-%m")


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _installment_interval_days(lock_days: int) -> int:
    return max(1, lock_days // 3)


def _installment_reward_total(total_amount: float, lock_multiplier: float) -> float:
    return round(total_amount * max(0.0, lock_multiplier - 1.0), 4)


def _installment_reward_per_period(total_amount: float, lock_multiplier: float) -> float:
    return round(_installment_reward_total(total_amount, lock_multiplier) / 3.0, 4)


EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO = 0.05
KEY_FAILURE_APPEAL_WINDOW_DAYS = 30


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
            "ALTER TABLE lock_installments ADD COLUMN key_id TEXT",
            "ALTER TABLE lock_installments ADD COLUMN interval_days INTEGER NOT NULL DEFAULT 30",
            "ALTER TABLE lock_installments ADD COLUMN forfeited_amount REAL NOT NULL DEFAULT 0",
            "ALTER TABLE lock_installments ADD COLUMN failure_reason TEXT",
            "ALTER TABLE lock_installments ADD COLUMN appeal_deadline TEXT",
            "ALTER TABLE billing_appeals ADD COLUMN appeal_kind TEXT NOT NULL DEFAULT 'general'",
            "ALTER TABLE billing_appeals ADD COLUMN installment_id TEXT",
            "ALTER TABLE billing_appeals ADD COLUMN forfeiture_amount REAL",
            "ALTER TABLE billing_appeals ADD COLUMN appeal_deadline TEXT",
            "ALTER TABLE fault_pool ADD COLUMN account_id TEXT",
            "ALTER TABLE fault_pool ADD COLUMN installment_id TEXT",
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

    def ensure_user_profile(self, account_id: str, *, email: str | None = None, display_name: str | None = None) -> None:
        """同步 users 表（KYC stub）；account_id 與 accounts.user_id 對應。"""
        now = _utc_now()
        aid = account_id.strip()
        with self._conn() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO users(user_id, email, display_name, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (aid, email, display_name, now, now),
            )
            if email or display_name:
                conn.execute(
                    """UPDATE users SET email=COALESCE(?, email), display_name=COALESCE(?, display_name),
                       updated_at=? WHERE user_id=?""",
                    (email, display_name, now, aid),
                )

    def record_key_health_event(
        self,
        key_id: str,
        *,
        event: str,
        contributor_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """記錄 Key 健康事件；區分 key_failure 與 balance_exhausted。"""
        now = _utc_now()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM key_health WHERE key_id=?", (key_id,)).fetchone()
            if row:
                failure_count = int(row["failure_count"])
                balance_exhausted_count = int(row["balance_exhausted_count"])
                health_score = float(row["health_score"])
            else:
                failure_count = 0
                balance_exhausted_count = 0
                health_score = 1.0
            if event == "key_failure":
                failure_count += 1
                health_score = max(0.0, health_score - 0.15)
                status = "degraded" if health_score >= 0.5 else "unhealthy"
                last_failure_reason = reason or "key_failure"
            elif event == "balance_exhausted":
                balance_exhausted_count += 1
                status = "healthy"
                last_failure_reason = reason or "balance_exhausted"
            else:
                status = "healthy"
                last_failure_reason = reason
            conn.execute(
                """INSERT INTO key_health(key_id, contributor_id, health_score, failure_count,
                   last_failure_at, last_failure_reason, balance_exhausted_count, status, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(key_id) DO UPDATE SET
                   contributor_id=COALESCE(excluded.contributor_id, key_health.contributor_id),
                   health_score=excluded.health_score,
                   failure_count=excluded.failure_count,
                   last_failure_at=excluded.last_failure_at,
                   last_failure_reason=excluded.last_failure_reason,
                   balance_exhausted_count=excluded.balance_exhausted_count,
                   status=excluded.status,
                   updated_at=excluded.updated_at""",
                (
                    key_id,
                    contributor_id,
                    health_score,
                    failure_count,
                    now if event == "key_failure" else None,
                    last_failure_reason,
                    balance_exhausted_count,
                    status,
                    now,
                ),
            )
        return {
            "key_id": key_id,
            "event": event,
            "failure_count": failure_count,
            "balance_exhausted_count": balance_exhausted_count,
            "health_score": health_score,
            "status": status,
        }

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

    def record_cache_prefix_hit(
        self,
        *,
        key_id: str,
        prefix_hash: str,
        account_id: str | None = None,
        savings_credits: float = 0,
    ) -> str:
        prefix_id = f"cpf_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT prefix_id, hit_count, savings_credits FROM cache_prefixes WHERE key_id=? AND prefix_hash=?",
                (key_id, prefix_hash),
            ).fetchone()
            if existing:
                prefix_id = str(existing["prefix_id"])
                conn.execute(
                    """UPDATE cache_prefixes SET hit_count=hit_count+1,
                       savings_credits=savings_credits+?, updated_at=? WHERE prefix_id=?""",
                    (savings_credits, now, prefix_id),
                )
            else:
                conn.execute(
                    """INSERT INTO cache_prefixes(prefix_id, account_id, key_id, prefix_hash,
                       hit_count, savings_credits, created_at, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?, ?, ?)""",
                    (prefix_id, account_id, key_id, prefix_hash, savings_credits, now, now),
                )
            profile = conn.execute(
                "SELECT cache_prefix_count, total_hits FROM key_cache_profile WHERE key_id=?",
                (key_id,),
            ).fetchone()
            if profile:
                conn.execute(
                    """UPDATE key_cache_profile SET total_hits=total_hits+1,
                       affinity_score=MIN(1.0, affinity_score + 0.01), updated_at=? WHERE key_id=?""",
                    (now, key_id),
                )
            else:
                conn.execute(
                    """INSERT INTO key_cache_profile(key_id, cache_prefix_count, total_hits,
                       affinity_score, profile_json, updated_at)
                       VALUES (?, 1, 1, 0.1, '{}', ?)""",
                    (key_id, now),
                )
            prefix_count = conn.execute(
                "SELECT COUNT(*) AS c FROM cache_prefixes WHERE key_id=?", (key_id,)
            ).fetchone()["c"]
            conn.execute(
                "UPDATE key_cache_profile SET cache_prefix_count=? WHERE key_id=?",
                (int(prefix_count), key_id),
            )
        return prefix_id

    def record_fault_pool(
        self,
        amount: float,
        reason: str,
        *,
        account_id: str | None = None,
        task_id: str | None = None,
        installment_id: str | None = None,
    ) -> None:
        if amount <= 0:
            return
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool(amount, reason, account_id, task_id, installment_id, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (amount, reason, account_id, task_id, installment_id, _utc_now()),
            )
        self.fault_pool_credit(
            amount,
            reason,
            account_id=account_id,
            task_id=task_id,
            installment_id=installment_id,
            source="legacy_inflow",
        )

    def fault_pool_balance(self) -> float:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COALESCE(SUM(CASE WHEN entry_type='credit' THEN amount ELSE -amount END), 0) AS bal
                   FROM fault_pool_ledger"""
            ).fetchone()
        if row and row["bal"] is not None:
            return round(float(row["bal"]), 4)
        with self._conn() as conn:
            legacy = conn.execute("SELECT COALESCE(SUM(amount), 0) AS t FROM fault_pool").fetchone()
        return round(float(legacy["t"] or 0), 4)

    def fault_pool_credit(
        self,
        amount: float,
        reason: str,
        *,
        account_id: str | None = None,
        task_id: str | None = None,
        installment_id: str | None = None,
        source: str = "platform_take",
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if amount <= 0:
            return {"entry_id": None, "amount": 0.0, "balance_after": self.fault_pool_balance()}
        entry_id = f"fp_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        balance_after = round(self.fault_pool_balance() + amount, 4)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool_ledger(entry_id, entry_type, amount, balance_after, reason, source,
                   account_id, task_id, installment_id, meta_json, created_at)
                   VALUES (?, 'credit', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    amount,
                    balance_after,
                    reason,
                    source,
                    account_id,
                    task_id,
                    installment_id,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                ),
            )
        return {"entry_id": entry_id, "amount": amount, "balance_after": balance_after, "entry_type": "credit"}

    def fault_pool_debit(
        self,
        amount: float,
        reason: str,
        *,
        account_id: str | None = None,
        task_id: str | None = None,
        installment_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if amount <= 0:
            return {"entry_id": None, "amount": 0.0, "disbursed": 0.0, "balance_after": self.fault_pool_balance()}
        balance = self.fault_pool_balance()
        disbursed = min(amount, balance)
        if disbursed <= 0:
            return {"entry_id": None, "amount": amount, "disbursed": 0.0, "balance_after": balance, "shortfall": amount}
        entry_id = f"fp_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        balance_after = round(balance - disbursed, 4)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool_ledger(entry_id, entry_type, amount, balance_after, reason, source,
                   account_id, task_id, installment_id, meta_json, created_at)
                   VALUES (?, 'debit', ?, ?, ?, 'disbursement', ?, ?, ?, ?, ?)""",
                (
                    entry_id,
                    disbursed,
                    balance_after,
                    reason,
                    account_id,
                    task_id,
                    installment_id,
                    json.dumps(meta or {}, ensure_ascii=False),
                    now,
                ),
            )
        return {
            "entry_id": entry_id,
            "amount": amount,
            "disbursed": disbursed,
            "balance_after": balance_after,
            "shortfall": round(amount - disbursed, 4),
            "entry_type": "debit",
        }

    def list_fault_pool_ledger(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM fault_pool_ledger ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 200)),)
            ).fetchall()
        return [dict(r) for r in rows]

    def fault_pool_summary_by_reason(self) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT reason, entry_type,
                   SUM(amount) AS total, COUNT(*) AS entries
                   FROM fault_pool_ledger GROUP BY reason, entry_type ORDER BY total DESC"""
            ).fetchall()
        return [dict(r) for r in rows]

    def record_fault_pool_alert(self, *, kind: str, message_zh: str, balance: float) -> str:
        alert_id = f"fpa_{uuid.uuid4().hex[:10]}"
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool_alerts(alert_id, kind, message_zh, balance, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (alert_id, kind, message_zh, balance, _utc_now()),
            )
        return alert_id

    def list_fault_pool_alerts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM fault_pool_alerts ORDER BY created_at DESC LIMIT ?", (max(1, min(limit, 100)),)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_routing_runtime(self, key: str, default: Any = None) -> Any:
        with self._conn() as conn:
            row = conn.execute("SELECT value_json FROM routing_runtime WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except json.JSONDecodeError:
            return default

    def set_routing_runtime(self, key: str, value: Any) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO routing_runtime(key, value_json, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at""",
                (key, json.dumps(value, ensure_ascii=False), _utc_now()),
            )

    def log_routing_decision(self, decision: dict[str, Any]) -> str:
        decision_id = f"rd_{uuid.uuid4().hex[:12]}"
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO routing_decisions(decision_id, task_id, account_id, routing_mode, decision_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    decision_id,
                    decision.get("task_id", ""),
                    decision.get("account_id"),
                    decision.get("routing_mode", "single"),
                    json.dumps(decision, ensure_ascii=False),
                    _utc_now(),
                ),
            )
        return decision_id

    def get_routing_decision(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM routing_decisions WHERE task_id=? ORDER BY created_at DESC LIMIT 1",
                (task_id,),
            ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["decision_json"])
        except json.JSONDecodeError:
            payload = {}
        return {"decision_id": row["decision_id"], **payload, "created_at": row["created_at"]}

    def save_task_key_split(self, task_id: str, keys: list[dict[str, Any]], *, split_mode: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO task_key_splits(task_id, split_mode, keys_json, created_at)
                   VALUES (?, ?, ?, ?)""",
                (task_id, split_mode, json.dumps(keys, ensure_ascii=False), _utc_now()),
            )

    def get_key_daily_usage(self, key_id: str, day_key: str | None = None) -> float:
        dk = day_key or datetime.now(timezone.utc).strftime("%Y%m%d")
        with self._conn() as conn:
            row = conn.execute(
                "SELECT tokens_used FROM key_daily_usage WHERE key_id=? AND day_key=?",
                (key_id, dk),
            ).fetchone()
        return float(row["tokens_used"]) if row else 0.0

    def increment_key_usage(self, key_id: str, *, tokens: int = 0, credits: float = 0) -> None:
        dk = datetime.now(timezone.utc).strftime("%Y%m%d")
        now = _utc_now()
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO key_daily_usage(key_id, day_key, tokens_used, credits_used, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(key_id, day_key) DO UPDATE SET
                   tokens_used = key_daily_usage.tokens_used + excluded.tokens_used,
                   credits_used = key_daily_usage.credits_used + excluded.credits_used,
                   updated_at = excluded.updated_at""",
                (key_id, dk, tokens, credits, now),
            )

    def get_key_concurrency(self, key_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS c FROM task_key_binding tkb
                   JOIN tasks t ON t.task_id = tkb.task_id
                   WHERE tkb.key_id=? AND t.status IN ('pending', 'running', 'active')""",
                (key_id,),
            ).fetchone()
        return int(row["c"] or 0) if row else 0

    def list_contributor_keys_with_health(self, account_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ak.key_id, ak.status, ak.limits_json, ak.org_id, ak.created_at,
                          kh.health_score, kh.status AS health_status, kh.failure_count,
                          kh.balance_exhausted_count, kh.last_failure_reason, kh.updated_at AS health_updated_at
                   FROM api_keys ak
                   JOIN contributors c ON c.contributor_id = ak.contributor_id
                   LEFT JOIN key_health kh ON kh.key_id = ak.key_id
                   WHERE c.account_id=? ORDER BY ak.created_at DESC""",
                (account_id.strip(),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            item = dict(r)
            try:
                item["limits"] = json.loads(r["limits_json"] or "{}")
            except json.JSONDecodeError:
                item["limits"] = {}
            item.pop("limits_json", None)
            item["daily_usage"] = self.get_key_daily_usage(str(r["key_id"]))
            out.append(item)
        return out

    def _primary_contributor_key(self, account_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT ak.key_id FROM api_keys ak
                   JOIN contributors c ON c.contributor_id = ak.contributor_id
                   WHERE c.account_id=? AND ak.status='active'
                   ORDER BY ak.created_at DESC LIMIT 1""",
                (account_id.strip(),),
            ).fetchone()
        return str(row["key_id"]) if row else None

    def create_lock_installment(
        self,
        account_id: str,
        *,
        total: float,
        per_installment: float,
        lock_days: int,
        lock_multiplier: float,
        key_id: str | None = None,
    ) -> str:
        iid = f"ins_{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        now = now_dt.isoformat()
        interval = _installment_interval_days(lock_days)
        first_due = (now_dt + timedelta(days=interval)).isoformat()
        bound_key = key_id or self._primary_contributor_key(account_id)
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO lock_installments(installment_id, account_id, total_amount, per_installment,
                   paid_installments, lock_days, lock_multiplier, status, next_due_at, key_id, interval_days,
                   forfeited_amount, created_at)
                   VALUES (?, ?, ?, ?, 0, ?, ?, 'active', ?, ?, ?, 0, ?)""",
                (
                    iid,
                    account_id,
                    total,
                    per_installment,
                    lock_days,
                    lock_multiplier,
                    first_due,
                    bound_key,
                    interval,
                    now,
                ),
            )
        return iid

    def _installment_row_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        paid = int(d.get("paid_installments") or 0)
        total = float(d["total_amount"])
        mult = float(d["lock_multiplier"])
        reward_total = _installment_reward_total(total, mult)
        reward_paid = round(reward_total * paid / 3.0, 4)
        remaining = max(0, 3 - paid)
        d["reward_total"] = reward_total
        d["reward_paid"] = reward_paid
        d["reward_remaining"] = round(reward_total - reward_paid, 4)
        principal_paid = round(float(d["per_installment"]) * paid, 4)
        d["principal_remaining"] = round(max(0.0, total - principal_paid), 4)
        d["progress_zh"] = f"已解鎖 {paid}/3 期"
        if d.get("next_due_at"):
            d["schedule_zh"] = f"下期 {d['next_due_at'][:10]}（每 {d.get('interval_days', 30)} 天）"
        return d

    def get_lock_installment(self, installment_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM lock_installments WHERE installment_id=?", (installment_id,)).fetchone()
        return self._installment_row_dict(row) if row else None

    def list_lock_installments(self, account_id: str) -> list[dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM lock_installments WHERE account_id=? ORDER BY created_at DESC",
                (account_id.strip(),),
            ).fetchall()
        return [self._installment_row_dict(r) for r in rows]

    def _pay_installment_period(self, conn: sqlite3.Connection, row: sqlite3.Row, now: str) -> dict[str, Any] | None:
        aid = row["account_id"]
        paid = int(row["paid_installments"])
        total = float(row["total_amount"])
        mult = float(row["lock_multiplier"])
        per = float(row["per_installment"])
        remaining_periods = max(1, 3 - paid)
        principal = per if remaining_periods > 1 else round(total - per * paid, 4)
        reward_total = _installment_reward_total(total, mult)
        reward_paid = round(reward_total * paid / 3.0, 4)
        reward = round(reward_total - reward_paid, 4) if remaining_periods == 1 else _installment_reward_per_period(total, mult)
        total_pay = round(principal + reward, 4)
        if not self.atomic_debit_pool(conn, aid, POOL_CONTRIBUTION_LOCKED, principal, now):
            return None
        conn.execute(
            """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(account_id, pool_type) DO UPDATE SET
               amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
            (aid, POOL_PURCHASED, total_pay, now),
        )
        paid = paid + 1
        status = "completed" if paid >= 3 else "active"
        interval = int(row["interval_days"] or _installment_interval_days(int(row["lock_days"])))
        next_due = None if status == "completed" else (
            _parse_iso(now) + timedelta(days=interval)
        ).replace(microsecond=0).isoformat()
        conn.execute(
            """UPDATE lock_installments SET paid_installments=?, status=?, next_due_at=?
               WHERE installment_id=?""",
            (paid, status, next_due, row["installment_id"]),
        )
        return {
            "installment_id": row["installment_id"],
            "account_id": str(aid),
            "principal_paid": principal,
            "reward_paid": reward,
            "total_paid": total_pay,
            "installment": paid,
            "status": status,
            "reward_pending_fault_pool": reward,
        }

    def process_lock_installments(
        self,
        account_id: str | None = None,
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        """處理到期分期（3 期）；force=True 時忽略到期時間（手動觸發）。"""
        results: list[dict[str, Any]] = []
        now = _utc_now()
        now_dt = _parse_iso(now)
        with self._conn() as conn:
            q = "SELECT * FROM lock_installments WHERE status='active' AND paid_installments < 3"
            params: list[Any] = []
            if account_id:
                q += " AND account_id=?"
                params.append(account_id.strip())
            rows = conn.execute(q, tuple(params)).fetchall()
            for row in rows:
                if not force:
                    due_at = row["next_due_at"]
                    if due_at and _parse_iso(str(due_at)) > now_dt:
                        continue
                paid = self._pay_installment_period(conn, row, now)
                if paid:
                    results.append(paid)
        for paid in results:
            pending = float(paid.pop("reward_pending_fault_pool", 0) or 0)
            if pending > 0:
                from backend.billing.fault_pool import disburse_for_lock_reward

                paid["fault_pool_reward"] = disburse_for_lock_reward(
                    pending,
                    account_id=str(paid.get("account_id", "")),
                    installment_id=str(paid.get("installment_id", "")),
                )
        return results

    def _unpaid_installment_amounts(self, row: sqlite3.Row) -> tuple[float, float, float]:
        paid = int(row["paid_installments"])
        total = float(row["total_amount"])
        mult = float(row["lock_multiplier"])
        per = float(row["per_installment"])
        principal_paid = round(per * paid, 4)
        principal = round(max(0.0, total - principal_paid), 4)
        reward_total = _installment_reward_total(total, mult)
        reward_paid = round(reward_total * paid / 3.0, 4)
        reward = round(max(0.0, reward_total - reward_paid), 4)
        return principal, reward, round(principal + reward, 4)

    def forfeit_installment_key_failure(
        self,
        installment_id: str,
        *,
        task_id: str | None = None,
        key_id: str | None = None,
    ) -> dict[str, Any]:
        """Key 故障：僅沒收未付分期（已付保留）；開啟 30 天申訴窗口。"""
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        now = now_dt.isoformat()
        appeal_deadline = (now_dt + timedelta(days=KEY_FAILURE_APPEAL_WINDOW_DAYS)).isoformat()
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM lock_installments WHERE installment_id=?", (installment_id,)).fetchone()
            if not row or row["status"] != "active":
                raise ValueError("分期不存在或已結束")
            unpaid_principal, unpaid_reward, forfeit_total = self._unpaid_installment_amounts(row)
            aid = row["account_id"]
            if unpaid_principal > 0:
                if not self.atomic_debit_pool(conn, aid, POOL_CONTRIBUTION_LOCKED, unpaid_principal, now):
                    locked_row = conn.execute(
                        "SELECT amount FROM balances WHERE account_id=? AND pool_type=?",
                        (aid, POOL_CONTRIBUTION_LOCKED),
                    ).fetchone()
                    avail = float(locked_row["amount"]) if locked_row else 0.0
                    if avail > 0:
                        self.atomic_debit_pool(conn, aid, POOL_CONTRIBUTION_LOCKED, avail, now)
                        forfeit_total = round(avail + unpaid_reward, 4)
            conn.execute(
                """UPDATE lock_installments SET status='forfeited_key_failure', failure_reason='key_failure',
                   forfeited_amount=?, appeal_deadline=?, next_due_at=NULL WHERE installment_id=?""",
                (forfeit_total, appeal_deadline, installment_id),
            )
        self.fault_pool_credit(
            forfeit_total,
            "key_failure_forfeiture",
            account_id=aid,
            task_id=task_id,
            installment_id=installment_id,
            source="lock_penalty",
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool(amount, reason, account_id, task_id, installment_id, created_at)
                   VALUES (?, 'key_failure_forfeiture', ?, ?, ?, ?)""",
                (forfeit_total, aid, task_id, installment_id, now),
            )
        return {
            "installment_id": installment_id,
            "forfeited_amount": forfeit_total,
            "unpaid_principal": unpaid_principal,
            "unpaid_reward": unpaid_reward,
            "appeal_deadline": appeal_deadline,
            "failure_reason": "key_failure",
        }

    def forfeit_installments_for_key_failure(
        self,
        key_id: str,
        *,
        task_id: str | None = None,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT installment_id FROM lock_installments WHERE status='active' AND key_id=?",
                (key_id,),
            ).fetchall()
        for row in rows:
            results.append(
                self.forfeit_installment_key_failure(str(row["installment_id"]), task_id=task_id, key_id=key_id)
            )
        return results

    def early_unlock_installment(self, account_id: str, installment_id: str) -> dict[str, Any]:
        """提前解鎖：沒收全部未付獎勵 + 5% 本金 → fault_pool；剩餘本金退回未鎖池。"""
        now = _utc_now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM lock_installments WHERE installment_id=? AND account_id=?",
                (installment_id, account_id.strip()),
            ).fetchone()
            if not row or row["status"] != "active":
                raise ValueError("分期不存在或不可提前解鎖")
            unpaid_principal, unpaid_reward, _ = self._unpaid_installment_amounts(row)
            penalty = round(float(row["total_amount"]) * EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO, 4)
            forfeit = round(unpaid_reward + penalty, 4)
            return_principal = round(max(0.0, unpaid_principal - penalty), 4)
            if unpaid_principal > 0:
                if not self.atomic_debit_pool(conn, account_id, POOL_CONTRIBUTION_LOCKED, unpaid_principal, now):
                    raise ValueError("鎖倉餘額不足")
            if return_principal > 0:
                conn.execute(
                    """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
                       ON CONFLICT(account_id, pool_type) DO UPDATE SET
                       amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                    (account_id, POOL_CONTRIBUTION_UNLOCKED, return_principal, now),
                )
            conn.execute(
                """UPDATE lock_installments SET status='early_unlocked', failure_reason='early_unlock',
                   forfeited_amount=?, next_due_at=NULL WHERE installment_id=?""",
                (forfeit, installment_id),
            )
        self.fault_pool_credit(
            forfeit,
            "early_unlock_penalty",
            account_id=account_id,
            installment_id=installment_id,
            source="lock_penalty",
        )
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO fault_pool(amount, reason, account_id, installment_id, created_at)
                   VALUES (?, 'early_unlock_penalty', ?, ?, ?)""",
                (forfeit, account_id, installment_id, now),
            )
        return {
            "installment_id": installment_id,
            "forfeited_amount": forfeit,
            "returned_principal": return_principal,
            "penalty_principal": penalty,
            "forfeited_reward": unpaid_reward,
        }

    def run_contribution_decay(self) -> list[dict[str, Any]]:
        """未鎖定貢獻積分半衰期：每 3 個月 ×0.8。"""
        results: list[dict[str, Any]] = []
        now_dt = datetime.now(timezone.utc).replace(microsecond=0)
        now = now_dt.isoformat()
        cutoff = now_dt - timedelta(days=CONTRIBUTION_UNLOCKED_HALF_LIFE_MONTHS * 30)
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT account_id, amount FROM balances WHERE pool_type=? AND amount > 0",
                (POOL_CONTRIBUTION_UNLOCKED,),
            ).fetchall()
            for row in rows:
                aid = str(row["account_id"])
                amount = float(row["amount"])
                log = conn.execute(
                    "SELECT last_decay_at FROM contribution_decay_log WHERE account_id=?", (aid,)
                ).fetchone()
                if log:
                    last = _parse_iso(str(log["last_decay_at"]))
                    if last > cutoff:
                        continue
                decayed = round(amount * (1.0 - CONTRIBUTION_UNLOCKED_DECAY), 4)
                new_amount = round(amount - decayed, 4)
                conn.execute(
                    "UPDATE balances SET amount=?, updated_at=? WHERE account_id=? AND pool_type=?",
                    (new_amount, now, aid, POOL_CONTRIBUTION_UNLOCKED),
                )
                conn.execute(
                    """INSERT INTO contribution_decay_log(account_id, last_decay_at) VALUES (?, ?)
                       ON CONFLICT(account_id) DO UPDATE SET last_decay_at=excluded.last_decay_at""",
                    (aid, now),
                )
                results.append({"account_id": aid, "before": amount, "decayed": decayed, "after": new_amount})
        return results

    def restore_key_failure_forfeiture(self, installment_id: str, amount: float) -> None:
        """申訴核准後恢復被沒收積分至未鎖池。"""
        if amount <= 0:
            return
        now = _utc_now()
        with self._conn() as conn:
            row = conn.execute(
                "SELECT account_id FROM lock_installments WHERE installment_id=?", (installment_id,)
            ).fetchone()
            if not row:
                raise ValueError("分期不存在")
            aid = str(row["account_id"])
            conn.execute(
                """INSERT INTO balances(account_id, pool_type, amount, updated_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(account_id, pool_type) DO UPDATE SET
                   amount = balances.amount + excluded.amount, updated_at = excluded.updated_at""",
                (aid, POOL_CONTRIBUTION_UNLOCKED, amount, now),
            )

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

    def bind_contributor_key(
        self,
        account_id: str,
        encrypted_key: str,
        limits: dict | None = None,
        *,
        org_id: str | None = None,
        plaintext_key: str | None = None,
    ) -> dict[str, Any]:
        from backend.billing.key_crypto import encrypt_api_key

        cid = self.ensure_contributor(account_id)
        kid = f"key_{uuid.uuid4().hex[:12]}"
        now = _utc_now()
        limits_payload = dict(limits or {})
        if org_id:
            limits_payload.setdefault("org_id", org_id)
        raw = plaintext_key or encrypted_key
        if not raw.startswith("enc1:") and not raw.startswith("enc256:"):
            stored = encrypt_api_key(raw)
        else:
            stored = raw
        resolved_org = org_id or limits_payload.get("org_id")
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO api_keys(key_id, contributor_id, org_id, encrypted_key, limits_json, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'active', ?)""",
                (kid, cid, resolved_org, stored, json.dumps(limits_payload, ensure_ascii=False), now),
            )
            conn.execute(
                """INSERT OR IGNORE INTO key_health(key_id, contributor_id, health_score, status, updated_at)
                   VALUES (?, ?, 1.0, 'healthy', ?)""",
                (kid, cid, now),
            )
        return {
            "contributor_id": cid,
            "key_id": kid,
            "status": "active",
            "org_id": resolved_org,
            "limits": limits_payload,
            "encrypted": True,
        }

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
