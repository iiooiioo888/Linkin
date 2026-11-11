"""PoolStore 的鎖倉分期、沒收、提早解鎖與貢獻 decay（自 backend.billing.pool_store 抽出）。"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.billing.pool_types import (
    CONTRIBUTION_UNLOCKED_DECAY,
    CONTRIBUTION_UNLOCKED_HALF_LIFE_MONTHS,
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_PURCHASED,
)

from .misc import _MiscMixin
from .schema import (
    EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO,
    KEY_FAILURE_APPEAL_WINDOW_DAYS,
    _installment_interval_days,
    _installment_reward_per_period,
    _installment_reward_total,
    _parse_iso,
    _utc_now,
)


class _InstallmentsMixin(_MiscMixin):
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
                else:
                    # 第一次看到這筆餘額：只記起算點，不當場扣 20%。
                    conn.execute(
                        """INSERT INTO contribution_decay_log(account_id, last_decay_at) VALUES (?, ?)
                           ON CONFLICT(account_id) DO UPDATE SET last_decay_at=excluded.last_decay_at""",
                        (aid, now),
                    )
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
