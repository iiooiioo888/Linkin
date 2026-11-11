"""PoolStore 的使用者資料、快取、故障池與其餘雜項（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import json
import uuid
from typing import Any

from .keys import _KeysMixin
from .schema import _utc_now


class _MiscMixin(_KeysMixin):
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
