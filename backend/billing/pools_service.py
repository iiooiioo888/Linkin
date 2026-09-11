"""多池積分服務 — 預扣、結算、充值、禁止轉移。"""
from __future__ import annotations

from typing import Any

from backend.billing.errors import InsufficientCreditsError
from backend.billing.pool_store import get_pool_store, _utc_now
from backend.billing.pool_types import POOL_CONTRIBUTION, POOL_PURCHASED
from backend.billing.pricing_engine import compute_cost_credits, estimate_task_reserve


class TransferForbiddenError(Exception):
    """積分不可轉贈／轉移／提現。"""

    def __init__(self) -> None:
        super().__init__("積分不可轉贈、轉移或提現")


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
        return {
            "account_id": account_id,
            "balances": balances,
            "spendable_credits": spendable,
            "pricing_config_version": pricing["version"],
            "credit_policy_version": policy["version"],
            "transfer_allowed": False,
        }

    def topup_purchased(self, user_id: str, amount: float, *, source: str = "purchase") -> dict[str, Any]:
        if amount <= 0:
            raise ValueError("充值金額須大於 0")
        account_id = self.ensure_user(user_id)
        self.store.credit_pool(account_id, POOL_PURCHASED, amount, source=source, description="購買積分入帳")
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
        if available < estimate:
            raise InsufficientCreditsError(balance_credits=available, required_credits=estimate)
        self.store.create_task_record(task_id, account_id, estimate, snapshot)
        breakdown = self.store.spend_from_pools(account_id, estimate, task_id=task_id, source="reserve")
        return {
            "task_id": task_id,
            "reserved_credits": estimate,
            "breakdown": breakdown,
            "pricing_config_version": snapshot["pricing_config_version"],
            "credit_policy_version": snapshot["credit_policy_version"],
        }

    def settle_task_usage(
        self,
        task_id: str,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cached_tokens: int = 0,
        cache_write_tokens: int = 0,
        model: str = "default",
        role: str = "",
        tool: str = "",
        event_type: str = "llm",
        source: str = "call_llm",
        key_id: str | None = None,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.store.get_task_snapshot(task_id)
        if not snapshot:
            raise ValueError(f"任務 {task_id} 無定價快照")
        config = snapshot.get("pricing_config", {})
        actual = compute_cost_credits(
            config,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
            role=role,
            tool=tool,
        )
        with self.store._conn() as conn:
            row = conn.execute("SELECT account_id FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if not row:
            raise ValueError(f"任務 {task_id} 不存在")
        account_id = row["account_id"]
        self.store.record_usage_event(
            account_id=account_id,
            task_id=task_id,
            event_type=event_type,
            source=source,
            tokens=input_tokens + output_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
            cost_credits=actual,
            pricing_version=snapshot.get("pricing_config_version"),
            key_id=key_id,
            meta=meta,
        )
        return {"task_id": task_id, "cost_credits": actual, "pricing_version": snapshot.get("pricing_config_version")}

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

    def redeem_contribution(self, user_id: str, amount: float) -> dict[str, Any]:
        account_id = self.ensure_user(user_id)
        balances = self.store.get_balances(account_id)
        avail = balances.get(POOL_CONTRIBUTION, 0.0)
        if amount > avail:
            raise InsufficientCreditsError(balance_credits=avail, required_credits=amount)
        self.store.spend_from_pools(account_id, amount, source="contribution_redeem")
        self.store.credit_pool(account_id, POOL_PURCHASED, amount, source="contribution_redeem", description="貢獻積分解鎖")
        return self.get_wallet_summary(user_id)


_pools: PoolsService | None = None


def get_pools_service() -> PoolsService:
    global _pools
    if _pools is None:
        _pools = PoolsService()
    return _pools


def reset_pools_service(service: PoolsService | None = None) -> None:
    global _pools
    _pools = service
