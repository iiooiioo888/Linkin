"""公司運行時 SSE 串流（_company_stream）。"""

import asyncio
import json as json_mod
import logging
import uuid
from typing import Any

from backend.billing.context import begin_chat_billing, chat_billing_snapshot, end_chat_billing
from backend.company.events import CompanyEvent
from backend.company.execution_gate import auto_approve_enabled
from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core import nodes
from backend.core.execution_path import resolve_company_template
from backend.core.graph import MAX_ITERATIONS, PASS_THRESHOLD, reflection_should_continue
from backend.core.post_company_reflect import post_company_reflect_mode
from backend.core.routing_preview import build_routing_preview
from backend.core.unified_pipeline import pipeline_at_least
from backend.services.task_manager import task_manager
from backend.services.trace_logger import TraceLogger

from .models import ChatRequest
from .routes import _sse_path_resolved

logger = logging.getLogger(__name__)


async def _company_confirmation_stream(req: ChatRequest):
    """公司 SSE 不直接執行。建立待確認任務後結束。"""
    record = task_manager.create_task(
        req.query, req.execution_strategy or "company", req.company_template or "quick_task", options={}
    )
    record.resolved_path = "company"
    task_manager.start_budget_draft(record)
    payload = {
        "task_id": record.task_id,
        "status": "awaiting_confirmation",
        "awaiting_confirmation": True,
        "answer": "請先確認預算方案，確認後才會開始執行。",
    }
    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'pending_user', 'task_id': record.task_id}, ensure_ascii=False)}\n\n"
    yield f"event: done\ndata: {json_mod.dumps(payload, ensure_ascii=False)}\n\n"


