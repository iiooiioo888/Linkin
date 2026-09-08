"""公司運行時事件系統。

提供生命週期事件定義與非阻塞事件匯流排，
讓外部程式可以監聽公司運行時的關鍵節點。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

# 事件監聽器簽章：(event, data) -> None
EventListener = Callable[["CompanyEvent", dict[str, Any]], None]


# ═══════════════════════════════════════════════════════════════
# 生命週期事件
# ═══════════════════════════════════════════════════════════════

class CompanyEvent(str, Enum):
    """公司運行時生命週期事件。

    覆蓋完整的執行流程：啟動 → 分解 → 執行 → 審查 → 整合 → 完成。
    """

    # ── 公司層級 ──
    COMPANY_START = "company_start"          # 公司開始執行
    COMPANY_DONE = "company_done"            # 公司執行完成
    PHASE_CHANGE = "phase_change"            # 階段切換（decompose/execute/synthesize/final_review）
    DECOMPOSE_DONE = "decompose_done"        # 任務分解完成（含策略與執行計劃）

    # ── 工作項層級 ──
    WORK_ITEM_START = "work_item_start"      # 工作項開始執行
    WORK_ITEM_DONE = "work_item_done"        # 工作項執行完成（提交審查）
    WORK_ITEM_ERROR = "work_item_error"      # 工作項執行失敗
    WORK_ITEM_RETRY = "work_item_retry"      # 工作項重試中
    WORK_ITEM_ESCALATE = "work_item_escalate"  # 工作項升級到上級角色
    GRILL_RAISED = "grill_raised"              # L2 對上級發起強制質詢
    GRILL_RESOLVED = "grill_resolved"          # 質詢已由上層裁決
    USER_DECISION_NEEDED = "user_decision_needed"  # 熱馬桶圈到達 L5，等待用戶
    RAHO_TIMEOUT = "raho_timeout"              # 決策 TTL 到期自動裁決

    # ── 工具調用層級（Agent 工具閉環）──
    TOOL_CALL = "tool_call"                  # Agent 發起工具調用
    TOOL_RESULT = "tool_result"              # 工具執行結果回傳

    # ── 審查層級 ──
    REVIEW_PASS = "review_pass"              # 審查通過
    REVIEW_REWORK = "review_rework"          # 審查不通過，退回修改
    REVIEW_FORCE_DONE = "review_force_done"  # 達到最大審查輪數，強制完成（降級）
    FINAL_REVIEW_DEGRADED = "final_review_degraded"  # 最終審查異常，自動通過（降級）

    # ── 預算層級 ──
    BUDGET_WARNING = "budget_warning"        # 預算警告（達到 warn_threshold）
    BUDGET_DEGRADE = "budget_degrade"        # 預算降級（達到 degrade_threshold）


# ═══════════════════════════════════════════════════════════════
# 事件匯流排
# ═══════════════════════════════════════════════════════════════

class EventBus:
    """非阻塞事件匯流排。

    註冊監聽器後，在關鍵節點呼叫 emit() 分發事件。
    監聽器中的異常不會中斷主流程。

    使用範例：
        >>> bus = EventBus()
        >>> bus.on(lambda event, data: print(f"{event.value}: {data}"))
        >>> bus.emit(CompanyEvent.WORK_ITEM_START, {"title": "任務A"})
    """

    def __init__(self):
        self._listeners: list[EventListener] = []

    def on(self, listener: EventListener) -> None:
        """註冊事件監聽器。

        Args:
            listener: 回呼函數，簽章為 (event: CompanyEvent, data: dict) -> None
        """
        self._listeners.append(listener)

    def off(self, listener: EventListener) -> None:
        """移除事件監聽器。"""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def emit(self, event: CompanyEvent, data: dict[str, Any] | None = None) -> None:
        """分發事件給所有監聽器（非阻塞，異常安全）。

        Args:
            event: 事件類型
            data: 事件附帶資料
        """
        payload = data or {}
        for listener in self._listeners:
            try:
                listener(event, payload)
            except Exception:
                logger.debug(
                    "事件監聽器異常（已忽略）：event=%s", event.value, exc_info=True
                )

    def clear(self) -> None:
        """清除所有監聽器。"""
        self._listeners.clear()

    @property
    def listener_count(self) -> int:
        """當前監聽器數量。"""
        return len(self._listeners)