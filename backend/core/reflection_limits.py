"""簡單路徑反思迭代上限（與公司／完整閉環分離，省 token）。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from backend.core.graph import MAX_ITERATIONS


def simple_path_max_iterations() -> int:
    """簡單路徑最大反思／改進輪次（預設 1；0 表示僅評估、不進入改進迴圈）。"""
    raw = os.getenv("EVOL_SIMPLE_MAX_ITERATIONS", "1").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 1


def is_simple_execution_state(state: Mapping[str, Any]) -> bool:
    """是否套用 EVOL_SIMPLE_MAX_ITERATIONS（強制 simple 或已標記 simple 複雜度）。"""
    strategy = (state.get("execution_strategy") or "auto").strip().lower()
    if strategy == "simple":
        return True
    if strategy == "company":
        return False
    complexity = (state.get("task_complexity") or "").strip().lower()
    return complexity == "simple"


def reflection_max_iterations(state: Mapping[str, Any]) -> int:
    """依執行策略解析有效 MAX_ITERATIONS（LangGraph 與 SSE 手抄迴圈共用）。"""
    if is_simple_execution_state(state):
        return simple_path_max_iterations()
    return MAX_ITERATIONS
