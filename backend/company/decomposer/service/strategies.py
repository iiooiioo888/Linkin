"""TaskDecomposer 的模板／規則策略與平行階段規劃（自 decomposer/service.py 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.milestone_actions import catalog_role_ids

from ..types import DecompositionResult, DecompositionStrategy
from .roles import _RolesMixin
from .state import logger


class _StrategiesMixin(_RolesMixin):

    def plan_parallel_execution(
        self,
        subtasks: list[dict[str, Any]],
    ) -> list[list[int]]:
        """根據依賴關係規劃並行執行階段。

        使用拓樸排序將子工作項分組為可並行執行的階段。

        Args:
            subtasks: 子工作項列表（含 depends_on 索引）

        Returns:
            list[list[int]]: 每個階段包含的工作項索引列表
        """
        n = len(subtasks)
        if n == 0:
            return []

        # 計算每個工作項的深度（最長依賴鏈長度）
        depth = [0] * n
        changed = True
        while changed:
            changed = False
            for i, task in enumerate(subtasks):
                deps = task.get("depends_on", [])
                if isinstance(deps, list):
                    for dep_idx in deps:
                        if isinstance(dep_idx, int) and 0 <= dep_idx < n:
                            new_depth = depth[dep_idx] + 1
                            if new_depth > depth[i]:
                                depth[i] = new_depth
                                changed = True

        # 按深度分組
        max_depth = max(depth) if depth else 0
        phases: list[list[int]] = [[] for _ in range(max_depth + 1)]
        for i, d in enumerate(depth):
            phases[d].append(i)

        # 移除空階段
        return [p for p in phases if p]

    # ═══════════════════════════════════════════════════════════
    # 模板驅動拆分
    # ═══════════════════════════════════════════════════════════

    def _template_decompose(self, goal: str) -> DecompositionResult:
        """模板驅動拆分：基於內建任務模板匹配。

        根據目標關鍵字匹配最合適的模板，並自動調整角色以匹配
        當前團隊配置。
        """
        goal_lower = goal.lower()

        # 尋找最匹配的模板
        matched_template = None
        matched_keyword = ""
        for keyword, template in self.prompt_config.template_keywords.items():
            if keyword in goal_lower:
                matched_template = template
                matched_keyword = keyword
                break

        if matched_template is None:
            # 無匹配模板，降級為 RULE
            logger.info("無匹配模板，降級為 RULE 策略")
            return self._rule_decompose(goal)

        # 過濾：只保留團隊中存在的角色
        available_roles = set(rt.value for rt in self.config.roles) | catalog_role_ids()
        subtasks = []
        for task in matched_template:
            role = task.get("assignee", "")
            # 若角色不在團隊中，替換為最接近的可用角色
            if role and role not in available_roles:
                replacement = self._find_closest_role(role, available_roles)
                if replacement:
                    task = {**task, "assignee": replacement}
                else:
                    continue  # 無可用角色，跳過此工作項
            subtasks.append(task)

        phases = self.plan_parallel_execution(subtasks)

        return DecompositionResult(
            goal=goal,
            strategy=DecompositionStrategy.TEMPLATE,
            subtasks=subtasks,
            execution_plan=f"使用模板 '{matched_keyword}' 拆分，共 {len(subtasks)} 個子工作項",
            phases=phases,
            meta={"template": matched_keyword},
        )

    # ═══════════════════════════════════════════════════════════
    # 規則驅動拆分
    # ═══════════════════════════════════════════════════════════

    def _rule_decompose(self, goal: str) -> DecompositionResult:
        """規則驅動拆分：簡單關鍵字拆分，零 LLM 成本。

        適用於簡單任務或預算緊張時。根據目標長度與關鍵字
        產生 1-3 個基本工作項。
        """
        available_roles = set(rt.value for rt in self.config.roles)

        # 選擇最佳執行角色
        primary_role = self._pick_best_role(goal, available_roles)

        # 根據目標複雜度決定拆分數量
        word_count = len(goal)
        if word_count < 30:
            # 簡單任務：單一工作項
            subtasks = [{
                "title": goal,
                "description": f"執行目標：{goal}",
                "assignee": primary_role,
                "depends_on": [],
                "complexity": "low",
                "phase": 1,
            }]
        elif word_count < 100:
            # 中等任務：分析 + 執行
            subtasks = [
                {
                    "title": f"分析：{goal[:40]}",
                    "description": f"分析需求並規劃執行方案：{goal}",
                    "assignee": "analyst" if "analyst" in available_roles else primary_role,
                    "depends_on": [],
                    "complexity": "medium",
                    "phase": 1,
                },
                {
                    "title": f"執行：{goal[:40]}",
                    "description": f"根據分析結果執行：{goal}",
                    "assignee": primary_role,
                    "depends_on": [0],
                    "complexity": "medium",
                    "phase": 2,
                },
            ]
        else:
            # 複雜任務：分析 + 執行 + 審查
            reviewer_role = "reviewer" if "reviewer" in available_roles else primary_role
            subtasks = [
                {
                    "title": f"分析：{goal[:40]}",
                    "description": f"分析需求並規劃執行方案：{goal}",
                    "assignee": "analyst" if "analyst" in available_roles else primary_role,
                    "depends_on": [],
                    "complexity": "medium",
                    "phase": 1,
                },
                {
                    "title": f"執行：{goal[:40]}",
                    "description": f"根據分析結果執行：{goal}",
                    "assignee": primary_role,
                    "depends_on": [0],
                    "complexity": "high",
                    "phase": 2,
                },
                {
                    "title": f"審查：{goal[:40]}",
                    "description": f"審查交付物品質並提供回饋：{goal}",
                    "assignee": reviewer_role,
                    "depends_on": [1],
                    "complexity": "low",
                    "phase": 3,
                },
            ]

        phases = self.plan_parallel_execution(subtasks)

        return DecompositionResult(
            goal=goal,
            strategy=DecompositionStrategy.RULE,
            subtasks=subtasks,
            execution_plan=f"規則拆分：{len(subtasks)} 個子工作項，{len(phases)} 個階段",
            phases=phases,
            meta={"word_count": word_count},
        )
