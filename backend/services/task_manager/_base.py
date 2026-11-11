"""共享基底：模組常數、TaskManager 實例屬性與跨 mixin 方法介面宣告。

對外 import 路徑仍是 backend.services.task_manager.TaskManager／task_manager；
此檔案只提供型別檢查與 mixin 之間的共同介面，實作仍在各 mixin 模組。
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any

from backend.company.orchestrator import CompanyOrchestrator
from backend.services.trace_logger import TraceLogger

from .models import TaskRecord

if TYPE_CHECKING:
    import redis


# 任務記憶體上限（避免無限增長）
MAX_TASKS = 100
MAX_EVENTS_PER_TASK = 200

# 取消寬限期（秒）：協作式取消（檢查點）失效後強制中斷 asyncio 任務
CANCEL_GRACE_SECONDS = 45

# Redis 持久化參數
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
TASK_KEY_PREFIX = "evoloop:task:"
TASK_TTL_SECONDS = 7 * 86400
COMPANY_PERSIST_DEBOUNCE_SEC = float(os.getenv("EVOL_TASK_PERSIST_DEBOUNCE_SEC", "0.35"))
COMPANY_PERSIST_EVERY_N = max(1, int(os.getenv("EVOL_TASK_PERSIST_EVERY_N", "8")))


class TaskManagerBase:
    """TaskManager 共享介面：實例屬性與方法 stub（實作在 mixin）。"""

    tasks: dict[str, TaskRecord]
    _redis: redis.Redis | None
    _redis_failed: bool
    _orchestrators: dict[str, CompanyOrchestrator]
    _running_tasks: dict[str, asyncio.Task]
    _loop: asyncio.AbstractEventLoop | None
    _persist_pending: dict[str, asyncio.TimerHandle]
    _persist_event_counters: dict[str, int]

    def _get_redis(self) -> redis.Redis | None:
        raise NotImplementedError

    def _persist(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def _should_batch_persist(self, record: TaskRecord) -> bool:
        raise NotImplementedError

    def _cancel_scheduled_persist(self, task_id: str) -> None:
        raise NotImplementedError

    def _flush_persist(self, task_id: str) -> None:
        raise NotImplementedError

    def _schedule_persist(self, record: TaskRecord, *, force: bool = False) -> None:
        raise NotImplementedError

    def _load_from_redis(self, task_id: str) -> TaskRecord | None:
        raise NotImplementedError

    def rehydrate(self) -> int:
        raise NotImplementedError

    def delete_task_record(self, task_id: str) -> bool:
        raise NotImplementedError

    def iter_all_records(self) -> list[TaskRecord]:
        raise NotImplementedError

    def create_task(
        self, query: str, strategy: str, template: str, options: dict[str, Any] | None = None
    ) -> TaskRecord:
        raise NotImplementedError

    def resume_task(self, task_id: str) -> tuple[bool, str]:
        raise NotImplementedError

    def get_task(self, task_id: str, *, skip_tenant_check: bool = False) -> TaskRecord | None:
        raise NotImplementedError

    def start_task(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def start_budget_draft(self, record: TaskRecord) -> None:
        raise NotImplementedError

    async def _draft_company_budget(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def decide_budget(self, task_id: str, action: str, note: str = "") -> tuple[bool, str]:
        raise NotImplementedError

    def update_budget_lines(self, task_id: str, lines: list[dict[str, Any]]) -> tuple[bool, str]:
        raise NotImplementedError

    def update_confirmation_draft(
        self,
        task_id: str,
        *,
        new_seats: list[dict[str, Any]] | None = None,
        field_writes: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        raise NotImplementedError

    def apply_seat_override(
        self,
        task_id: str,
        role_id: str,
        *,
        system_prompt: str | None = None,
        tools_allowed: list[str] | None = None,
    ) -> tuple[bool, str]:
        raise NotImplementedError

    def retry_field_writes(self, task_id: str, writes: list[dict[str, Any]] | None = None) -> tuple[bool, str]:
        raise NotImplementedError

    def commit_narrative(self, task_id: str, kind: str, entity: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
        raise NotImplementedError

    def _reserve_execution_billing(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def start_task_from_thread(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def cancel_task(self, task_id: str) -> tuple[bool, str]:
        raise NotImplementedError

    def _force_cancel_if_still_running(self, task_id: str) -> None:
        raise NotImplementedError

    def _check_cancelled(self, record: TaskRecord) -> bool:
        raise NotImplementedError

    def _set_phase(self, record: TaskRecord, phase: str, **data: Any) -> None:
        raise NotImplementedError

    def _broadcast_event(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _add_event(self, record: TaskRecord, event: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _evaluation_event_data(self, state: dict[str, Any], **fields: Any) -> dict[str, Any]:
        raise NotImplementedError

    def _sync_length_gate_from_state(self, record: TaskRecord, state: dict[str, Any]) -> None:
        raise NotImplementedError

    def _length_gate_finish_payload(self, record: TaskRecord) -> dict[str, Any]:
        raise NotImplementedError

    def _finish(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def _archive_task(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def _resolve_path(self, record: TaskRecord) -> str:
        raise NotImplementedError

    async def _run_unified_task(self, record: TaskRecord) -> None:
        raise NotImplementedError

    async def _run_unified_task_inner(self, record: TaskRecord) -> None:
        raise NotImplementedError

    async def _run_simple_task(self, record: TaskRecord) -> None:
        raise NotImplementedError

    def _reflection_routing_state(
        self, record: TaskRecord, state: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _reflection_max_iterations(self, record: TaskRecord, state: dict[str, Any]) -> int:
        raise NotImplementedError

    def _reflection_should_continue(
        self, record: TaskRecord, state: dict[str, Any]
    ) -> bool:
        raise NotImplementedError

    async def _run_reflection_loop(
        self, record: TaskRecord, state: dict[str, Any], tracer: TraceLogger
    ) -> None:
        raise NotImplementedError

    async def _run_post_company_reflection(
        self, record: TaskRecord, state: dict[str, Any], tracer: TraceLogger
    ) -> None:
        raise NotImplementedError

    def _attach_company_listener(
        self, record: TaskRecord, orchestrator: CompanyOrchestrator
    ) -> None:
        raise NotImplementedError

    def _save_company_checkpoint(self, record: TaskRecord, orchestrator: CompanyOrchestrator, phase: str) -> None:
        raise NotImplementedError

    async def _resume_company_task(self, record: TaskRecord, checkpoint: dict[str, Any]) -> None:
        raise NotImplementedError

    async def _run_company_task(self, record: TaskRecord) -> None:
        raise NotImplementedError
