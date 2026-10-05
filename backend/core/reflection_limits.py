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


def is_minecraft_ops_execution_state(state: Mapping[str, Any]) -> bool:
    """minecraft_ops 路徑：僅允許單次評估，不進入分數驅動的反思／改進。"""
    return str(state.get("resolved_execution_path") or "").strip().lower() == "minecraft_ops"


def is_simple_execution_state(state: Mapping[str, Any]) -> bool:
    """是否套用簡單路徑反思上限（強制 simple 策略或已解析為 simple／opc 生成閉環）。"""
    strategy = (state.get("execution_strategy") or "auto").strip().lower()
    if strategy == "simple":
        return True
    if strategy == "company":
        return False
    path = str(state.get("resolved_execution_path") or "").strip().lower()
    if path in ("simple", "opc"):
        return True
    complexity = (state.get("task_complexity") or "").strip().lower()
    return complexity == "simple"


def _company_reflect_max_iterations() -> int:
    """公司路徑：僅 post_company_reflect 階段可能進入反思／改進（#11）。"""
    try:
        from backend.core.post_company_reflect import post_company_reflect_mode

        mode = post_company_reflect_mode()
    except Exception:
        mode = "off"
    if mode == "full":
        return MAX_ITERATIONS
    return 0


def _simple_path_base_cap(complexity: str, *, strategy: str) -> int:
    if strategy == "simple":
        return simple_path_max_iterations()
    level = (complexity or "simple").strip().lower()
    if level == "medium":
        return 2
    if level == "complex":
        return MAX_ITERATIONS
    return simple_path_max_iterations()


def reflection_max_iterations(state: Mapping[str, Any]) -> int:
    """依執行策略與路徑解析有效反思迭代上限（LangGraph、SSE、Task、preview 共用）。"""
    if is_minecraft_ops_execution_state(state):
        return 0

    path = str(state.get("resolved_execution_path") or "").strip().lower()
    strategy = (state.get("execution_strategy") or "auto").strip().lower()

    if state.get("company_result"):
        mode = str(state.get("post_company_reflect_mode") or "").strip().lower()
        if not mode:
            try:
                from backend.core.post_company_reflect import post_company_reflect_mode

                mode = post_company_reflect_mode()
            except Exception:
                mode = "off"
        return MAX_ITERATIONS if mode == "full" else 0

    if path == "company" or strategy == "company":
        return _company_reflect_max_iterations()

    if path == "opc":
        return MAX_ITERATIONS

    if is_simple_execution_state(state):
        complexity = (state.get("task_complexity") or "simple").strip().lower()
        base = _simple_path_base_cap(complexity, strategy=strategy)
        bonus = 0
        try:
            from backend.core.routing_feedback import extra_reflection_rounds

            bonus = extra_reflection_rounds(
                execution_path=path or "simple",
            )
        except Exception:
            bonus = 0
        return base + bonus

    return MAX_ITERATIONS


def resolve_task_complexity(query: str, execution_strategy: str = "auto") -> str:
    """Task／Chat 共用的複雜度分類（強制 simple 策略時固定 simple）。"""
    if (execution_strategy or "auto").strip().lower() == "simple":
        return "simple"
    from backend.core.cost_speed_router import classify_task_complexity

    return classify_task_complexity(query or "")


__all__ = [
    "is_minecraft_ops_execution_state",
    "is_simple_execution_state",
    "reflection_max_iterations",
    "resolve_task_complexity",
    "simple_path_max_iterations",
]
