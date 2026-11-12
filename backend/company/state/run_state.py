"""公司運行時狀態（自 backend.company.state 抽出）。

CompanyRunState：單次運行的即時狀態與看板／序列化。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import CompanyConfig
from .enums import BudgetTier, WorkItemStatus
from .models import WorkItem
from .role import assignee_token

# ═══════════════════════════════════════════════════════════════
# 公司運行時狀態
# ═══════════════════════════════════════════════════════════════

@dataclass
class CompanyRunState:
    """公司單次運行的即時狀態。"""

    config: CompanyConfig = field(default_factory=CompanyConfig)
    goal: str = ""                                  # 公司目標
    work_items: dict[str, WorkItem] = field(default_factory=dict)
    run_log: list[dict[str, Any]] = field(default_factory=list)

    # 預算追蹤
    task_spent: float = 0.0
    session_spent: float = 0.0
    monthly_spent: float = 0.0
    active_tier: BudgetTier = BudgetTier.ROUTINE

    # 執行統計
    total_items: int = 0
    completed_items: int = 0
    review_rounds: int = 0

    def get_kanban(self) -> dict[WorkItemStatus, list[WorkItem]]:
        """回傳當前看板狀態。"""
        board: dict[WorkItemStatus, list[WorkItem]] = {
            s: [] for s in WorkItemStatus
        }
        for item in self.work_items.values():
            board[item.status].append(item)
        return board

    def get_ready_items(self) -> list[WorkItem]:
        """取得所有就緒可執行的工作項（依賴已滿足）。"""
        done_ids = {
            wid for wid, item in self.work_items.items()
            if item.status == WorkItemStatus.DONE
        }
        ready = []
        for item in self.work_items.values():
            if item.status != WorkItemStatus.READY:
                continue
            if all(dep in done_ids for dep in item.depends_on):
                ready.append(item)
        return ready

    def to_dict(self) -> dict[str, Any]:
        """序列化為字典（供存檔/API 回應）。"""
        return {
            "goal": self.goal,
            "work_items": {
                wid: {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status.value,
                    "assignee": assignee_token(item.assignee),
                    "depends_on": item.depends_on,
                    "tier": item.tier.value,
                    "actual_cost": item.actual_cost,
                    "created_at": item.created_at,
                    "completed_at": item.completed_at,
                }
                for wid, item in self.work_items.items()
            },
            "budget": {
                "task_spent": round(self.task_spent, 4),
                "task_limit": self.config.budget.task_limit_usd,
                "session_spent": round(self.session_spent, 4),
                "session_limit": self.config.budget.session_limit_usd,
                "monthly_spent": round(self.monthly_spent, 4),
                "monthly_limit": self.config.budget.monthly_limit_usd,
                "active_tier": self.active_tier.value,
            },
            "progress": {
                "total": self.total_items,
                "completed": self.completed_items,
                "review_rounds": self.review_rounds,
            },
        }
