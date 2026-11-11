"""多池積分持久層 — balances / grants / pricing / tasks / ledger（account_id = user_id）。

自 backend.billing.pool_store 模組拆為套件，公開 import 路徑維持不變，例如：
from backend.billing.pool_store import PoolStore, get_pool_store, KEY_FAILURE_APPEAL_WINDOW_DAYS

PoolStore 由各領域 mixin（schema／pricing／pools／task_billing／keys／misc／installments）
依序組合而成，方法本體為原模組原樣搬移；singleton 管理仍在本套件入口。
"""

from __future__ import annotations

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
from backend.billing.pricing_engine import DEFAULT_CREDIT_POLICY, DEFAULT_PRICING_CONFIG
from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS

from .installments import _InstallmentsMixin
from .schema import (
    _DB_LOCK,
    _DEFAULT_DB,
    EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO,
    KEY_FAILURE_APPEAL_WINDOW_DAYS,
    _installment_interval_days,
    _installment_reward_per_period,
    _installment_reward_total,
    _month_key,
    _parse_iso,
    _utc_now,
)
from .schema_sql import _POOL_SCHEMA

__all__ = [
    "CONTRIBUTION_UNLOCKED_DECAY",
    "CONTRIBUTION_UNLOCKED_HALF_LIFE_MONTHS",
    "DEFAULT_CREDIT_POLICY",
    "DEFAULT_PRICING_CONFIG",
    "DEFAULT_VENDOR_CONFIGS",
    "EARLY_UNLOCK_PRINCIPAL_PENALTY_RATIO",
    "KEY_FAILURE_APPEAL_WINDOW_DAYS",
    "POOL_CONTRIBUTION_LOCKED",
    "POOL_CONTRIBUTION_UNLOCKED",
    "POOL_LOCKED",
    "POOL_MONTHLY_GRANT",
    "POOL_PURCHASED",
    "SPEND_ORDER",
    "_DB_LOCK",
    "_DEFAULT_DB",
    "_POOL_SCHEMA",
    "PoolStore",
    "_installment_interval_days",
    "_installment_reward_per_period",
    "_installment_reward_total",
    "_month_key",
    "_parse_iso",
    "_utc_now",
    "get_pool_store",
    "reset_pool_store",
]


class PoolStore(_InstallmentsMixin):
    pass


_pool_store: PoolStore | None = None


def get_pool_store() -> PoolStore:
    global _pool_store
    if _pool_store is None:
        _pool_store = PoolStore()
    return _pool_store


def reset_pool_store(store: PoolStore | None = None) -> None:
    global _pool_store
    _pool_store = store
