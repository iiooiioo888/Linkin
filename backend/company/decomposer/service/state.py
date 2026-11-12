"""TaskDecomposer 的狀態初始化與組織圖／角色描述格式化（自 decomposer/service.py 抽出）。"""

from __future__ import annotations

import logging

from backend.company.budget import BudgetManager
from backend.company.prompts import PromptConfig
from backend.company.state import CompanyConfig, RoleType
from backend.company.work_item import WorkItemManager

# 沿用原單檔模組名稱，維持日誌通道不變
logger = logging.getLogger("backend.company.decomposer")


class _StateMixin:
    config: CompanyConfig
    budget: BudgetManager
    work_items: WorkItemManager
    prompt_config: PromptConfig

    def __init__(
        self,
        config: CompanyConfig,
        budget_manager: BudgetManager,
        work_items: WorkItemManager | None = None,
        prompt_config: PromptConfig | None = None,
    ):
        self.config = config
        self.budget = budget_manager
        self.work_items = work_items or WorkItemManager()
        self.prompt_config = prompt_config or config.prompt_config

    # ═══════════════════════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════════════════════

    def _format_org_chart(self) -> str:
        """格式化組織架構樹（供 Prompt 使用）。"""
        if not self.config.org_chart:
            return "\n".join(
                f"- {rt.value}（{rd.name}）"
                for rt, rd in self.config.roles.items()
            )

        def _format_subtree(role: RoleType, indent: int = 0) -> list[str]:
            lines = []
            role_def = self.config.roles.get(role)
            name = role_def.name if role_def else role.value
            level = self.config.get_role_level(role)
            lines.append(f"{'  ' * indent}├─ {role.value}（{name}，Level {level}）")
            for sub in self.config.org_chart.get(role, []):
                lines.extend(_format_subtree(sub, indent + 1))
            return lines

        roots = [r for r in self.config.roles if self.config.get_role_level(r) == 0]
        if not roots and self.config.roles:
            roots = [next(iter(self.config.roles))]

        lines = ["組織層級結構："]
        for root in roots:
            lines.extend(_format_subtree(root))
        return "\n".join(lines)

    def _format_role_descriptions(self) -> str:
        """格式化角色能力說明（供 Prompt 使用）。"""
        lines = []
        for rt, rd in self.config.roles.items():
            resp = "、".join(rd.responsibilities[:3])
            lines.append(
                f"- {rt.value}（{rd.name}，Level {rd.level}）：{resp}"
            )
        return "\n".join(lines)
