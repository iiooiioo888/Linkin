"""PoolStore 的 schema／連線／migration／seed 與時間 helper（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from backend.billing.pool_types import POOL_PURCHASED
from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS

from .schema_sql import _POOL_SCHEMA

_DB_LOCK = threading.RLock()
# 套件化後多一層目錄：parents[2] 仍指向 backend/，維持原 backend/data/billing.sqlite3。
_DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "billing.sqlite3"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _month_key(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    return d.strftime("%Y-%m")


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _installment_interval_days(lock_days: int) -> int:
    return max(1, lock_days // 3)


def _installment_reward_total(total_amount: float, lock_multiplier: float) -> float:
    return round(total_amount * max(0.0, lock_multiplier - 1.0), 4)


def _installment_reward_per_period(total_amount: float, lock_multiplier: float) -> float:
    return round(_installment_reward_total(total_amount, lock_multiplier) / 3.0, 4)


EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO = 0.05
KEY_FAILURE_APPEAL_WINDOW_DAYS = 30


class _SchemaMixin:
    db_path: str

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
