"""預算控制系統。

提供：
- BudgetManager: 追蹤任務/會話/月度花費，強制執行上限與降級
- TierRouter: 根據任務重要性與預算壓力選擇模型層級
- CostTracker: 估算 LLM 呼叫成本（token 計價）

所有金額以 USD 為單位。

套件化：本模組已拆為 backend/company/budget/ 套件，公開 import 路徑不變。
constants／costs／tiers／manager 各自持有領域內容；本 __init__.py 只做 re-export。
"""

from __future__ import annotations

# 相容：原模組因 import 而存在的公開名稱（維持 dir() 介面；不擴大 __all__）
import logging  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from typing import Any  # noqa: F401

from backend.company.rate_card import (
    estimate_usage_cost,
    get_model_costs,
    get_model_rate_cards,
    public_rate_cards,
    rate_card_for,
    reload_model_costs,
)
from backend.company.state import BudgetConfig, BudgetTier  # noqa: F401

from .constants import (  # noqa: F401
    DEFAULT_FORECAST_WINDOW_DAYS,
    DEFAULT_HISTORY_WINDOW_DAYS,
    MIN_DATA_POINTS_FOR_FORECAST,
    logger,
)
from .costs import CostTracker
from .manager import BudgetManager
from .tiers import TierRouter

__all__ = [
    "BudgetManager",
    "CostTracker",
    "TierRouter",
    "estimate_usage_cost",
    "get_model_costs",
    "get_model_rate_cards",
    "public_rate_cards",
    "rate_card_for",
    "reload_model_costs",
]


# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.company.budget) 的公開名稱與原模組一致（20 個）。
for _submodule in (
    "constants",
    "costs",
    "manager",
    "tiers",
):
    globals().pop(_submodule, None)
del _submodule
