"""任務拆分器 —— EvoLoop 核心主功能。

將複雜目標分解為可並行執行的子工作項，是整個公司運行時的
第一大階段。支援三種拆分策略：

  1. LLM 驅動：利用 LLM 理解目標語義，智能分解與角色指派
  2. 模板驅動：基於內建任務模板（如 page_dev）快速匹配
  3. 規則驅動：簡單關鍵字拆分，適用於低複雜度任務

設計原則：
  - 獨立模組：可脫離 CompanyOrchestrator 單獨使用與測試
  - 策略可插拔：三種策略可根據場景自動選擇或手動指定
  - 層級感知：充分利用 org_chart 規劃並行階段與依賴鏈
  - 預算感知：根據預算壓力自動選擇合適的拆分策略

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- types：策略列舉、拆分結果模型與 draft 假設 helper
- llm：LLM 呼叫執行緒輔助
- service：TaskDecomposer 本體
- _compat：call_llm patch 相容層（呼叫時解析套件層屬性）
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
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
from backend.core.llm import call_llm, llm_kwargs_for_role, parse_json_response

from .service import TaskDecomposer, logger
from .types import DecompositionResult, DecompositionStrategy

__all__ = [
    "Any",
    "BudgetManager",
    "BudgetTier",
    "CompanyConfig",
    "CostTracker",
    "DecompositionResult",
    "DecompositionStrategy",
    "Enum",
    "PromptConfig",
    "RoleType",
    "TaskDecomposer",
    "WorkItem",
    "WorkItemManager",
    "WorkItemStatus",
    "annotations",
    "asyncio",
    "call_llm",
    "catalog_role_ids",
    "dataclass",
    "field",
    "hashlib",
    "llm_kwargs_for_role",
    "logger",
    "logging",
    "os",
    "parse_json_response",
    "resolve_assignee",
    "time",
]
