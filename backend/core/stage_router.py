"""管線環節 → 模型層級路由（P0：任務-模型匹配）。

反思閉環各環節使用不同規模模型，降低 API 成本 40–60%：
  - generate / improve：ROUTINE（日常生成）
  - evaluate / cross_eval：SUMMARY（最便宜，分類評分）
  - reflect：REASONING（根因分析需較強推理）
"""

from __future__ import annotations

import logging
import os
from typing import Literal

from backend.company.budget import BudgetManager
from backend.company.state import BudgetConfig, BudgetTier

logger = logging.getLogger(__name__)

PipelineStage = Literal[
    "generate", "evaluate", "reflect", "improve", "cross_eval", "decompose"
]

# 環節 → 預設層級（可透過 EVOL_STAGE_TIER_<STAGE> 覆寫）
_DEFAULT_STAGE_TIERS: dict[str, BudgetTier] = {
    "generate": BudgetTier.ROUTINE,
    "evaluate": BudgetTier.SUMMARY,
    "reflect": BudgetTier.REASONING,
    "improve": BudgetTier.ROUTINE,
    "cross_eval": BudgetTier.SUMMARY,
    "decompose": BudgetTier.REASONING,
}

_STAGE_TIER_ENV = {
    "generate": "EVOL_STAGE_TIER_GENERATE",
    "evaluate": "EVOL_STAGE_TIER_EVALUATE",
    "reflect": "EVOL_STAGE_TIER_REFLECT",
    "improve": "EVOL_STAGE_TIER_IMPROVE",
    "cross_eval": "EVOL_STAGE_TIER_CROSS_EVAL",
    "decompose": "EVOL_STAGE_TIER_DECOMPOSE",
}

_budget_manager: BudgetManager | None = None


def _get_budget_manager() -> BudgetManager:
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = BudgetManager(BudgetConfig())
    return _budget_manager


def _parse_tier(name: str) -> BudgetTier | None:
    try:
        return BudgetTier(name.strip().lower())
    except ValueError:
        return None


def stage_tier(stage: PipelineStage) -> BudgetTier:
    """解析環節對應的 BudgetTier。"""
    env_key = _STAGE_TIER_ENV.get(stage)
    if env_key:
        override = os.getenv(env_key)
        if override:
            parsed = _parse_tier(override)
            if parsed:
                return parsed
            logger.warning("無效的 %s=%s，使用預設層級", env_key, override)
    return _DEFAULT_STAGE_TIERS.get(stage, BudgetTier.ROUTINE)


def resolve_stage_model(
    stage: PipelineStage,
    *,
    query: str | None = None,
    complexity: str | None = None,
) -> str:
    """依管線環節選擇模型（含預算壓力降級與 cost_speed 成本感知）。"""
    tier = stage_tier(stage)
    fallback = _get_budget_manager().resolve_model_for_tier(tier)
    try:
        from backend.core.cost_speed_router import (
            classify_task_complexity,
            cost_speed_enabled,
            resolve_cost_speed_model,
        )

        if cost_speed_enabled():
            comp = complexity or (classify_task_complexity(query) if query else None)
            if comp in {"simple", "medium", "complex"}:
                model = resolve_cost_speed_model(comp, stage, fallback)  # type: ignore[arg-type]
                logger.debug(
                    "環節 %s → complexity %s → model %s（tier %s）",
                    stage,
                    comp,
                    model,
                    tier.value,
                )
                return model
    except Exception as exc:
        logger.warning("cost_speed 路由失敗，回退 tier 模型：%s", exc)
    logger.debug("環節 %s → tier %s → model %s", stage, tier.value, fallback)
    return fallback


def reset_stage_budget() -> None:
    """重置環節預算計數（測試用）。"""
    global _budget_manager
    if _budget_manager is not None:
        _budget_manager.reset_session()
