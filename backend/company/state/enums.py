"""工作項與預算列舉（自 backend.company.state 抽出）。

WorkItemStatus／VALID_TRANSITIONS／BudgetTier／Priority。
"""

from __future__ import annotations

from enum import Enum

# ═══════════════════════════════════════════════════════════════
# 工作項狀態機
# ═══════════════════════════════════════════════════════════════

class WorkItemStatus(str, Enum):
    """工作項生命週期狀態。

    流轉路徑：
      PLANNING → READY → EXECUTING → IN_REVIEW
        → REWORK → EXECUTING（迴圈）
        → DONE
        → BLOCKED（可由任何狀態轉入，解除後回到原狀態）
    """

    PLANNING = "planning"        # 規劃中：Manager 正在拆解/定義
    READY = "ready"              # 就緒：可被領取執行
    EXECUTING = "executing"      # 執行中：Worker 正在處理
    IN_REVIEW = "in_review"      # 審查中：Reviewer 正在評估
    REWORK = "rework"            # 需修改：審查不通過，退回重做
    DONE = "done"                # 已完成
    BLOCKED = "blocked"          # 阻塞：等待外部依賴或決策
    CANCELLED = "cancelled"      # 已取消：使用者中止任務時未完成的項目（終態）


# 合法的狀態轉換
VALID_TRANSITIONS: dict[WorkItemStatus, set[WorkItemStatus]] = {
    WorkItemStatus.PLANNING:   {WorkItemStatus.READY, WorkItemStatus.BLOCKED,
                                WorkItemStatus.CANCELLED},
    WorkItemStatus.READY:      {WorkItemStatus.EXECUTING, WorkItemStatus.BLOCKED,
                                WorkItemStatus.CANCELLED},
    WorkItemStatus.EXECUTING:  {WorkItemStatus.IN_REVIEW, WorkItemStatus.BLOCKED,
                                WorkItemStatus.CANCELLED},
    WorkItemStatus.IN_REVIEW:  {WorkItemStatus.DONE, WorkItemStatus.REWORK,
                                WorkItemStatus.BLOCKED, WorkItemStatus.CANCELLED},
    WorkItemStatus.REWORK:     {WorkItemStatus.EXECUTING, WorkItemStatus.BLOCKED,
                                WorkItemStatus.CANCELLED},
    WorkItemStatus.DONE:       set(),  # 終態
    WorkItemStatus.BLOCKED:    {WorkItemStatus.READY, WorkItemStatus.EXECUTING,
                                WorkItemStatus.IN_REVIEW, WorkItemStatus.REWORK,
                                WorkItemStatus.CANCELLED},
    WorkItemStatus.CANCELLED:  set(),  # 終態
}


# ═══════════════════════════════════════════════════════════════
# 預算層級
# ═══════════════════════════════════════════════════════════════

class BudgetTier(str, Enum):
    """模型路由層級，決定使用哪個模型處理任務。

    - critical:  關鍵決策、複雜程式碼生成（最貴模型）
    - reasoning: 多步驟規劃、邏輯推理
    - routine:   日常對話、簡單任務
    - summary:   摘要、分類（最便宜模型）
    """

    CRITICAL = "critical"
    REASONING = "reasoning"
    ROUTINE = "routine"
    SUMMARY = "summary"


# ═══════════════════════════════════════════════════════════════
# 工作項優先級
# ═══════════════════════════════════════════════════════════════

class Priority(int, Enum):
    """工作項優先級。數值越小優先級越高。"""

    CRITICAL = 0   # 關鍵路徑，必須最先完成
    HIGH = 1       # 高優先級
    MEDIUM = 2     # 中優先級（預設）
    LOW = 3        # 低優先級，可延後
