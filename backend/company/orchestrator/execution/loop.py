"""執行-審查迴圈 mixin：平行執行就緒工作項並逐個審查。"""

from __future__ import annotations

import asyncio
import logging

from backend.company.state import WorkItemStatus

from .._base import OrchestratorBase

logger = logging.getLogger("backend.company.orchestrator.execution")


class _ExecutionLoopMixin(OrchestratorBase):
    """執行-審查主迴圈與 Semaphore 並行包裝。"""

    # ═══════════════════════════════════════════════════════════
    # 階段 2：執行-審查迴圈
    # ═══════════════════════════════════════════════════════════

    async def _execute_review_loop(self, goal: str) -> None:
        """執行-審查主迴圈：平行執行就緒工作項（Semaphore 限制並行數），逐個審查。"""
        max_rounds = self.config.max_review_rounds

        while self.work_items.has_work_remaining():
            # 取消檢查點：每輪迴圈開始時
            if self._check_cancel():
                logger.info("執行迴圈偵測到取消請求，中止")
                return

            ready_items = self.work_items.get_ready_items()

            if not ready_items:
                # 檢查是否有阻塞的工作項
                blocked = self.work_items.get_blocked_by_deps()
                if blocked:
                    logger.warning(
                        "%d 個工作項因依賴未滿足而阻塞",
                        len(blocked),
                    )
                # 檢查是否全部完成
                if self.work_items.is_all_done():
                    break
                # 死鎖檢測：無就緒項、無執行中、無審查中項目時，
                # 剩餘工作項全部處於 blocked/rework 等無法推進狀態，
                # 繼續等待只會無限空轉 → 直接退出迴圈
                active_statuses = {
                    WorkItemStatus.EXECUTING,
                    WorkItemStatus.IN_REVIEW,
                    WorkItemStatus.REWORK,
                    WorkItemStatus.READY,
                }
                has_active = any(
                    item.status in active_statuses
                    for item in self.work_items.list_all()
                )
                if not has_active:
                    logger.warning(
                        "無可推進的工作項（全部阻塞或完成），退出執行迴圈"
                    )
                    break
                # 等待（實際場景中可能有非同步事件）
                await asyncio.sleep(0.1)
                continue

            # 自適應並發調整（優化 #6）
            self._adjust_concurrency()

            # 平行執行就緒工作項（Semaphore 限制並行數）
            self._log("parallel_execute", {
                "count": len(ready_items),
                "max_parallel": self._max_parallel,
            })
            tasks = [
                self._execute_with_semaphore(goal, item)
                for item in ready_items
            ]
            await asyncio.gather(*tasks)

            # 取消檢查點：gather 返回後立即早退，不再審查剛完成的項目
            if self._check_cancel():
                logger.info("執行迴圈偵測到取消請求（gather 後），中止")
                return

            # 審查每個剛完成的工作項
            for item in ready_items:
                # 重新取得最新狀態
                current = self.work_items.get(item.id)
                if current and current.status == WorkItemStatus.IN_REVIEW:
                    await self._review_item(goal, current, max_rounds)

    async def _execute_with_semaphore(self, goal: str, item) -> None:
        """用 Semaphore 包裝 _execute_single_item，限制並行數。"""
        async with self._worker_semaphore:
            await self._execute_single_item(goal, item)