async def _company_stream(req: ChatRequest):
    """公司運行時 SSE 串流：異步執行 + EventBus 事件推送。

    預設先停在預算確認。只有 EVOL_BUDGET_AUTO_APPROVE 才沿用直接執行。
    """
    if not auto_approve_enabled():
        async for chunk in _company_confirmation_stream(req):
            yield chunk
        return

    session_id = req.session_id or uuid.uuid4().hex[:12]

    billing_token = begin_chat_billing(session_id)
    lock = req.semantic_lock or {}
    query = req.query
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])

    template_name = resolve_company_template(query, req.company_template or "quick_task")

    try:
        from backend.core.company_nodes import enhance_with_opc_context, with_opc_summary

        opc_state = await enhance_with_opc_context({"query": query, "session_id": session_id})
        query = with_opc_summary(query, str((opc_state.get("opc_context") or {}).get("summary") or ""))
    except Exception:
        logger.debug("公司 SSE 的 OPC 摘要略過", exc_info=True)

    # 選擇組織模板。工業查詢用 industrial_ops 席位，仍由任務經理分析。
    config = BUILTIN_TEMPLATES.get(template_name)
    if config is None:
        config = BUILTIN_TEMPLATES["quick_task"]

    orchestrator = CompanyOrchestrator(config)

    # 公司模式思考軌跡：session_id 即軌跡檔名
    company_tracer = TraceLogger(session_id)

    # 用 Queue 橋接 EventBus → SSE
    event_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    def _on_company_event(event: CompanyEvent, data: dict[str, Any]) -> None:
        """EventBus 監聽器：將事件推入 Queue，並回填思考軌跡。"""
        try:
            event_queue.put_nowait({"event": event.value, "data": data})
        except Exception:
            pass
        try:
            et = event.value
            if et == "phase_change":
                company_tracer.log_phase_change(str(data.get("phase", "")), data={k: v for k, v in data.items() if k != "phase"})
            elif et == "work_item_done":
                company_tracer.log_llm_call(
                    prompt=f"[{data.get('assignee', data.get('role', 'role'))}] {str(data.get('title', ''))[:200]}",
                    response=str(data.get("output") or data.get("result") or "")[:8000],
                    phase="execute_review",
                    role=str(data.get("assignee") or data.get("role") or ""),
                    item_id=str(data.get("item_id") or data.get("id") or ""),
                )
            elif et in ("work_item_error", "review_rework", "work_item_escalate"):
                company_tracer.log_custom(et, {k: (str(v)[:500]) for k, v in data.items()})
        except Exception:
            pass

    orchestrator.events.on(_on_company_event)

    # 後台執行公司任務
    async def _run_company() -> None:
        try:
            result = await orchestrator.execute(query)
            await event_queue.put({"event": "_done", "data": result})
        except Exception as exc:
            await event_queue.put({"event": "_error", "data": {"error": str(exc)}})

    task = asyncio.create_task(_run_company())

    preview = build_routing_preview(
        query,
        mode=req.execution_strategy,
        company_template=template_name,
    )
    yield _sse_path_resolved(preview)

    # 階段：啟動
    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'company_start', 'template': template_name}, ensure_ascii=False)}\n\n"

    # 持續從 Queue 讀取事件並推送 SSE
    try:
        while True:
            try:
                msg = await asyncio.wait_for(event_queue.get(), timeout=300)
            except asyncio.TimeoutError:
                yield f"event: error\ndata: {json_mod.dumps({'error': '公司運行時超時（300s）'}, ensure_ascii=False)}\n\n"
                break

            if msg is None:
                break

            evt = msg["event"]
            data = msg["data"]

            if evt == "_done":
                final_output = data.get("final_output", "")
                company_result = data
                reflect_mode = post_company_reflect_mode()

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'company_done', 'success': data.get('success', False)}, ensure_ascii=False)}\n\n"

                eval_state: dict[str, Any] = {
                    "query": query,
                    "current_answer": final_output,
                    "session_id": session_id,
                    "company_result": company_result,
                }

                unified_reflect = pipeline_at_least("reflect")
                if unified_reflect:
                    # P2：公司 SSE 反思與圖／Task 同源（should_improve）
                    eval_state["resolved_execution_path"] = "company"
                    eval_state["post_company_reflect_mode"] = reflect_mode
                final_answer = final_output

                if reflect_mode == "off":
                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'post_company_reflect_skipped', 'mode': 'off'}, ensure_ascii=False)}\n\n"
                elif reflect_mode == "evaluate":
                    eval_state.update(await asyncio.to_thread(nodes.enforce_output_length, eval_state))
                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.evaluate_answer, eval_state))
                    eval_data = {
                        'score': eval_state.get('score'),
                        'iteration': 0,
                        'multi_dim': eval_state.get('multi_dim_evaluation', {}),
                    }
                    yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"
                    final_answer = eval_state.get('current_answer', final_output)
                else:
                    eval_state.update(await asyncio.to_thread(nodes.enforce_output_length, eval_state))
                    yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                    eval_state.update(await asyncio.to_thread(nodes.evaluate_answer, eval_state))
                    eval_data = {
                        'score': eval_state.get('score'),
                        'iteration': 0,
                        'multi_dim': eval_state.get('multi_dim_evaluation', {}),
                    }
                    yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"

                    prev_score = eval_state.get('score', 0.0)

                    def _company_should_continue(
                        st: dict[str, Any],
                        *,
                        unified_reflect: bool = unified_reflect,
                    ) -> bool:
                        if unified_reflect:
                            return reflection_should_continue(st)
                        return (
                            st.get('score', 0.0) < PASS_THRESHOLD
                            and st.get('iteration', 0) < MAX_ITERATIONS
                        ) or bool(st.get("length_directive"))

                    while _company_should_continue(eval_state):
                        cur = eval_state.get('score', 0.0)
                        if eval_state.get('iteration', 0) >= 1:
                            if cur - prev_score < 0.5 and not eval_state.get("length_directive"):
                                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'early_stop', 'reason': '分數提升不足'}, ensure_ascii=False)}\n\n"
                                break
                        prev_score = cur

                        yield f"event: phase\ndata: {json_mod.dumps({'phase': 'reflect', 'iteration': eval_state.get('iteration', 0)})}\n\n"
                        eval_state.update(await asyncio.to_thread(nodes.reflect, eval_state))

                        yield f"event: phase\ndata: {json_mod.dumps({'phase': 'improve', 'iteration': eval_state.get('iteration', 0)})}\n\n"
                        eval_state.update(await asyncio.to_thread(nodes.improve_answer, eval_state))

                        yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                        eval_state.update(await asyncio.to_thread(nodes.evaluate_answer, eval_state))
                        eval_data = {
                            'score': eval_state.get('score'),
                            'iteration': eval_state.get('iteration', 0),
                            'multi_dim': eval_state.get('multi_dim_evaluation', {}),
                        }
                        yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"
                        eval_state.update(await asyncio.to_thread(nodes.enforce_output_length, eval_state))

                    final_answer = eval_state.get('current_answer', final_output)
                    eval_state['final_answer'] = final_answer
                    try:
                        await asyncio.to_thread(nodes.save_memory, eval_state)
                    except Exception:
                        pass

                done_company: dict[str, Any] = {
                    'answer': final_answer,
                    'score': eval_state.get('score'),
                    'iteration': eval_state.get('iteration', 0),
                    'company': company_result.get('stats', {}),
                    'complexity': preview.get('complexity'),
                    'reflection_rounds_used': eval_state.get('iteration', 0),
                    'reflection_rounds_max': preview.get('max_reflection_rounds'),
                }
                billing_snap = chat_billing_snapshot()
                if billing_snap:
                    done_company['billing'] = billing_snap
                yield f"event: done\ndata: {json_mod.dumps(done_company, ensure_ascii=False)}\n\n"
                break

            elif evt == "_error":
                yield f"event: error\ndata: {json_mod.dumps({'error': data.get('error', '未知錯誤')}, ensure_ascii=False)}\n\n"
                break

            else:
                # 公司生命週期事件 → 推送給前端
                yield f"event: company\ndata: {json_mod.dumps({'event': evt, **data}, ensure_ascii=False)}\n\n"

    finally:
        task.cancel()
        end_chat_billing(billing_token)
