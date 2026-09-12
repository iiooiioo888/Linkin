"""貢獻積分：鎖倉、轉換、分期解鎖（v6.0）。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.billing.contribution_threshold import compute_lock_threshold
from backend.billing.errors import InsufficientCreditsError
from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import (
    CONTRIBUTION_LOCK_TIERS,
    CONTRIBUTION_UNLOCKED_CONVERT_RATIO,
    POOL_CONTRIBUTION_LOCKED,
    POOL_CONTRIBUTION_UNLOCKED,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _plan_id_for_account(account_id: str) -> str:
    with get_pool_store()._conn() as conn:
        row = conn.execute("SELECT plan_id FROM accounts WHERE user_id=?", (account_id.strip(),)).fetchone()
    return str(row["plan_id"]) if row else "free"


def contribution_status(account_id: str) -> dict[str, Any]:
    store = get_pool_store()
    store.ensure_user_profile(account_id)
    bals = store.get_balances(account_id)
    unlocked = float(bals.get(POOL_CONTRIBUTION_UNLOCKED, 0))
    locked = float(bals.get(POOL_CONTRIBUTION_LOCKED, 0))
    plan_id = _plan_id_for_account(account_id)
    threshold = compute_lock_threshold(unlocked=unlocked, locked=locked, plan_id=plan_id)
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
        "threshold_dynamic": True,
        "notice_zh": (
            f"當前累積 {unlocked:.1f} / 動態閾值 {threshold:.1f}，"
            f"剩餘 {convertible:.1f} 可轉鎖倉"
        ),
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


def process_due_installments(account_id: str | None = None, *, force: bool = False) -> list[dict[str, Any]]:
    """分期解鎖：將到期分期從 locked 轉入 purchased（本金 + 獎勵）。"""
    return get_pool_store().process_lock_installments(account_id, force=force)


def early_unlock_contribution(account_id: str, installment_id: str) -> dict[str, Any]:
    result = get_pool_store().early_unlock_installment(account_id, installment_id)
    return {**result, **contribution_status(account_id)}


def convert_unlocked_to_purchased(account_id: str, amount: float) -> dict[str, Any]:
    from backend.billing.pools_service import get_pools_service

    return get_pools_service().convert_contribution_unlocked(account_id, amount)


def run_contribution_decay() -> list[dict[str, Any]]:
    return get_pool_store().run_contribution_decay()
