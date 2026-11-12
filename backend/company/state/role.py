"""角色定義（自 backend.company.state 抽出）。

RoleDefinition dataclass 與 assignee_token helper。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import BudgetTier
from .role_types import RoleType


@dataclass
class RoleDefinition:
    """角色定義：職責、能力、層級關係、可委派對象。"""

    role_type: RoleType
    name: str                                    # 角色名稱（如 "前端主管"）
    responsibilities: list[str] = field(default_factory=list)
    can_delegate_to: list[RoleType] = field(default_factory=list)
    reporting_to: RoleType | None = None          # 匯報對象（上級角色）
    default_tier: BudgetTier = BudgetTier.ROUTINE
    max_parallel_work: int = 3
    system_prompt: str = ""
    level: int = 3                                # 角色層級（0=最高）

    def is_superior_to(self, other: RoleType) -> bool:
        """判斷是否為 other 的上級。"""
        return other in self.can_delegate_to

    def can_manage(self, other: RoleType) -> bool:
        """判斷是否可管理 other（直接或間接）。"""
        return other in self.can_delegate_to


def assignee_token(assignee: RoleType | str | None) -> str | None:
    """內建席位用列舉值，自訂席用目錄 id。"""
    if assignee is None:
        return None
    if isinstance(assignee, RoleType):
        return assignee.value
    return str(assignee)
