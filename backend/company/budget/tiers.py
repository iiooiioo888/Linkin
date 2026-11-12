"""TierRouter：tier→model 選擇與路由（自 backend.company.budget 抽出）。"""

from __future__ import annotations

from backend.company.state import BudgetConfig, BudgetTier

from .constants import logger


class TierRouter:
    """根據任務重要性與預算壓力選擇模型層級。"""

    def __init__(self, config: BudgetConfig):
        self.config = config

    def resolve_model(
        self,
        tier: BudgetTier,
        budget_pressure: float = 0.0,  # 0.0 ~ 1.0，越高壓力越大
    ) -> str:
        """根據層級與預算壓力解析實際使用的模型名稱。

        budget_pressure >= degrade_threshold 時，使用降級鏈中的便宜模型。
        """
        if budget_pressure >= self.config.degrade_threshold:
            degraded = self.config.degrade_chain.get(tier)
            if degraded:
                logger.info(
                    "預算壓力 %.0f%%，tier %s 降級為 %s",
                    budget_pressure * 100,
                    tier.value,
                    degraded,
                )
                return degraded
        return self.config.tier_models.get(tier, "gpt-5.6-luna")

    def select_tier(
        self,
        task_complexity: str,
        is_critical: bool = False,
    ) -> BudgetTier:
        """根據任務特徵選擇層級。"""
        if is_critical:
            return BudgetTier.CRITICAL
        mapping = {
            "high": BudgetTier.REASONING,
            "medium": BudgetTier.ROUTINE,
            "low": BudgetTier.SUMMARY,
        }
        return mapping.get(task_complexity, BudgetTier.ROUTINE)
