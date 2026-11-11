"""統一管線執行 mixin（RuntimeMixin）：路徑解析、簡單任務執行、反思迴圈與公司後反思。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.core import nodes
from backend.core.execution_path import resolve_execution_path
from backend.core.graph import reflection_should_continue
from backend.core.reflection_limits import reflection_max_iterations, resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.integrations.recall_bridge import enhance_with_recall_context
from backend.services.trace_logger import TraceLogger, eval_trace_kwargs

from ._base import TaskManagerBase
from ._compat import enhance_with_linkin_context, enhance_with_opc_context, new_trace_logger
from .models import TaskRecord, _post_company_reflect_mode

logger = logging.getLogger(__name__)


class RuntimeMixin(TaskManagerBase):
    """路徑解析、簡單任務執行、反思迴圈與公司後反思。"""

    # ── 執行策略解析 ──

    def _resolve_path(self, record: TaskRecord) -> str:
        """依執行策略與任務內容解析實際執行路徑（與 route_by_complexity / SSE 共用）。"""
        tc = (record.task_complexity or "").strip() or None
        return resolve_execution_path(
            record.query,
            record.strategy,
            task_complexity=tc,
        )

    # ── 統一管線執行 ──

    async def _run_unified_task(self, record: TaskRecord) -> None:
        """統一模式任務執行入口：解析路徑後分派到對應子流程。"""
        from backend.billing.context import billing_enabled, billing_task_id, billing_user_id
        from backend.tenant.context import tenant_user_id

        tenant_token = tenant_user_id.set(record.user_id or "")
        billing_token = billing_user_id.set(record.user_id or billing_user_id.get())
        # 任務建單時已預扣（record.options["billing"]）；執行期綁定 task_id，
        # 讓 meter_llm 把用量記在這張單，而不是每呼叫一次再扣一次錢。
        reserved = (record.options or {}).get("billing")
        billed = bool(reserved) and billing_enabled()
        task_token = billing_task_id.set(record.task_id) if billed else None
        try:
            await self._run_unified_task_inner(record)
        finally:
            if billed:
                try:
                    from backend.billing.task_lifecycle import complete_billed_task

                    await asyncio.to_thread(complete_billed_task, record.task_id)
                except Exception:
                    logger.warning("任務 %s 結算失敗，預扣未退還", record.task_id, exc_info=True)
            if task_token is not None:
                billing_task_id.reset(task_token)
            tenant_user_id.reset(tenant_token)
            billing_user_id.reset(billing_token)

    async def _run_unified_task_inner(self, record: TaskRecord) -> None:
        record.status = "running"
        self._persist(record)

        record.task_complexity = resolve_task_complexity(record.query, record.strategy)
        preview = build_routing_preview(
            record.query,
            mode=record.strategy,
            company_template=record.template,
            task_complexity=record.task_complexity,
        )
        path = str(preview.get("path") or "simple")
        record.resolved_path = "company" if path == "opc" else path
        preview_template = preview.get("template")
        if preview_template:
            record.template = str(preview_template)
        record.reflection_rounds_max = int(preview.get("max_reflection_rounds") or 0)
        self._add_event(record, "path_resolved", preview)
        logger.info("任務 %s 解析執行路徑：%s（策略：%s）", record.task_id, record.resolved_path, record.strategy)

        try:
            if record.resolved_path == "company":
                await self._run_company_task(record)
            else:
                await self._run_simple_task(record)
        except asyncio.CancelledError:
            # 強制中斷（取消寬限期保險絲）：收尾為 cancelled，不讓任務懸在 running
            if record.status in ("running", "pending"):
                record.status = "cancelled"
                record.error = record.error or "任務已被使用者取消（強制中斷）"
                record.resumable = record.resolved_path == "company"
                self._set_phase(record, "cancelled")
                self._finish(record)
            raise
        finally:
            self._running_tasks.pop(record.task_id, None)

    # ── 簡單任務執行（單次生成 + 反思迴圈） ──

    async def _run_simple_task(self, record: TaskRecord) -> None:
        """簡單任務：記憶檢索 → OPC 上下文增強 → 生成 → 反思迴圈。"""
        tracer = new_trace_logger(record.task_id)
        opts = record.options or {}
        from backend.core.locale_prompt import normalize_ui_language

        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "history": [],
            "ui_language": normalize_ui_language(opts.get("ui_language")),
            "execution_strategy": record.strategy if record.strategy == "simple" else "auto",
            "task_complexity": record.task_complexity,
            "resolved_execution_path": record.resolved_path,
        }
        try:
            self._set_phase(record, "retrieve_memories")
            tracer.log_phase_change("retrieve_memories")
            state.update(await asyncio.to_thread(nodes.retrieve_memories, state))
            memories = state.get("retrieved_memories", [])
            if memories:
                tracer.log_context_injection(
                    source="memory", items=memories,
                    phase="retrieve_memories", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            # OPC 上下文增強（統一管線標準步驟）
            self._set_phase(record, "enhance_opc_context")
            state.update(await enhance_with_opc_context(state))
            opc_ctx = state.get("opc_context", {})
            if opc_ctx.get("summary"):
                tracer.log_context_injection(
                    source="opc", items=[opc_ctx["summary"]],
                    phase="enhance_opc_context", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            # 靈境 RAG 增強（命中世界觀關鍵詞才注入）
            self._set_phase(record, "enhance_linkin_context")
            state.update(await asyncio.to_thread(enhance_with_linkin_context, state))
            linkin_ctx = state.get("linkin_context", {}) or {}
            if linkin_ctx.get("summary"):
                tracer.log_context_injection(
                    source="linkin", items=[linkin_ctx["summary"]],
                    phase="enhance_linkin_context", query=record.query,
                )
            if self._check_cancelled(record):
                self._finish(record)
                return

            # 整合召回（MemOS / OpenViking / WeKnora，fail-open）
            self._set_phase(record, "enhance_recall_context")
            state.update(await asyncio.to_thread(enhance_with_recall_context, state))
            recall_ctx = state.get("recall_context") or {}
            if isinstance(recall_ctx, dict) and recall_ctx.get("injection"):
                tracer.log_context_injection(
                    source="recall",
                    items=[recall_ctx["injection"]],
                    phase="enhance_recall_context",
                    query=record.query,
                )
                self._add_event(record, "recall_assembled", {
                    "reason_codes": recall_ctx.get("reason_codes", []),
                    "degraded_sources": recall_ctx.get("degraded_sources", []),
                    "token_report": recall_ctx.get("token_report", {}),
                    "fragment_sources": [
                        f.get("source") for f in (recall_ctx.get("fragments") or [])
                    ],
                })
            if self._check_cancelled(record):
                self._finish(record)
                return

            self._set_phase(record, "generate")
            tracer.log_phase_change("generate")
            state.update(await asyncio.to_thread(nodes.generate_initial_answer, state))
            tracer.log_llm_call(
                prompt=state.get("generate_prompt") or f"[generate] query={record.query}",
                response=state.get("initial_answer", "")[:8000],
                model=state.get("generate_model"),
                system=state.get("generate_system"),
                phase="generate",
            )
            if self._check_cancelled(record):
                self._finish(record)
                return

            await self._run_reflection_loop(record, state, tracer)

            record.answer = str(
                state.get("final_answer") or state.get("current_answer") or ""
            )
            record.score = state.get("score")
            record.iteration = state.get("iteration", 0)
            if record.status != "cancelled" and not record.cancel_requested:
                record.status = "completed"
                tracer.log_phase_change("done")
                self._set_phase(record, "done")
        except Exception as exc:
            logger.error("簡單任務 %s 執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase=record.phase, recoverable=False)
        self._finish(record)

    # ── 反思迭代迴圈（三條路徑共用） ──

    def _reflection_routing_state(
        self, record: TaskRecord, state: dict[str, Any]
    ) -> dict[str, Any]:
        """與 LangGraph ``should_improve`` 共用：合併 execution_strategy 等路由欄位。"""
        merged = {**state, "execution_strategy": record.strategy}
        merged["task_complexity"] = record.task_complexity or state.get("task_complexity")
        merged["resolved_execution_path"] = record.resolved_path
        if record.resolved_path == "simple" and record.strategy == "simple":
            merged["task_complexity"] = "simple"
        return merged

    def _reflection_max_iterations(self, record: TaskRecord, state: dict[str, Any]) -> int:
        return reflection_max_iterations(self._reflection_routing_state(record, state))

    def _reflection_should_continue(
        self, record: TaskRecord, state: dict[str, Any]
    ) -> bool:
        return reflection_should_continue(self._reflection_routing_state(record, state))

    async def _run_reflection_loop(
        self, record: TaskRecord, state: dict[str, Any], tracer: TraceLogger
    ) -> None:
        """評估 → 反思 → 改進迭代迴圈（直到達標或達最大迭代；長度指令未消化時多跑一輪）。"""
        # 輸出長度守門：超標時把「精簡」當成額外一輪改進目標（預算由節點控管）
        state.update(await asyncio.to_thread(nodes.enforce_output_length, state))
        self._set_phase(record, "evaluate")
        tracer.log_phase_change("evaluate")
        state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
        tracer.log_evaluation(
            score=state.get("score"),
            iteration=0,
            **eval_trace_kwargs(state.get("multi_dim_evaluation")),
        )
        self._add_event(record, "evaluation", self._evaluation_event_data(
            state,
            score=state.get("score"),
            iteration=0,
        ))
        if self._check_cancelled(record):
            return

        while self._reflection_should_continue(record, state):
            if self._check_cancelled(record):
                return

            self._set_phase(record, "reflect", iteration=state.get("iteration", 0))
            tracer.log_phase_change("reflect", data={"iteration": state.get("iteration", 0)})
            state.update(await asyncio.to_thread(nodes.reflect, state))
            tracer.log_reflection(
                reflection=state.get("critique", ""),
                iteration=state.get("iteration", 0),
                current_answer_preview=state.get("current_answer", "")[:200],
            )

            self._set_phase(record, "improve", iteration=state.get("iteration", 0))
            tracer.log_phase_change("improve", data={"iteration": state.get("iteration", 0)})
            state.update(await asyncio.to_thread(nodes.improve_answer, state))
            tracer.log_improvement(
                improved_answer=state.get("current_answer", ""),
                iteration=state.get("iteration", 0),
                based_on_reflection=state.get("critique", ""),
            )

            self._set_phase(record, "evaluate")
            state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
            tracer.log_evaluation(
                score=state.get("score"),
                iteration=state.get("iteration", 0),
                **eval_trace_kwargs(state.get("multi_dim_evaluation")),
            )
            self._add_event(record, "evaluation", self._evaluation_event_data(
                state,
                score=state.get("score"),
                iteration=state.get("iteration", 0),
            ))
            state.update(await asyncio.to_thread(nodes.enforce_output_length, state))
            self._sync_length_gate_from_state(record, state)

        state.update(await asyncio.to_thread(nodes.finalize_task_answer, state))
        self._sync_length_gate_from_state(record, state)

    async def _run_post_company_reflection(
        self, record: TaskRecord, state: dict[str, Any], tracer: TraceLogger
    ) -> None:
        """公司路徑專用：預設跳過完整反思閉環（可經環境變數恢復）。"""
        mode = _post_company_reflect_mode()
        if mode == "off":
            record.post_company_reflect_applied = "off"
            self._add_event(record, "post_company_reflect_skipped", {"mode": "off"})
            tracer.log_phase_change("post_company_reflect_skipped", data={"mode": "off"})
            return
        if mode == "evaluate":
            record.post_company_reflect_applied = "evaluate"
            self._set_phase(record, "evaluate")
            tracer.log_phase_change("evaluate")
            state.update(await asyncio.to_thread(nodes.enforce_output_length, state))
            state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
            tracer.log_evaluation(
                score=state.get("score"),
                iteration=0,
                **eval_trace_kwargs(state.get("multi_dim_evaluation")),
            )
            self._add_event(record, "evaluation", self._evaluation_event_data(
                state,
                score=state.get("score"),
                iteration=0,
                mode="evaluate_only",
            ))
            state.update(await asyncio.to_thread(nodes.finalize_task_answer, state))
            self._sync_length_gate_from_state(record, state)
            return
        record.post_company_reflect_applied = "full"
        state["post_company_reflect_mode"] = "full"
        state["resolved_execution_path"] = "company"
        await self._run_reflection_loop(record, state, tracer)
