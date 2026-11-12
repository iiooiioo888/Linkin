"""工作項模型（自 backend.company.state 抽出）。

WorkItem／RetryConfig dataclass。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .enums import VALID_TRANSITIONS, BudgetTier, Priority, WorkItemStatus
from .role_types import RoleType

# ═══════════════════════════════════════════════════════════════
# 工作項
# ═══════════════════════════════════════════════════════════════

@dataclass
class WorkItem:
    """單一工作項：可被指派、執行、審查的任務單元。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    status: WorkItemStatus = WorkItemStatus.PLANNING
    assignee: RoleType | str | None = None        # 內建席位或目錄自訂 id
    created_by: RoleType | None = None            # 創建者
    depends_on: list[str] = field(default_factory=list)  # 依賴的工作項 ID
    artifacts: dict[str, Any] = field(default_factory=dict)  # 產出物
    feedback: list[dict[str, Any]] = field(default_factory=list)  # 審查回饋
    tier: BudgetTier = BudgetTier.ROUTINE         # 所需模型層級
    priority: Priority = Priority.MEDIUM            # 優先級
    estimated_cost: float = 0.0                   # 預估成本
    actual_cost: float = 0.0                      # 實際成本
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def transition_to(self, new_status: WorkItemStatus) -> bool:
        """嘗試狀態轉換，回傳是否成功。"""
        if new_status in VALID_TRANSITIONS.get(self.status, set()):
            self.status = new_status
            self.updated_at = datetime.now(timezone.utc).isoformat()
            if new_status == WorkItemStatus.DONE:
                self.completed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# 預算設定
# ═══════════════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    """錯誤重試與升級配置。"""

    max_retries: int = 3                    # 最大重試次數
    retry_backoff_base: float = 1.0         # 退避基礎秒數（指數增長）
    enable_escalation: bool = True          # 是否啟用角色升級
    deadline_seconds: float = 300.0         # 單一工作項超時秒數（0=不限）
