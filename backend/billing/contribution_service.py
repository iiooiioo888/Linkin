"""貢獻積分：鎖倉、轉換、分期解鎖（v6.0）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from backend.billing.errors import InsufficientCreditsError
from backend.billing.pool_store import get_pool_store, _utc_now
from backend.billing.pool_types import (
    CONTRIBUTION_LOCK_TIERS,
    CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
    POOL_PURCHASED,
)

# 動態鎖倉閾值：累積未鎖定積分超過此值才建議轉鎖倉
_LOCK_THRESHOLD_BASE = 50.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def contribution_status(account_id: str) -> dict[str, Any]:
    store = get_pool_store()
    bals = store.get_balances(account_id)
    unlocked = float(bals.get(POOL_CONTRIBUTION_UNLOCKED, 0))
    locked = float(bals.get(POOL_CONTRIBUTION_LOCKED, 0))
    threshold = _LOCK_THRESHOLD_BASE
    convertible = max(0.0, unlocked - threshold)
    installments = store.list_lock_installments(account_id)
    return {
        "unlocked": unlocked,
        "locked": locked,
        "convert_threshold": threshold,
        "accumulated_unlocked": unlocked,
        "convertible_to_locked": convertible,
        "convert_ratio_to_purchased": CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
        "lock_tiers": CONTRIBUTION_LOCK_TIERS,
        "installments": installments,
        "notice_zh": f"當前累積 {unlocked:.1f} / 閾值 {threshold:.1f}，剩餘 {convertible:.1f} 可轉鎖倉",
    }


def lock_contribution(account_id: str, amount: float, lock_days: int) -> dict[str, Any]:
    if lock_days not in CONTRIBUTION_LOCK_TIERS:
        raise ValueError("鎖定期須為 30 / 90 / 180 天")
    if amount <= 0:
        raise ValueError("鎖倉數量須大於 0")
    store = get_pool_store()
    status = contribution_status(account_id)
    if amount > status["convertible_to_locked"]:
        raise InsufficientCreditsError(
            balance_credits=status["convertible_to_locked"],
            required_credits=amount,
            message=f"超過可轉鎖倉餘額（剩餘 {status['convertible_to_locked']:.2f}）",
        )
    multiplier = float(CONTRIBUTION_LOCK_TIERS[lock_days])
    now = _utc_now_iso()
    with store._conn() as conn:
        if not store.atomic_debit_pool(conn, account_id, POOL_CONTRIBUTION_UNLOCKED, amount, now):
            raise InsufficientCreditsError(balance_credits=status["unlocked"], required_credits=amount)
    store.credit_pool(
        account_id,
        POOL_CONTRIBUTION_LOCKED,
        amount,
        source=f"lock_{lock_days}d",
        description=f"鎖倉 {lock_days} 天 ×{multiplier}",
        origin="contribution_lock",
        lock_days=lock_days,
        lock_multiplier=multiplier,
    )
    per = round(amount / 3, 4)
    iid = store.create_lock_installment(
        account_id,
        total=amount,
        per_installment=per,
        lock_days=lock_days,
        lock_multiplier=multiplier,
    )
    return {
        "locked_amount": amount,
        "lock_days": lock_days,
        "lock_multiplier": multiplier,
        "installment_id": iid,
        "installments_total": 3,
        **contribution_status(account_id),
    }


def process_due_installments(account_id: str | None = None) -> list[dict[str, Any]]:
    """分期解鎖：將到期分期從 locked 轉入 purchased（1:1 本金，倍率已体现在锁仓时）。"""
    store = get_pool_store()
    return store.process_lock_installments(account_id)


def convert_unlocked_to_purchased(account_id: str, amount: float) -> dict[str, Any]:
    from backend.billing.pools_service import get_pools_service

    return get_pools_service().convert_contribution_unlocked(account_id, amount)
