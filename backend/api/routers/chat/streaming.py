"""POST /chat/stream 的 token 串流、評估、反思與定稿。"""

import asyncio
import json as json_mod
import logging
import time
import uuid
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from backend.billing.context import (
    begin_chat_billing,
    chat_billing_snapshot,
    end_chat_billing,
    mark_chat_billing_interrupted,
)
from backend.billing.errors import InsufficientCreditsError
from backend.core import nodes
from backend.core.execution_path import chat_stream_uses_company_sse, resolve_execution_path
from backend.core.graph import reflection_should_continue
from backend.core.llm import call_llm_stream, split_thinking
from backend.core.locale_prompt import normalize_ui_language
from backend.core.reflection_limits import resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.core.stage_router import resolve_stage_model
from backend.core.unified_pipeline import pipeline_at_least, run_pre_route_enhancements
from backend.services.trace_logger import TraceLogger
from backend.services.trace_logger import eval_trace_kwargs as _eval_trace_kwargs

from ._router import router
from .company_stream import _company_stream
from .minecraft_stream import _minecraft_ops_stream
from .models import ChatRequest
from .routes import _sse_path_resolved

logger = logging.getLogger(__name__)


async def _client_disconnected(request: Request) -> bool:
    """客戶端是否已中止連線（SSE 協作式取消；偵測失敗視為未斷線）。"""
    try:
        return await request.is_disconnected()
    except Exception:
        return False


