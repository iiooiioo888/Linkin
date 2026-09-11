"""Fault Pool 運行時 v6.0 Phase 2 — 獨立分類帳、支出、耗盡告警。"""
from __future__ import annotations

from typing import Any

from backend.billing.pool_store import get_pool_store

DEFAULT_PLATFORM_TAKE = 0.08
DEFAULT_DEPLETION_THRESHOLD = 100.0
DEFAULT_PUBLIC_POOL_PREMIUM = 1.15


def get_fault_pool_balance() -> float:
    return get_pool_store().fault_pool_balance()


def credit_fault_pool(
    amount: float,
    reason: str,
    *,
    account_id: str | None = None,
    task_id: str | None = None,
    installment_id: str | None = None,
    source: str = "platform",
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """入帳：平台抽成、快取節省、獎勵折讓、沒收等。"""
    store = get_pool_store()
    entry = store.fault_pool_credit(
        amount,
        reason,
        account_id=account_id,
        task_id=task_id,
        installment_id=installment_id,
        source=source,
        meta=meta,
    )
    _maybe_handle_depletion()
    return entry


def disburse_from_fault_pool(
    amount: float,
    reason: str,
    *,
    account_id: str | None = None,
    task_id: str | None = None,
    installment_id: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """支出：鎖倉獎勵、降級補貼等。"""
    store = get_pool_store()
    result = store.fault_pool_debit(
        amount,
        reason,
        account_id=account_id,
        task_id=task_id,
        installment_id=installment_id,
        meta=meta,
    )
    _maybe_handle_depletion()
    return result


def disburse_for_lock_reward(
    reward_amount: float,
    *,
    account_id: str,
    installment_id: str,
) -> dict[str, Any]:
    """分期獎勵優先從 fault_pool 撥付。"""
    if reward_amount <= 0:
        return {"requested": 0.0, "disbursed": 0.0, "shortfall": 0.0}
    balance = get_fault_pool_balance()
    disbursed = min(reward_amount, balance)
    if disbursed > 0:
        disburse_from_fault_pool(
            disbursed,
            "lock_installment_reward",
            account_id=account_id,
            installment_id=installment_id,
            meta={"reward_requested": reward_amount},
        )
    shortfall = round(reward_amount - disbursed, 4)
    if shortfall > 0:
        credit_fault_pool(
            shortfall,
            "lock_reward_shortfall_platform",
            account_id=account_id,
            installment_id=installment_id,
            source="platform_take",
        )
    return {"requested": reward_amount, "disbursed": disbursed, "shortfall": shortfall}


def record_cache_invalidation(
    *,
    task_id: str,
    old_key_id: str,
    new_key_id: str,
    cost_credits: float,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Failover 快取失效寫入 fault_pool（負向事件記錄為支出需求）。"""
    amount = max(0.01, round(cost_credits * 0.02, 4))
    return credit_fault_pool(
        amount,
        "cache_invalidation_failover",
        account_id=account_id,
        task_id=task_id,
        source="cache_savings",
        meta={"old_key_id": old_key_id, "new_key_id": new_key_id},
    )


def record_relay_cache_write(task_id: str, cost_credits: float, *, account_id: str | None = None) -> dict[str, Any]:
    return credit_fault_pool(
        max(0.01, round(cost_credits * 0.01, 4)),
        "relay_cache_write",
        account_id=account_id,
        task_id=task_id,
        source="cache_savings",
    )


def record_degrade_spread(task_id: str, spread_credits: float, *, account_id: str | None = None) -> dict[str, Any]:
    return credit_fault_pool(
        max(0.0, round(spread_credits, 4)),
        "degrade_spread",
        account_id=account_id,
        task_id=task_id,
        source="platform_take",
    )


def record_public_pool_premium(task_id: str, premium_credits: float, *, account_id: str | None = None) -> dict[str, Any]:
    return credit_fault_pool(
        max(0.0, round(premium_credits, 4)),
        "public_pool_premium",
        account_id=account_id,
        task_id=task_id,
        source="platform_take",
    )


def record_split_duplicate_write(task_id: str, duplicate_credits: float) -> dict[str, Any]:
    return credit_fault_pool(
        max(0.0, round(duplicate_credits, 4)),
        "split_duplicate_write",
        task_id=task_id,
        source="cache_savings",
    )


def fault_pool_status() -> dict[str, Any]:
    store = get_pool_store()
    balance = store.fault_pool_balance()
    threshold = float(store.get_routing_runtime("fault_pool_depletion_threshold", DEFAULT_DEPLETION_THRESHOLD))
    take_rate = float(store.get_routing_runtime("platform_take_rate", DEFAULT_PLATFORM_TAKE))
    paused = bool(store.get_routing_runtime("public_pool_paused", False))
    premium = float(store.get_routing_runtime("public_pool_premium", DEFAULT_PUBLIC_POOL_PREMIUM))
    alerts = store.list_fault_pool_alerts(limit=10)
    ledger = store.list_fault_pool_ledger(limit=20)
    by_reason = store.fault_pool_summary_by_reason()
    return {
        "balance": balance,
        "depletion_threshold": threshold,
        "depleted": balance < threshold,
        "platform_take_rate": take_rate,
        "public_pool_paused": paused,
        "public_pool_premium": premium,
        "alerts": alerts,
        "ledger_recent": ledger,
        "by_reason": by_reason,
        "notice_zh": (
            "公共池已暫停，共享池不受影響"
            if paused
            else f"Fault Pool 餘額 {balance:.2f}，平台抽成 {take_rate * 100:.1f}%"
        ),
    }


def _maybe_handle_depletion() -> None:
    store = get_pool_store()
    balance = store.fault_pool_balance()
    threshold = float(store.get_routing_runtime("fault_pool_depletion_threshold", DEFAULT_DEPLETION_THRESHOLD))
    if balance >= threshold:
        return
    take = float(store.get_routing_runtime("platform_take_rate", DEFAULT_PLATFORM_TAKE))
    new_take = min(0.25, round(take + 0.02, 4))
    store.set_routing_runtime("platform_take_rate", new_take)
    store.set_routing_runtime("public_pool_paused", True)
    store.record_fault_pool_alert(
        kind="depletion",
        message_zh=f"Fault Pool 餘額 {balance:.2f} 低於閾值 {threshold:.2f}；已提高抽成至 {new_take * 100:.1f}% 並暫停公共池",
        balance=balance,
    )
