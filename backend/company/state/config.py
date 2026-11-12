"""公司配置（自 backend.company.state 抽出）。

CompanyConfig：組織架構、角色、預算、提示詞與重試設定。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.company.prompts import PromptConfig

from .budget import BudgetConfig
from .models import RetryConfig
from .role import RoleDefinition
from .role_types import ROLE_LEVEL, RoleType

# ═══════════════════════════════════════════════════════════════
# 公司配置
# ═══════════════════════════════════════════════════════════════

@dataclass
class CompanyConfig:
    """公司配置：組織架構、角色、層級樹、預算、執行策略。"""

    name: str = "EvoLoop 公司"
    description: str = ""
    roles: dict[RoleType, RoleDefinition] = field(default_factory=dict)
    budget: BudgetConfig = field(default_factory=BudgetConfig)

    # 層級關係
    org_chart: dict[RoleType, list[RoleType]] = field(default_factory=dict)
    # org_chart[MANAGER] = [TECH_LEAD, ARCHITECT]
    # org_chart[TECH_LEAD] = [FRONTEND_LEAD, BACKEND_LEAD, TEST_LEAD]

    # 執行策略
    max_parallel_workers: int = 4
    max_review_rounds: int = 3
    auto_approve_risk: str = "medium"

    # 提示詞配置（可完全自定義）
    prompt_config: PromptConfig = field(default_factory=PromptConfig)

    # 重試與錯誤處理配置
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # 任務分解策略
    decompose_strategy: str = "auto"  # auto | hierarchical | flat
    enable_parallel_decompose: bool = True  # 是否允許 LLM 規劃並發執行

    def get_subordinates(self, role: RoleType) -> list[RoleType]:
        """取得某角色的直屬下級。"""
        return self.org_chart.get(role, [])

    def get_all_subordinates(self, role: RoleType) -> list[RoleType]:
        """遞迴取得所有下級（含間接）。"""
        result = []
        direct = self.org_chart.get(role, [])
        for sub in direct:
            result.append(sub)
            result.extend(self.get_all_subordinates(sub))
        return result

    def get_superior(self, role: RoleType) -> RoleType | None:
        """取得某角色的直屬上級。"""
        for superior, subs in self.org_chart.items():
            if role in subs:
                return superior
        return None

    def get_role_level(self, role: RoleType) -> int:
        """取得角色層級。"""
        return ROLE_LEVEL.get(role, 3)

    def build_org_tree(self) -> dict:
        """構建組織樹（供視覺化）。"""
        def _build(node: RoleType) -> dict:
            role_def = self.roles.get(node)
            return {
                "role": node.value,
                "name": role_def.name if role_def else node.value,
                "level": self.get_role_level(node),
                "children": [
                    _build(child)
                    for child in self.org_chart.get(node, [])
                ],
            }
        # 找根節點（Level 0）
        roots = [r for r in self.roles if self.get_role_level(r) == 0]
        if not roots:
            roots = [next(iter(self.roles))] if self.roles else []
        return {
            "company": self.name,
            "tree": [_build(root) for root in roots],
        }
