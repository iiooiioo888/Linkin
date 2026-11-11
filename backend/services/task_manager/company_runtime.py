"""公司運行時 mixin（CompanyRuntimeMixin）：事件監聽、檢查點、斷點續跑與公司任務執行。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.company.events import CompanyEvent
from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core.company_nodes import with_opc_summary
from backend.linkin.pipeline import prefix_query_with_linkin, resolve_linkin_company_template

from ._base import TaskManagerBase
from ._compat import (
    delete_checkpoint,
    enhance_with_linkin_context,
    enhance_with_opc_context,
    load_checkpoint,
    new_trace_logger,
    save_checkpoint,
)
from .models import TaskRecord, _apply_commander_result, _task_precomputed_planner, _task_ticket

logger = logging.getLogger(__name__)


class CompanyRuntimeMixin(TaskManagerBase):
    """事件監聽、檢查點、斷點續跑與公司任務執行。"""

    # ── 公司運行時執行 ──

    def _attach_company_listener(
        self, record: TaskRecord, orchestrator: CompanyOrchestrator
    ) -> None:
        """掛載事件監聽器：收集事件並更新看板快照。

        seat_io 倉只落 llm_call 全文；這裡把 CompanyEvent 生命週期事件
        （work_item_*/tool_*/review_*/grill_*/inspector_verdict…）同步鏡像進
        trace_<task_id>.jsonl，執行軌跡頁與角色 I/O 回放才有完整鏈路。
        """
        # 席位 I/O 歸屬：run_id ≠ task_id，需顯式注入任務座標與軌跡寫入器
        orchestrator.task_id = record.task_id
        try:
            tracer = new_trace_logger(record.task_id)
            orchestrator.tracer = tracer
        except Exception as exc:
            tracer = None
            logger.warning("公司任務軌跡注入失敗（不影響執行）：%s", exc)

        def listener(event: CompanyEvent, data: dict[str, Any]) -> None:
            event_data = {k: v for k, v in data.items() if k != "config"}
            # execution_plan 較大且已存於 record.plan，不重複放入事件流
            if event == CompanyEvent.DECOMPOSE_DONE:
                event_data.pop("execution_plan", None)
            self._add_event(record, event.value, event_data)
            # ── 軌跡鏡像（寫入失敗不影響執行）：發出協程的 llm_trace 上下文補 role/item ──
            if tracer is not None:
                try:
                    from backend.core import llm_trace as _lt

                    mirror = dict(event_data)
                    ctx = _lt.current_context()
                    if ctx["task_id"] == record.task_id or not ctx["task_id"]:
                        mirror.setdefault("role", ctx["role"])
                        mirror.setdefault("item_id", ctx["item_id"])
                        mirror.setdefault("phase", ctx["phase"])
                    tracer.log_company_event(event.value, mirror)
                except Exception:
                    logger.debug("公司事件軌跡鏡像失敗：%s", event)
            if event == CompanyEvent.PHASE_CHANGE:
                record.phase = str(data.get("phase", ""))
            # 分解完成：即時記錄規劃（供任務頁執行中展示）
            if event == CompanyEvent.DECOMPOSE_DONE:
                record.plan = {
                    "subtask_count": data.get("subtask_count"),
                    "strategy": data.get("strategy"),
                    "execution_plan": data.get("execution_plan"),
                    "campaign": data.get("campaign") or getattr(orchestrator, "_campaign", {}),
                }
            if event in {
                CompanyEvent.CAMPAIGN_PLANNED,
                CompanyEvent.BATTLE_PLANNED,
                CompanyEvent.GRILL_RAISED,
                CompanyEvent.GRILL_RESOLVED,
                CompanyEvent.USER_DECISION_NEEDED,
                CompanyEvent.RAHO_TIMEOUT,
                CompanyEvent.INSPECTOR_VERDICT,
            }:
                try:
                    record.raho = orchestrator._raho_snapshot()
                except Exception:
                    pass
            # 每次事件都刷新看板與預算快照
            try:
                record.kanban = {
                    status.value: items
                    for status, items in orchestrator.get_kanban().items()
                }
                record.budget = orchestrator.get_budget_status()
            except Exception:
                pass

        orchestrator.events.on(listener)

    def _save_company_checkpoint(self, record: TaskRecord, orchestrator: CompanyOrchestrator, phase: str) -> None:
        """保存公司任務檢查點（供斷點續跑）。"""
        try:
            checkpoint_data = orchestrator.to_checkpoint(goal=record.query)
            checkpoint_data["phase"] = phase
            checkpoint_data["template"] = record.template
            save_checkpoint(record.task_id, checkpoint_data)
            record.resumable = True
            self._persist(record)
        except Exception as exc:
            logger.warning("檢查點保存失敗（不影響執行）：%s", exc)

    async def _resume_company_task(self, record: TaskRecord, checkpoint: dict[str, Any]) -> None:
        """從檢查點恢復公司運行時任務執行。"""
        record.status = "running"
        record.phase = "resuming"
        self._persist(record)
        resume_task_handle = asyncio.current_task()
        if resume_task_handle is not None:
            self._running_tasks[record.task_id] = resume_task_handle
        tracer = new_trace_logger(record.task_id)
        tracer.log_phase_change("resume", data={"checkpoint_phase": checkpoint.get("phase", "")})

        config = BUILTIN_TEMPLATES.get(record.template)
        if config is None:
            config = BUILTIN_TEMPLATES["quick_task"]

        # 從檢查點恢復 orchestrator
        orchestrator = CompanyOrchestrator.from_checkpoint(checkpoint, config=config)
        self._attach_company_listener(record, orchestrator)
        self._orchestrators[record.task_id] = orchestrator

        try:
            result = await orchestrator.execute(
                record.query,
                ticket=_task_ticket(record),
                precomputed_planner=_task_precomputed_planner(record),
            )
        except asyncio.CancelledError:
            if record.status in ("running", "pending"):
                record.status = "cancelled"
                record.error = record.error or "任務已被使用者取消（強制中斷）"
                record.resumable = True
                self._set_phase(record, "cancelled")
                self._finish(record)
            raise
        except Exception as exc:
            logger.error("公司任務 %s 恢復執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase="resume", recoverable=False)
            # 檢查點仍在：允許再次續跑
            record.resumable = load_checkpoint(record.task_id) is not None
            self._orchestrators.pop(record.task_id, None)
            self._finish(record)
            return
        finally:
            self._orchestrators.pop(record.task_id, None)
            self._running_tasks.pop(record.task_id, None)

        if not result.get("success"):
            error_msg = result.get("error") or result.get("final_output") or "公司運行時恢復執行失敗"
            if record.cancel_requested or "取消" in error_msg:
                record.status = "cancelled"
                record.error = "任務已被使用者取消"
                self._save_company_checkpoint(record, orchestrator, record.phase)
            else:
                record.status = "failed"
                record.error = error_msg
                record.resumable = load_checkpoint(record.task_id) is not None
            self._set_phase(record, "cancelled" if record.status == "cancelled" else "failed")
            self._finish(record)
            return

        record.review = result.get("review")
        record.stats = result.get("stats")
        record.raho = result.get("raho") or record.raho
        self._persist(record)

        # 公司產出進入評估/反思/改進迭代迴圈
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": result.get("final_output", ""),
            "iteration": 0,
            "score": 0.0,
        }
        try:
            await self._run_post_company_reflection(record, state, tracer)
        except Exception as exc:
            logger.warning("任務 %s 評估迴圈失敗（保留公司產出）：%s", record.task_id, exc)

        record.answer = str(
            state.get("final_answer") or state.get("current_answer") or ""
        )
        record.score = state.get("score")
        record.iteration = state.get("iteration", 0)
        if not record.length_compliance and state.get("length_compliance"):
            self._sync_length_gate_from_state(record, state)
        if record.status != "cancelled" and not record.cancel_requested:
            record.status = "completed"
            record.resumable = False
            delete_checkpoint(record.task_id)  # 完成後清理檢查點
            self._set_phase(record, "done")
        self._finish(record)

    async def _run_company_task(self, record: TaskRecord) -> None:
        """公司運行時路徑：多角色分工 → 反思迴圈。"""
        tracer = new_trace_logger(record.task_id)
        self._set_phase(record, "starting", template=record.template)
        tracer.log_phase_change("starting", data={"template": record.template})
        # 角色 I/O 上下文：綁定 task_id 供事件鏡像/席位軌跡歸屬（公司協程內自動繼承）
        from backend.core import llm_trace

        llm_trace.trace_task_id.set(record.task_id)

        from backend.core.execution_path import resolve_company_template

        record.template = resolve_company_template(record.query, record.template)
        config = BUILTIN_TEMPLATES.get(record.template)
        if config is None:
            config = BUILTIN_TEMPLATES["quick_task"]

        linkin_state: dict[str, Any] = {
            "query": record.query,
            "company_template": record.template or "quick_task",
        }
        try:
            linkin_state.update(await asyncio.to_thread(enhance_with_linkin_context, linkin_state))
            linkin_template = resolve_linkin_company_template(linkin_state)
            if linkin_template:
                config = BUILTIN_TEMPLATES.get(linkin_template) or config
            company_query = prefix_query_with_linkin(record.query, linkin_state)
        except Exception:
            company_query = record.query

        try:
            opc_state = await enhance_with_opc_context({"query": company_query})
            opc_summary = str((opc_state.get("opc_context") or {}).get("summary") or "")
            company_query = with_opc_summary(company_query, opc_summary)
        except Exception:
            logger.debug("公司任務 OPC 摘要略過", exc_info=True)

        orchestrator = CompanyOrchestrator(config)
        self._attach_company_listener(record, orchestrator)
        # 註冊 orchestrator 引用（供取消使用）
        self._orchestrators[record.task_id] = orchestrator

        try:
            result = await orchestrator.execute(
                company_query,
                ticket=_task_ticket(record),
                precomputed_planner=_task_precomputed_planner(record),
            )
        except asyncio.CancelledError:
            # 強制中斷：保存檢查點供斷點續跑，狀態收尾交給 _run_unified_task
            self._save_company_checkpoint(record, orchestrator, record.phase)
            raise
        except Exception as exc:
            logger.error("公司任務 %s 執行失敗：%s", record.task_id, exc)
            record.status = "failed"
            record.error = str(exc)
            tracer.log_error(str(exc), phase=record.phase, recoverable=False)
            # 失敗時保存檢查點，允許斷點續跑
            self._save_company_checkpoint(record, orchestrator, record.phase)
            self._orchestrators.pop(record.task_id, None)
            self._finish(record)
            return
        finally:
            # 無論成功失敗，清理 orchestrator 引用
            self._orchestrators.pop(record.task_id, None)

        _apply_commander_result(record, result)
        if not result.get("success"):
            error_msg = result.get("error") or result.get("final_output") or "公司運行時執行失敗"
            # 判斷是否為使用者取消
            if record.cancel_requested or "取消" in error_msg:
                record.status = "cancelled"
                record.error = "任務已被使用者取消"
                # 保留檢查點：取消的公司任務可斷點續跑
                self._save_company_checkpoint(record, orchestrator, record.phase)
            else:
                record.status = "failed"
                record.error = error_msg
            self._set_phase(record, "cancelled" if record.status == "cancelled" else "failed")
            self._finish(record)
            return

        # ── 提取公司運行細節（供任務頁展示） ──
        record.review = result.get("review")
        record.stats = result.get("stats")
        record.raho = result.get("raho") or record.raho
        for entry in result.get("run_log", []):
            if entry.get("event") == "decompose_done":
                record.plan = {
                    "subtask_count": entry.get("subtask_count"),
                    "strategy": entry.get("strategy"),
                    "execution_plan": entry.get("execution_plan"),
                }
                break
        self._persist(record)

        # ── 公司產出進入評估/反思/改進迭代迴圈 ──
        state: dict[str, Any] = {
            "query": record.query,
            "session_id": record.task_id,
            "current_answer": result.get("final_output", ""),
            "iteration": 0,
            "score": 0.0,
        }
        try:
            await self._run_post_company_reflection(record, state, tracer)
        except Exception as exc:
            logger.warning("任務 %s 評估迴圈失敗（保留公司產出）：%s", record.task_id, exc)

        record.answer = str(
            state.get("final_answer") or state.get("current_answer") or ""
        )
        record.score = state.get("score")
        record.iteration = state.get("iteration", 0)
        if not record.length_compliance and state.get("length_compliance"):
            self._sync_length_gate_from_state(record, state)
        if record.status != "cancelled" and not record.cancel_requested:
            record.status = "completed"
            self._set_phase(record, "done")
        self._finish(record)
