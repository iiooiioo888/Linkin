"""任務生命週期 mixin（LifecycleMixin）：建立、查詢、啟動、取消、事件廣播、結束與存檔。"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from backend.core import nodes
from backend.core.post_company_reflect import task_finish_reflect_mode
from backend.core.unified_pipeline import resolve_task_effective_query
from backend.services.archiver import save_session_archive_sync
from backend.services.task_broadcaster import task_broadcaster

from ._base import CANCEL_GRACE_SECONDS, MAX_EVENTS_PER_TASK, MAX_TASKS, TaskManagerBase
from ._compat import load_checkpoint
from .models import TaskRecord

logger = logging.getLogger(__name__)


class LifecycleMixin(TaskManagerBase):
    """建立、查詢、啟動、取消、事件廣播、結束與存檔。"""

    # ── 公開 API ──

    def create_task(
        self, query: str, strategy: str, template: str, options: dict[str, Any] | None = None
    ) -> TaskRecord:
        from backend.tenant.context import current_tenant_user

        task_id = uuid.uuid4().hex[:12]
        record = TaskRecord(task_id, query, strategy, template)
        record.user_id = current_tenant_user()
        record.options = options or {}
        record.query = resolve_task_effective_query(query, record.options)
        self.tasks[task_id] = record
        self._persist(record)
        # 簡單淘汰：超出上限時刪除最舊的已結束任務（取消／中斷也算，否則永遠清不掉）
        if len(self.tasks) > MAX_TASKS:
            finished = [
                t for t in self.tasks.values()
                if t.status in ("completed", "failed", "cancelled", "interrupted")
            ]
            overflow = len(self.tasks) - MAX_TASKS
            for t in sorted(finished, key=lambda x: x.created_at)[:overflow]:
                self.tasks.pop(t.task_id, None)
        return record

    def resume_task(self, task_id: str) -> tuple[bool, str]:
        """斷點續跑：從檢查點恢復任務執行。

        僅支援走公司運行時路徑的任務（有 orchestrator checkpoint）。

        Returns:
            (success, message)
        """
        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if record.status == "running":
            return False, "任務正在執行中"
        if record.status == "completed":
            return False, "任務已完成，無需恢復"
        if record.resolved_path != "company":
            return False, "僅公司運行時路徑的任務支持斷點續跑"
        if not record.resumable:
            return False, "此任務沒有可用檢查點，無法恢復"

        # 檢查是否有檢查點
        checkpoint = load_checkpoint(task_id)
        if checkpoint is None:
            return False, "找不到檢查點，無法恢復"

        # 重置任務狀態
        record.status = "pending"
        record.error = ""
        record.cancel_requested = False
        record.resumable = False
        self._add_event(record, "resume_requested", {"checkpoint_phase": checkpoint.get("phase", "")})
        self._persist(record)

        # 啟動恢復執行
        asyncio.create_task(self._resume_company_task(record, checkpoint))
        logger.info("任務 %s 已啟動斷點續跑", task_id)
        return True, "已啟動斷點續跑"

    def get_task(self, task_id: str, *, skip_tenant_check: bool = False) -> TaskRecord | None:
        record = self.tasks.get(task_id)
        if record is None:
            record = self._load_from_redis(task_id)
            if record is not None:
                self.tasks[task_id] = record
        if record is None:
            return None
        from backend.company.execution_gate import expire_budget_if_needed

        if expire_budget_if_needed(record):
            self._persist(record)
        if skip_tenant_check:
            return record
        from backend.tenant.tasks import task_visible_for_tenant

        if not task_visible_for_tenant(record):
            return None
        return record

    def start_task(self, record: TaskRecord) -> None:
        """以背景任務方式啟動（統一管線）。公司路徑必須先鎖上預算方案。"""
        if record.resolved_path == "company":
            from backend.company.execution_gate import require_user_approved

            require_user_approved(record.task_id)
        task = asyncio.create_task(self._run_unified_task(record))
        self._running_tasks[record.task_id] = task

    def start_task_from_thread(self, record: TaskRecord) -> None:
        """從無 event loop 的執行緒／行程啟動任務（MCP server 用）。

        當前執行緒有 loop 就直接啟動；否則交給主 loop（lifespan 註冊）。
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = self._loop
            if loop is not None and loop.is_running():
                loop.call_soon_threadsafe(self.start_task, record)
                return
            raise
        self.start_task(record)

    def cancel_task(self, task_id: str) -> tuple[bool, str]:
        """請求取消任務。

        設置取消標誌，執行迴圈會在下一個檢查點中止；公司路徑同時把
        未完成工作項標記為 CANCELLED 終態。若寬限期（CANCEL_GRACE_SECONDS）
        內執行迴圈仍未結束（例如卡在長時間 LLM 呼叫），強制中斷 asyncio
        任務，避免「取消中…」永久卡住。
        已完成/已失敗/已取消的任務無法取消。

        Returns:
            (success, message)
        """
        record = self.get_task(task_id)
        if record is None:
            return False, "任務不存在"
        if record.status in ("completed", "failed", "cancelled", "interrupted"):
            return False, f"任務已結束（{record.status}），無法取消"
        record.cancel_requested = True
        self._add_event(record, "cancel_requested", {})
        self._persist(record)
        # 公司運行時：傳遞取消請求到 orchestrator（會同時終結未完成工作項）
        orchestrator = self._orchestrators.get(task_id)
        if orchestrator is not None:
            orchestrator.request_cancel()
        # 寬限期後強制中斷（協作式取消失敗時的保險絲）
        running = self._running_tasks.get(task_id)
        if running is not None and not running.done():
            asyncio.get_running_loop().call_later(
                CANCEL_GRACE_SECONDS, self._force_cancel_if_still_running, task_id,
            )
        logger.info("任務 %s 已請求取消", task_id)
        return True, "已請求取消，任務將在下一個檢查點中止"

    def _force_cancel_if_still_running(self, task_id: str) -> None:
        """寬限期保險絲：任務仍在跑就強制 cancel 其 asyncio Task。

        _run_unified_task 的 CancelledError 分支會把狀態收尾為 cancelled。
        """
        record = self.tasks.get(task_id)
        running = self._running_tasks.get(task_id)
        if record is None or running is None or running.done():
            return
        if not record.cancel_requested or record.status not in ("running", "pending"):
            return
        logger.warning("任務 %s 取消寬限期（%ds）已過，強制中斷", task_id, CANCEL_GRACE_SECONDS)
        running.cancel()

    def _check_cancelled(self, record: TaskRecord) -> bool:
        """檢查任務是否已被請求取消，若是則標記為 cancelled。"""
        if record.cancel_requested and record.status == "running":
            record.status = "cancelled"
            record.error = "任務已被使用者取消"
            self._set_phase(record, "cancelled")
            return True
        return False

    # ── 事件記錄輔助（每次變更都持久化） ──

    def _set_phase(self, record: TaskRecord, phase: str, **data: Any) -> None:
        record.phase = phase
        record.events.append({
            "ts": time.time(),
            "event": "phase_change",
            "data": {"phase": phase, **data},
        })
        self._schedule_persist(record, force=True)
        # WebSocket 实时推送（fire-and-forget）
        self._broadcast_event(record.task_id, "phase_change", {"phase": phase, **data})

    def _broadcast_event(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        """Fire-and-forget 广播事件到 WebSocket 订阅者。"""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(task_broadcaster.broadcast(task_id, event, data))
        except RuntimeError:
            # 无事件循环时跳过广播（降级为轮询）
            pass

    def _add_event(self, record: TaskRecord, event: str, data: dict[str, Any]) -> None:
        record.events.append({"ts": time.time(), "event": event, "data": data})
        if len(record.events) > MAX_EVENTS_PER_TASK:
            record.events = record.events[-MAX_EVENTS_PER_TASK:]
        force = event in ("cancel_requested", "resume_requested") or event == "phase_change"
        self._schedule_persist(record, force=force)
        # WebSocket 实时推送
        self._broadcast_event(record.task_id, event, data)

    def _evaluation_event_data(self, state: dict[str, Any], **fields: Any) -> dict[str, Any]:
        data = dict(fields)
        data.update(nodes.length_gate_event_fields(state))
        return data

    def _sync_length_gate_from_state(self, record: TaskRecord, state: dict[str, Any]) -> None:
        compliance = state.get("length_compliance")
        record.length_compliance = dict(compliance) if isinstance(compliance, dict) else None
        record.length_warning = bool(state.get("length_warning"))
        record.length_refused = bool(state.get("length_refused"))

    def _length_gate_finish_payload(self, record: TaskRecord) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if isinstance(record.length_compliance, dict) and record.length_compliance:
            payload["length_compliance"] = record.length_compliance
        if record.length_warning:
            payload["length_warning"] = True
        if record.length_refused:
            payload["length_refused"] = True
        return payload

    def _finish(self, record: TaskRecord) -> None:
        """任務結束（完成/失敗）：持久化並寫入 JSONL 存檔。"""
        if record.finished_at is None:
            record.finished_at = time.time()
        self._cancel_scheduled_persist(record.task_id)
        self._persist_event_counters.pop(record.task_id, None)
        self._persist(record)
        # WebSocket 推送任务完成/失败事件
        finish_data: dict[str, Any] = {
            "status": record.status,
            "score": record.score,
            "iteration": record.iteration,
            "error": record.error,
            "complexity": record.task_complexity,
            "reflection_rounds_used": record.iteration,
            "reflection_rounds_max": record.reflection_rounds_max,
            **self._length_gate_finish_payload(record),
        }
        finish_data["reflect_mode"] = task_finish_reflect_mode(
            record.resolved_path,
            applied_mode=record.post_company_reflect_applied,
        )
        self._broadcast_event(record.task_id, "task_finished", finish_data)
        if record.status == "completed":
            self._archive_task(record)

    def _archive_task(self, record: TaskRecord) -> None:
        """將任務結果寫入 JSONL 對話存檔（與 /chat 同一管線）。"""
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": record.answer,
            "final_answer": record.answer,
            "score": record.score,
            "iteration": record.iteration,
            "reflections": [],
            "retrieved_memories": [],
            "archive_metadata": {
                "source": "task_api",
                "strategy": record.strategy,
                "resolved_path": record.resolved_path,
                "template": record.template,
            },
        }
        try:
            save_session_archive_sync(state, record.task_id)
        except Exception as exc:
            logger.warning("任務存檔失敗（不影響結果）：%s", exc)