# ==================== 串流聊天 API（SSE 打字機效果） ====================


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    """SSE 串流聊天：即時推送階段進度與生成 token。

    事件格式（Server-Sent Events）：
      event: phase      → 階段切換 {"phase": "..."}
      event: token      → 生成片段 {"token": "..."}
      event: evaluation → 評分 {"score": n, "iteration": n}
      event: done       → 完成 {"answer": "...", "score": n, "iteration": n}
      event: error      → 錯誤 {"error": "..."}

    統一模式：複雜任務（公司運行時路徑）自動降級為同步 /chat。
    """
    if chat_stream_uses_company_sse(req.query, req.execution_strategy):
        # 公司運行時：SSE 串流進度（優化 #11）
        return StreamingResponse(
            _company_stream(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    if resolve_execution_path(req.query, req.execution_strategy) == "minecraft_ops":
        return StreamingResponse(
            _minecraft_ops_stream(req),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    session_id = req.session_id or uuid.uuid4().hex[:12]

    # 思考軌跡回填（session_id 即軌跡檔名；前端「軌跡」按鈕以此查詢）
    chat_tracer = TraceLogger(session_id)

    def _sse_billing_event() -> str | None:
        snap = chat_billing_snapshot()
        if not snap or float(snap.get("credits_deducted") or 0) <= 0:
            return None
        return f"event: billing\ndata: {json_mod.dumps(snap, ensure_ascii=False)}\n\n"

    async def event_stream():
        billing_token = begin_chat_billing(session_id)

        strategy = (req.execution_strategy or "auto").strip().lower()
        lock = req.semantic_lock or {}
        query_for_route = req.query
        if isinstance(lock, dict) and lock.get("locked_brief"):
            query_for_route = str(lock["locked_brief"])
        preview = build_routing_preview(
            query_for_route,
            mode=req.execution_strategy,
            company_template=req.company_template,
        )
        yield _sse_path_resolved(preview)

        state: dict[str, Any] = {
            "query": query_for_route,
            "session_id": session_id,
            "task_id": session_id,
            "history": req.history or [],
            "semantic_lock": req.semantic_lock or {},
            "ui_language": normalize_ui_language(req.ui_language),
            "execution_strategy": req.execution_strategy,
            "task_complexity": preview.get("complexity")
            or resolve_task_complexity(query_for_route, req.execution_strategy),
            "resolved_execution_path": preview.get("path") or "simple",
        }
        reflection_rounds_max = int(preview.get("max_reflection_rounds") or 0)
        lock = req.semantic_lock or {}
        if isinstance(lock, dict) and lock.get("locked_brief"):
            state["query"] = str(lock["locked_brief"])
        try:
            # 階段 1：記憶檢索
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'retrieve_memories'})}\n\n"
            chat_tracer.log_phase_change("retrieve_memories")
            state.update(await asyncio.to_thread(nodes.retrieve_memories, state))
            _mems = state.get("retrieved_memories") or []
            if _mems:
                chat_tracer.log_context_injection(
                    source="memory", items=_mems, phase="retrieve_memories", query=state["query"],
                )

            # 前置增強：OPC／靈境／整合召回（P1 統一管線：並行 + 逾時降級，設計 §7.4(b)）
            pre_enhance_degraded: dict[str, Any] | None = None
            if pipeline_at_least("pre"):
                for _phase in (
                    "enhance_opc_context",
                    "enhance_linkin_context",
                    "enhance_recall_context",
                ):
                    yield f"event: phase\ndata: {json_mod.dumps({'phase': _phase})}\n\n"
                    chat_tracer.log_phase_change(_phase)

                _pre_update, pre_enhance_degraded = await run_pre_route_enhancements(state)
                state.update(_pre_update)

                _opc_ctx = state.get("opc_context") or {}
                if isinstance(_opc_ctx, dict) and _opc_ctx.get("summary"):
                    chat_tracer.log_context_injection(
                        source="opc", items=[_opc_ctx["summary"]],
                        phase="enhance_opc_context", query=state["query"],
                    )
                _linkin_ctx = state.get("linkin_context") or {}
                if isinstance(_linkin_ctx, dict) and _linkin_ctx.get("summary"):
                    chat_tracer.log_context_injection(
                        source="linkin", items=[_linkin_ctx["summary"]],
                        phase="enhance_linkin_context", query=state["query"],
                    )
                _recall = state.get("recall_context") or {}
                if isinstance(_recall, dict) and _recall.get("injection"):
                    chat_tracer.log_context_injection(
                        source="recall", items=[_recall["injection"]],
                        phase="enhance_recall_context", query=state["query"],
                    )
                if pre_enhance_degraded.get("context_degraded"):
                    # 逾時降級資訊在增強完成後才可知，故於此補發 path_resolved
                    yield _sse_path_resolved({**preview, **pre_enhance_degraded})
                    chat_tracer.log_custom("pre_enhance_degraded", dict(pre_enhance_degraded))
            else:
                # 整合召回（MemOS / OpenViking / WeKnora，fail-open）
                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'enhance_recall_context'})}\n\n"
                chat_tracer.log_phase_change("enhance_recall_context")
                from backend.integrations.recall_bridge import enhance_with_recall_context

                state.update(await asyncio.to_thread(enhance_with_recall_context, state))
                _recall = state.get("recall_context") or {}
                if isinstance(_recall, dict) and _recall.get("injection"):
                    chat_tracer.log_context_injection(
                        source="recall",
                        items=[_recall["injection"]],
                        phase="enhance_recall_context",
                        query=state["query"],
                    )

            # 階段 2：生成回答（串流 token，Queue 橋接同步生成器與非同步迴圈）
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'generate'})}\n\n"
            chat_tracer.log_phase_change("generate")
            gen_prompt, gen_system = nodes.build_generate_prompt(state)
            # 與管線節點同一套環節路由，軌跡才能記到真實模型
            gen_model = resolve_stage_model(
                "generate",
                query=state["query"],
                complexity=state.get("task_complexity"),
            )
            loop = asyncio.get_running_loop()
            token_queue: asyncio.Queue[str | None] = asyncio.Queue()
            gen_started = time.monotonic()

            def _produce_tokens() -> None:
                try:
                    for token in call_llm_stream(gen_prompt, system=gen_system, model=gen_model):
                        loop.call_soon_threadsafe(token_queue.put_nowait, token)
                finally:
                    loop.call_soon_threadsafe(token_queue.put_nowait, None)

            asyncio.get_running_loop().run_in_executor(None, _produce_tokens)

            answer_parts: list[str] = []
            chunk_count = 0
            while True:
                token = await token_queue.get()
                if token is None:
                    break
                answer_parts.append(token)
                yield f"event: token\ndata: {json_mod.dumps({'token': token}, ensure_ascii=False)}\n\n"
                chunk_count += 1
                if chunk_count % 16 == 0 and await _client_disconnected(request):
                    break
            answer = "".join(answer_parts)
            if await _client_disconnected(request):
                # 客戶端已離線：不評估／不改進／不存記憶，計費標記中斷
                mark_chat_billing_interrupted("client_disconnect")
                chat_tracer.log_phase_change("client_disconnect")
                return
            gen_thinking, visible = split_thinking(answer)
            state.update({
                "initial_answer": visible or answer,
                "current_answer": visible or answer,
                "iteration": 0,
                "thinking": gen_thinking,
            })
            chat_tracer.log_llm_call(
                prompt=gen_prompt, response=(visible or answer)[:8000],
                model=gen_model,
                system=gen_system,
                duration_ms=round((time.monotonic() - gen_started) * 1000, 1),
                phase="generate",
            )
            billing_evt = _sse_billing_event()
            if billing_evt:
                yield billing_evt

            # 輸出長度守門：超標時把「精簡」當成額外一輪改進目標（預算由節點控管）
            state.update(await asyncio.to_thread(nodes.enforce_output_length, state))

            # 階段 3：多維度評估（優化 #1 + #4）
            yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
            chat_tracer.log_phase_change("evaluate")
            state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
            eval_data = {
                'score': state.get('score'),
                'iteration': 0,
                'multi_dim': state.get('multi_dim_evaluation', {}),
            }
            chat_tracer.log_evaluation(
                state.get('score'), iteration=0,
                **_eval_trace_kwargs(state.get('multi_dim_evaluation')),
            )
            yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"

            # 反思/改進迴圈（動態迭代：帶分數變化率檢測；長度指令未消化時強制多跑一輪）
            prev_score = state.get('score', 0.0)
            while reflection_should_continue(state):
                if await _client_disconnected(request):
                    mark_chat_billing_interrupted("client_disconnect")
                    chat_tracer.log_phase_change("client_disconnect")
                    return
                current_score = state.get('score', 0.0)
                # 動態迭代檢查：分數變化率過低時提前終止（優化 #4）
                if state.get('iteration', 0) >= 1:
                    improvement = current_score - prev_score
                    if improvement < 0.5 and not state.get("length_directive"):  # MIN_SCORE_IMPROVEMENT
                        yield f"event: phase\ndata: {json_mod.dumps({'phase': 'early_stop', 'reason': f'分數提升不足 ({improvement:.1f})', 'iteration': state.get('iteration', 0)})}\n\n"
                        break
                prev_score = current_score

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'reflect', 'iteration': state.get('iteration', 0), 'score': current_score})}\n\n"
                chat_tracer.log_phase_change("reflect", data={"iteration": state.get("iteration", 0), "score": current_score})
                state.update(await asyncio.to_thread(nodes.reflect, state))
                critique = str(state.get("critique") or "")
                suggestion = str(state.get("suggestion") or "")
                if critique or suggestion:
                    chat_tracer.log_reflection(
                        "\n".join(x for x in (f"反思：{critique}", f"改進建議：{suggestion}") if x),
                        iteration=state.get("iteration", 0),
                    )
                reflect_text = "\n".join(
                    p for p in (
                        f"反思：{critique}" if critique else "",
                        f"改進建議：{suggestion}" if suggestion else "",
                    ) if p
                )
                if reflect_text:
                    think_token = f"<think>\n{reflect_text}\n</think>\n"
                    yield f"event: token\ndata: {json_mod.dumps({'token': think_token}, ensure_ascii=False)}\n\n"
                    state["thinking"] = "\n\n".join(
                        x for x in (str(state.get("thinking") or ""), reflect_text) if x
                    )

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'improve', 'iteration': state.get('iteration', 0)})}\n\n"
                chat_tracer.log_phase_change("improve", data={"iteration": state.get("iteration", 0)})
                state.update(await asyncio.to_thread(nodes.improve_answer, state))
                improved = str(state.get("current_answer") or "")
                if improved:
                    chat_tracer.log_improvement(
                        improved, iteration=state.get("iteration", 0),
                        based_on_reflection=critique or suggestion,
                    )
                imp_think, imp_vis = split_thinking(improved)
                if imp_think:
                    state["thinking"] = "\n\n".join(
                        x for x in (str(state.get("thinking") or ""), imp_think) if x
                    )
                    state["current_answer"] = imp_vis or improved
                if improved:
                    body = imp_vis or improved
                    yield f"event: answer\ndata: {json_mod.dumps({'answer': body}, ensure_ascii=False)}\n\n"

                yield f"event: phase\ndata: {json_mod.dumps({'phase': 'evaluate'})}\n\n"
                state.update(await asyncio.to_thread(nodes.evaluate_answer, state))
                chat_tracer.log_evaluation(
                    state.get('score'), iteration=state.get('iteration', 0),
                    **_eval_trace_kwargs(state.get('multi_dim_evaluation')),
                )
                eval_data = {
                    'score': state.get('score'),
                    'iteration': state.get('iteration', 0),
                    'multi_dim': state.get('multi_dim_evaluation', {}),
                }
                yield f"event: evaluation\ndata: {json_mod.dumps(eval_data, ensure_ascii=False)}\n\n"
                state.update(await asyncio.to_thread(nodes.enforce_output_length, state))
                billing_evt = _sse_billing_event()
                if billing_evt:
                    yield billing_evt

            if await _client_disconnected(request):
                mark_chat_billing_interrupted("client_disconnect")
                chat_tracer.log_phase_change("client_disconnect")
                return

            final_answer = state.get("current_answer", "")
            if pipeline_at_least("reflect"):
                # P2：與 Task 同源收尾（decide_final_answer → record_outcome 恰一次 + 長度守門）
                state.update(await asyncio.to_thread(nodes.finalize_task_answer, state))
                final_answer = (
                    state.get("final_answer") or state.get("current_answer") or final_answer
                )
            chat_tracer.log_phase_change("done", data={"score": state.get("score"), "iteration": state.get("iteration", 0)})
            # 儲存記憶（盡力而為）
            state["final_answer"] = final_answer
            await asyncio.to_thread(nodes.save_memory, state)

            done_payload: dict[str, Any] = {
                "answer": final_answer,
                "thinking": state.get("thinking", ""),
                "score": state.get("score"),
                "iteration": state.get("iteration", 0),
                "complexity": state.get("task_complexity"),
                "reflection_rounds_used": state.get("iteration", 0),
                "reflection_rounds_max": reflection_rounds_max,
            }
            if pre_enhance_degraded is not None:
                done_payload.update(pre_enhance_degraded)
            billing_snap = chat_billing_snapshot()
            if billing_snap:
                done_payload["billing"] = billing_snap
            yield f"event: done\ndata: {json_mod.dumps(done_payload, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error("串流聊天失敗：%s", exc)
            err_msg = str(exc)
            interrupted = False
            if isinstance(exc.__cause__, InsufficientCreditsError):
                err_msg = exc.__cause__.message
            elif "靈境積分不足" in err_msg or "INSUFFICIENT_CREDITS" in err_msg:
                interrupted = True
            snap = chat_billing_snapshot()
            if snap and interrupted:
                snap = {**snap, "interrupted": True, "interrupt_reason": err_msg}
                yield f"event: billing\ndata: {json_mod.dumps(snap, ensure_ascii=False)}\n\n"
            yield f"event: error\ndata: {json_mod.dumps({'error': err_msg, 'code': 'INSUFFICIENT_CREDITS' if interrupted else 'CHAT_ERROR'}, ensure_ascii=False)}\n\n"
        finally:
            end_chat_billing(billing_token)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
