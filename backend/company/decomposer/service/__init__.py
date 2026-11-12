"""任務拆分器主體：TaskDecomposer（LLM／模板／規則三策略）。

套件化：實作已由單檔 service.py 拆為 service/ 子套件（mixin 組合），對外 import 路徑 backend.company.decomposer.service.TaskDecomposer 不變。
state／roles／strategies／llm_mixin／decompose_mixin 各自持有職責；call_llm 經 .._compat 於呼叫時解析 backend.company.decomposer.call_llm（保留測試 patch 語意）。
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

from backend.company.budget import BudgetManager, CostTracker
from backend.company.milestone_actions import catalog_role_ids, resolve_assignee
from backend.company.prompts import PromptConfig
from backend.company.state import (
    BudgetTier,
    CompanyConfig,
    RoleType,
    WorkItem,
    WorkItemStatus,
)
from backend.company.work_item import WorkItemManager
from backend.core.llm import llm_kwargs_for_role, parse_json_response

from .._compat import call_llm
from ..types import DecompositionResult, DecompositionStrategy
from .decompose_mixin import _DecomposeMixin
from .state import logger


class TaskDecomposer(_DecomposeMixin):
    """任務拆分器 —— 將複雜目標分解為可執行的子工作項。

    這是 EvoLoop 公司運行時的第一大階段，也是最重要的主功能模組。
    支援三種拆分策略，可根據場景自動選擇或手動指定。

    使用範例：
        >>> config = create_page_dev_team()
        >>> budget = BudgetManager(config.budget)
        >>> decomposer = TaskDecomposer(config, budget)
        >>> result = await decomposer.decompose("開發一個用戶登入頁面")
        >>> items = decomposer.build_work_items(result)
    """


__all__ = [
    "Any",
    "BudgetManager",
    "BudgetTier",
    "CompanyConfig",
    "CostTracker",
    "DecompositionResult",
    "DecompositionStrategy",
    "PromptConfig",
    "RoleType",
    "TaskDecomposer",
    "WorkItem",
    "WorkItemManager",
    "WorkItemStatus",
    "call_llm",
    "catalog_role_ids",
    "hashlib",
    "llm_kwargs_for_role",
    "logger",
    "logging",
    "os",
    "parse_json_response",
    "resolve_assignee",
    "time",
]


# 只保留原單檔模組的介面：移除 import 子模組時自動掛在 service 套件上的屬性，
# 讓 dir(backend.company.decomposer.service) 的公開名稱與原模組一致（24 個）。
for _submodule in (
    "decompose_mixin",
    "llm_mixin",
    "roles",
    "state",
    "strategies",
):
    globals().pop(_submodule, None)
del _submodule
