"""TaskDecomposer 的公開入口 decompose／build_work_items 與策略選擇（含拆分結果快取）（自 decomposer/service.py 抽出）。"""

from __future__ import annotations

import hashlib
import os
from collections import OrderedDict as _OrderedDict

from backend.company.milestone_actions import resolve_assignee
from backend.company.state import BudgetTier, RoleType, WorkItem, WorkItemStatus

from ..types import DecompositionResult, DecompositionStrategy
from .llm_mixin import _LlmMixin
from .state import logger

# ── 拆分結果快取（優化 #13）──
_DECOMPOSE_CACHE_SIZE = int(os.getenv("EVOL_DECOMPOSE_CACHE_SIZE", "64"))

_decompose_cache: _OrderedDict[str, DecompositionResult] = _OrderedDict()


class _DecomposeMixin(_LlmMixin):

    # ═══════════════════════════════════════════════════════════
    # 公開 API
    # ═══════════════════════════════════════════════════════════

    async def decompose(
        self,
        goal: str,
        strategy: DecompositionStrategy = DecompositionStrategy.AUTO,
    ) -> DecompositionResult:
        """將目標分解為子工作項描述（優化 #13：拆分結果快取）。

        Args:
            goal: 要分解的目標描述
            strategy: 拆分策略（預設 AUTO，自動選擇最優策略）

        Returns:
            DecompositionResult: 包含子工作項描述、執行計劃、階段資訊
        """
        # 自動選擇策略
        if strategy == DecompositionStrategy.AUTO:
            strategy = self._select_strategy(goal)

        # 查詢快取（相同目標 + 策略 → 復用拆分結果）
        cache_key = hashlib.sha256(f"{strategy.value}:{goal}".encode()).hexdigest()[:24]
        if cache_key in _decompose_cache:
            logger.info("任務拆分快取命中：%s", cache_key[:12])
            _decompose_cache.move_to_end(cache_key)
            return _decompose_cache[cache_key]

        logger.info("任務拆分開始：goal=%s，strategy=%s", goal[:80], strategy.value)

        if strategy == DecompositionStrategy.TEMPLATE:
            result = self._template_decompose(goal)
        elif strategy == DecompositionStrategy.RULE:
            result = self._rule_decompose(goal)
        else:
            result = await self._llm_decompose(goal)

        # 存入快取
        _decompose_cache[cache_key] = result
        if len(_decompose_cache) > _DECOMPOSE_CACHE_SIZE:
            _decompose_cache.popitem(last=False)

        logger.info(
            "任務拆分完成：%d 個子工作項，%d 個階段",
            result.subtask_count,
            result.phase_count,
        )
        return result

    def build_work_items(
        self,
        result: DecompositionResult,
        created_by: RoleType = RoleType.MANAGER,
    ) -> list[WorkItem]:
        """將拆分結果轉換為實際工作項（含依賴解析）。

        這是 decompose 的後續步驟：將 LLM/模板產出的子工作項描述
        轉換為 WorkItemManager 中的實際工作項，並解析索引式依賴為實際 ID。

        Args:
            result: decompose() 的回傳結果
            created_by: 創建者角色

        Returns:
            list[WorkItem]: 已建立的工作項列表（狀態為 READY）
        """
        # 步驟 1：建立所有工作項（暫無依賴）
        created_items: list[WorkItem] = []
        id_map: dict[int, str] = {}

        for i, task in enumerate(result.subtasks):
            role_str = task.get("assignee", "developer")
            assignee = resolve_assignee(str(role_str or "developer"))

            complexity = task.get("complexity", "medium")
            tier_map = {
                "low": BudgetTier.SUMMARY,
                "medium": BudgetTier.ROUTINE,
                "high": BudgetTier.REASONING,
            }

            item = self.work_items.create(
                title=task["title"],
                description=task.get("description", ""),
                assignee=assignee,
                created_by=created_by,
                depends_on=[],  # 稍後設定
                tier=tier_map.get(complexity, BudgetTier.ROUTINE),
            )
            item.transition_to(WorkItemStatus.READY)
            created_items.append(item)
            id_map[i] = item.id

        # 步驟 2：設定依賴關係（索引 → 實際 ID）
        for i, task in enumerate(result.subtasks):
            dep_indices = task.get("depends_on", [])
            if isinstance(dep_indices, list) and dep_indices:
                item = created_items[i]
                item.depends_on = [
                    id_map[idx] for idx in dep_indices
                    if idx in id_map
                ]

        logger.info(
            "工作項建立完成：%d 個（含 %d 個有依賴）",
            len(created_items),
            sum(1 for item in created_items if item.depends_on),
        )
        return created_items

    # ═══════════════════════════════════════════════════════════
    # 策略選擇
    # ═══════════════════════════════════════════════════════════

    def _select_strategy(self, goal: str) -> DecompositionStrategy:
        """根據目標特徵與預算壓力自動選擇拆分策略。

        決策邏輯：
          1. 預算壓力 >= 90% → RULE（零成本）
          2. 目標匹配已知模板 → TEMPLATE（快速、低成本）
          3. 預設 → LLM（最強大）
        """
        # 預算壓力高時降級
        if self.budget.budget_pressure >= 0.9:
            logger.info("預算壓力 %.0f%%，使用 RULE 策略", self.budget.budget_pressure * 100)
            return DecompositionStrategy.RULE

        # 檢查是否匹配已知模板
        goal_lower = goal.lower()
        for keyword in self.prompt_config.template_keywords:
            if keyword in goal_lower:
                logger.info("目標匹配模板關鍵字 '%s'，使用 TEMPLATE 策略", keyword)
                return DecompositionStrategy.TEMPLATE

        # 預設使用 LLM
        return DecompositionStrategy.LLM
