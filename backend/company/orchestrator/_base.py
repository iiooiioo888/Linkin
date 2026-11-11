"""共享基底：CompanyOrchestrator 的實例屬性與跨 mixin 方法介面宣告。

對外 import 路徑仍是 backend.company.orchestrator.CompanyOrchestrator；
此檔案只提供型別檢查與 mixin 之間的共同介面，實作仍在各 mixin 模組。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.company.budget import BudgetManager
from backend.company.decomposer import TaskDecomposer
from backend.company.events import CompanyEvent, EventBus
from backend.company.prompts import PromptConfig
from backend.company.roles import RoleType
from backend.company.state import CompanyConfig, CompanyRunState
from backend.company.work_item import WorkItemManager
from backend.services.docker_manager import DockerManager


async def _llm_thread(fn, *args, **kwargs):
    """在 worker 執行緒跑同步 LLM 呼叫（不凍結 event loop）。

    StopIteration 不得進入 Future（asyncio 會炸掉 callback 並讓等待方
    永久懸掛）：mock side_effect 耗盡等場景統一轉成 RuntimeError。
    """
    def _run():
        try:
            return fn(*args, **kwargs)
        except StopIteration as exc:
            raise RuntimeError(f"LLM 呼叫序列耗盡（StopIteration）：{exc}") from exc

    return await asyncio.to_thread(_run)


class OrchestratorBase:
    """CompanyOrchestrator 共享介面：實例屬性與方法 stub（實作在 mixin）。"""

    config: CompanyConfig
    budget: BudgetManager
    work_items: WorkItemManager
    _run_state: CompanyRunState | None
    _run_log: list[dict[str, Any]]
    _run_id: str | None
    prompt_config: PromptConfig
    events: EventBus
    decomposer: TaskDecomposer
    _max_parallel: int
    _worker_semaphore: asyncio.Semaphore
    _concurrency_stats: dict[str, Any]
    docker: DockerManager | None
    cancel_requested: bool
    _campaign: dict[str, Any]
    _battle_plan: dict[str, Any]
    _commander: dict[str, Any]
    tracer: Any
    task_id: str

    def request_cancel(self) -> None:
        raise NotImplementedError

    def _check_cancel(self) -> bool:
        raise NotImplementedError

    def _adjust_concurrency(self) -> None:
        raise NotImplementedError

    async def execute(
        self,
        goal: str,
        ticket: dict[str, Any] | None = None,
        precomputed_planner: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def get_kanban(self) -> dict:
        raise NotImplementedError

    def get_budget_status(self) -> dict:
        raise NotImplementedError

    def _raho_snapshot(self) -> dict[str, Any]:
        raise NotImplementedError

    def _emit_user_pending(self, pending, *, title: str = "", phase: str = "") -> None:
        raise NotImplementedError

    def _allowed_tools_for(self, item) -> list[str] | None:
        raise NotImplementedError

    async def _maybe_resolve_mgp(
        self,
        goal: str,
        item,
        role_type: RoleType,
        raw: str,
        prompt: str,
        system_prompt: str,
        model: str,
        llm_opts: dict | None,
        timeout_s: float,
        seat: dict | None = None,
    ) -> tuple[str, str]:
        raise NotImplementedError

    def _apply_escalation_patch(self, item, resolved: dict) -> None:
        raise NotImplementedError

    def to_checkpoint(self, goal: str = "") -> dict[str, Any]:
        raise NotImplementedError

    def _restore_from_checkpoint(self, data: dict[str, Any]) -> None:
        raise NotImplementedError

    async def _execute_review_loop(self, goal: str) -> None:
        raise NotImplementedError

    async def _execute_with_semaphore(self, goal: str, item) -> None:
        raise NotImplementedError

    async def _execute_with_tool_loop(
        self,
        prompt: str,
        system: str,
        model: str | None,
        role_value: str,
        item,
        max_tool_steps: int = 3,
        llm_kwargs: dict | None = None,
        seat: dict | None = None,
    ) -> str:
        raise NotImplementedError

    def _record_seat_io(
        self,
        seat: dict | None,
        item,
        role_value: str,
        *,
        prompt: str,
        system: str,
        model: str | None,
        response: str,
        step: int,
        llm_kwargs: dict | None = None,
        duration_ms: float | None = None,
        tool_steps: int = 0,
        final: bool = True,
        error: str = "",
        degraded: bool = False,
        cost_usd: float | None = None,
    ) -> None:
        raise NotImplementedError

    def _seat_meta(
        self,
        role_type: RoleType,
        *,
        kind: str,
        phase: str,
        role_label: str = "",
        attempt: int = 0,
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def _execute_single_item(self, goal: str, item) -> None:
        raise NotImplementedError

    def _task_spec_from_item(self, item) -> dict[str, Any]:
        raise NotImplementedError

    async def _run_l1_inspect(self, goal: str, item, review_round: int, max_rounds: int):
        raise NotImplementedError

    async def _review_item(self, goal: str, item, max_rounds: int) -> None:
        raise NotImplementedError

    async def _rework_item(self, goal: str, item, feedback: str) -> None:
        raise NotImplementedError

    async def _review_and_synthesize(self, goal: str) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError

    async def _synthesize(self, goal: str) -> str:
        raise NotImplementedError

    async def _manager_final_review(self, goal: str, final_output: str) -> dict:
        raise NotImplementedError

    def _build_context(self, item) -> str:
        raise NotImplementedError

    def _collect_artifacts(self) -> str:
        raise NotImplementedError

    def _count_review_rounds(self) -> int:
        raise NotImplementedError

    def _log(
        self,
        event: str,
        data: dict[str, Any],
        *,
        degraded: bool = False,
        level: int = logging.DEBUG,
    ) -> None:
        raise NotImplementedError

    def _persist_bus_event(self, event: CompanyEvent, data: dict[str, Any]) -> None:
        raise NotImplementedError

    def _check_docker_budget(self) -> tuple[bool, str]:
        raise NotImplementedError

    def _apply_docker_optimization(self, suggestions: list[dict[str, Any]]) -> dict[str, Any]:
        raise NotImplementedError

    def _build_from_battle_plan(self, plan: dict[str, Any]) -> list:
        raise NotImplementedError

    def _error_result(self, message: str) -> dict[str, Any]:
        raise NotImplementedError

    @staticmethod
    def _catalog_tool_filter(role_value: str, item=None) -> tuple[bool, list[str] | None]:
        raise NotImplementedError

    def _get_docker_tools_for_role(self, role_type: RoleType, item=None) -> str:
        raise NotImplementedError

    def execute_docker_request(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        raise NotImplementedError

    def get_docker_status(self) -> dict[str, Any]:
        raise NotImplementedError
