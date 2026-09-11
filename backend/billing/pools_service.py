"""多池積分服務 v6.0 — 預扣分級、結算、貢獻轉換、禁止轉移。"""
from __future__ import annotations

from typing import Any

from backend.billing.errors import InsufficientCreditsError
from backend.billing.pool_store import get_pool_store, _utc_now
from backend.billing.pool_types import (
    CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_PURCHASED,
)
from backend.billing.pricing_engine import compute_cost_credits, estimate_task_reserve


class TransferForbiddenError(Exception):
    def __init__(self) -> None:
        super().__init__("積分不可轉贈、轉移或提現")


class ReserveRejectedError(InsufficientCreditsError):
    """餘額 < 預估 50%，拒絕執行。"""


def evaluate_reserve_tier(available: float, estimate: float) -> str:
    """<50% 拒絕；≥50% 且 <100% 降級；≥100% 正常。"""
    if estimate <= 0:
        return "normal"
    ratio = available / estimate
    if ratio < 0.5:
        return "reject"
    if ratio < 1.0:
        return "degrade"
    return "normal"


class PoolsService:
    @property
    def store(self):
        return get_pool_store()

    def ensure_user(self, user_id: str, plan_id: str = "free") -> str:
        return self.store.ensure_pools(user_id, plan_id)

    def get_wallet_summary(self, user_id: str) -> dict[str, Any]:
        account_id = self.ensure_user(user_id)
        balances = self.store.get_balances(account_id)
        spendable = self.store.total_spendable(account_id)
        pricing = self.store.active_pricing_config()
        policy = self.store.active_credit_policy()
        vendor = self.store.active_vendor_config()
        return {
            "account_id": account_id,
            "balances": balances,
            "spendable_credits": spendable,
            "pricing_config_version": pricing["version"],
            "credit_policy_version": policy["version"],
            "vendor_config_version": vendor["version"],
            "transfer_allowed": False,
        }

    def topup_purchased(self, user_id: str, amount: float, *, source: str = "purchase") -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("充值金額須大於 0")
        account_id = self.ensure_user(user_id)
        self.store.credit_pool(
            account_id, POOL_PURCHASED, amount, source=source, description="購買積分入帳", origin="purchase"
        )
        return self.get_wallet_summary(user_id)

    def transfer(self, *args: Any, **kwargs: Any) -> None:
        raise TransferForbiddenError()

    def share(self, *args: Any, **kwargs: Any) -> None:
        raise TransferForbiddenError()

    def reserve_for_task(
        self,
        user_id: str,
        task_id: str,
        *,
        baseline_tokens: int = 1000,
        iterations: int = 1,
        roles: int = 1,
        model: str = "default",
        lock_multiplier: float = 1.0,
    ) -> dict[str, Any]:
        account_id = self.ensure_user(user_id)
        snapshot = self.store.snapshot_pricing()
        estimate = estimate_task_reserve(
            snapshot["pricing_config"],
            baseline_tokens=baseline_tokens,
            iterations=iterations,
            roles=roles,
            model=model,
        )
        available = self.store.total_spendable(account_id)
        tier = evaluate_reserve_tier(available, estimate)
        if tier == "reject":
            raise ReserveRejectedError(balance_credits=available, required_credits=estimate)
        reserved = estimate if tier == "normal" else available
        run_mode = "normal" if tier == "normal" else "degrade"
        snapshot = {**snapshot, "lock_multiplier": lock_multiplier}
        self.store.create_task_record(
            task_id,
            account_id,
            estimate,
            reserved,
            snapshot,
            run_mode=run_mode,
            lock_multiplier=lock_multiplier,
        )
        breakdown = self.store.spend_from_pools(account_id, reserved, task_id=task_id, source="reserve")
        return {
            "task_id": task_id,
            "reserved_credits": reserved,
            "estimate_credits": estimate,
            "run_mode": run_mode,
            "breakdown": breakdown,
            "pricing_config_version": snapshot["pricing_config_version"],
            "rollover_policy_version": snapshot.get("rollover_policy_version"),
            "lock_multiplier": lock_multiplier,
        }

    def settle_task_usage(
        self,
        task_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        cached_tokens: int = 0,
        model: str = "default",
        role: str = "",
        tool: str = "",
        vendor_id: str | None = None,
        cache_metadata_missing: bool = False,
        l3_cache_hit: bool = False,
        event_type: str = "llm",
        source: str = "call_llm",
        key_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.store.get_task_snapshot(task_id)
        if not snapshot:
            raise ValueError(f"任務 {task_id} 無定價快照")
        config = snapshot.get("pricing_config", {})
        lock_mult = float(snapshot.get("lock_multiplier") or 1.0)
        with self.store._conn() as conn:
            row = conn.execute("SELECT lock_multiplier FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row and row["lock_multiplier"]:
            lock_mult = float(row["lock_multiplier"])
        actual = compute_cost_credits(
            config,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens or cached_tokens,
            cache_write_tokens=cache_write_tokens,
            role=role,
            tool=tool,
            vendor_id=vendor_id,
            cache_metadata_missing=cache_metadata_missing,
            l3_cache_hit=l3_cache_hit,
            lock_multiplier=lock_mult,
        )
        with self.store._conn() as conn:
            row = conn.execute("SELECT account_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"任務 {task_id} 不存在")
        account_id = row["account_id"]
        payload = dict(meta or {})
        payload["lock_multiplier"] = lock_mult
        self.store.record_usage_event(
            account_id=account_id,
            task_id=task_id,
            event_type=event_type,
            source=source,
            tokens=input_tokens + output_tokens,
            cached_tokens=cache_read_tokens or cached_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_credits=actual,
            pricing_version=snapshot.get("pricing_config_version"),
            key_id=key_id,
            meta=payload,
        )
        return {
            "task_id": task_id,
            "cost_credits": actual,
            "pricing_version": snapshot.get("pricing_config_version"),
            "lock_multiplier": lock_mult,
        }

    def finalize_task(self, task_id: str, actual_total: float) -> dict[str, Any]:
        with self.store._conn() as conn:
            row = conn.execute(
                "SELECT account_id, reserved_credits FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        if not row:
            raise ValueError(f"任務 {task_id} 不存在")
        account_id = row["account_id"]
        reserved = float(row["reserved_credits"] or 0)
        delta = reserved - actual_total
        if delta > 0:
            self.store.credit_pool(
                account_id,
                POOL_PURCHASED,
                delta,
                source="reserve_refund",
                description=f"任務 {task_id} 預扣退還",
                task_id=task_id,
                origin="reserve_refund",
            )
        elif delta < 0:
            extra = -delta
            available = self.store.total_spendable(account_id)
            if available < extra:
                raise InsufficientCreditsError(balance_credits=available, required_credits=extra)
            self.store.spend_from_pools(account_id, extra, task_id=task_id, source="settle_extra")
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE tasks SET settled_credits=?, status='settled', updated_at=? WHERE task_id=?",
                (actual_total, _utc_now(), task_id),
            )
        return {"task_id": task_id, "reserved": reserved, "actual": actual_total, "refund": max(delta, 0)}

    def run_rollover(self, month_key: str | None = None) -> list[dict[str, Any]]:
        return self.store.run_monthly_rollover(month_key)

    def convert_contribution_unlocked(self, user_id: str, amount: float) -> dict[str, Any]:
        """未鎖定貢獻積分 1:0.4 轉入 purchased（自動入帳，不過期）。"""
        account_id = self.ensure_user(user_id)
        balances = self.store.get_balances(account_id)
        avail = balances.get(POOL_CONTRIBUTION_UNLOCKED, 0.0)
        if amount > avail:
            raise InsufficientCreditsError(balance_credits=avail, required_credits=amount)
        with self.store._conn() as conn:
            if not self.store.atomic_debit_pool(conn, account_id, POOL_CONTRIBUTION_UNLOCKED, amount, _utc_now()):
                raise InsufficientCreditsError(balance_credits=avail, required_credits=amount)
        purchased = round(amount * CONTRIBUTION_UNLOCKED_CONVERT_RATIO, 4)
        self.store.credit_pool(
            account_id,
            POOL_PURCHASED,
            purchased,
            source="contribution_convert",
            description=f"貢獻積分轉換 1:{CONTRIBUTION_UNLOCKED_CONVERT_RATIO}",
            origin="contribution_unlocked",
        )
        return {"converted": amount, "purchased_credits": purchased, **self.get_wallet_summary(user_id)}


_pools: PoolsService | None = None


def get_pools_service() -> PoolsService:
    global _pools
    if _pools is None:
        _pools = PoolsService()
    return _pools


def reset_pools_service(service: PoolsService | None = None) -> None:
    global _pools
    _pools = service
