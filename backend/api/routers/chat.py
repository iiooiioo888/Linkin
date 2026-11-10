"""聊天、SSE 串流與路由預覽 API（自 backend.main 抽出）。

含 POST /chat、POST /chat/stream、POST /routing/preview，以及串流用的
模組層 helper（_company_stream／_sse_path_resolved／_client_disconnected／
_minecraft_ops_stream）。inline import 已整理到模組頂部；只有會降級或屬可選整合的
依賴（company_nodes、recall_bridge）保留在函式內，以維持原本的 fail-open 行為。
"""

import asyncio
import json as json_mod
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.billing.context import (
    begin_chat_billing,
    chat_billing_snapshot,
    end_chat_billing,
    mark_chat_billing_interrupted,
)
from backend.billing.errors import InsufficientCreditsError
from backend.company.events import CompanyEvent
from backend.company.orchestrator import CompanyOrchestrator
from backend.company.roles import BUILTIN_TEMPLATES
from backend.core import nodes
from backend.core.execution_path import (
    chat_stream_uses_company_sse,
    resolve_company_template,
    resolve_execution_path,
)
from backend.core.graph import (
    MAX_ITERATIONS,
    PASS_THRESHOLD,
    evoloop_graph,
    reflection_should_continue,
)
from backend.core.llm import call_llm_stream, split_thinking
from backend.core.locale_prompt import normalize_ui_language
from backend.core.post_company_reflect import post_company_reflect_mode
from backend.core.reflection_limits import resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.core.stage_router import resolve_stage_model
from backend.core.unified_pipeline import pipeline_at_least, run_pre_route_enhancements
from backend.services.trace_logger import TraceLogger
from backend.services.trace_logger import eval_trace_kwargs as _eval_trace_kwargs

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    query: str
    session_id: str | None = None
    # 統一模式：執行策略（auto / simple / company），預設 auto 自動判斷
    execution_strategy: str = "auto"
    company_template: str = "quick_task"
    # 多輪對話歷史：[{"role": "user"|"assistant", "content": "..."}, ...]
    history: list[dict[str, str]] = []
    # 前端 i18n（zh-TW / en）→ 約束回覆語言
    ui_language: str | None = None
    # RAHO：用戶 Grill-Me 鎖定後的戰役簡報
    semantic_lock: dict[str, Any] | None = None
    skip_user_grill: bool = False


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    score: float | None = None
    iteration: int = 0
    status: str = "ok"
    grill: dict[str, Any] | None = None


class RoutingPreviewRequest(BaseModel):
    query: str
    mode: str = "auto"
    context: dict[str, Any] | None = None
    company_template: str | None = None


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """执行 EvoLoop 统一模式图（支援多輪對話歷史）。"""
    session_id = req.session_id or uuid.uuid4().hex[:12]
    query = req.query
    lock = req.semantic_lock or {}
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])

    initial_state = {
        "query": query,
        "session_id": session_id,
        "iteration": 0,
        "score": 0.0,
        "current_answer": "",
        "reflection": "",
        "memories": [],
        "history": req.history or [],
        "execution_strategy": req.execution_strategy,
        "company_template": req.company_template,
        "semantic_lock": lock if isinstance(lock, dict) else {},
        "ui_language": normalize_ui_language(req.ui_language),
    }
    result = await evoloop_graph.ainvoke(initial_state)
    return ChatResponse(
        session_id=session_id,
        answer=result.get("current_answer", "") or result.get("final_answer", ""),
        score=result.get("score"),
        iteration=result.get("iteration", 0),
    )


# ==================== 公司模式 SSE 串流（優化 #11） ====================


async def _company_stream(req: ChatRequest):
    """公司運行時 SSE 串流：異步執行 + EventBus 事件推送。

    將公司運行時的生命週期事件轉換為 SSE 事件，
    前端可即時看到分解/執行/審查/整合各階段進度。
    """
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


# ==================== 路由預覽（發送前，純規則） ====================


@router.post("/routing/preview")
async def routing_preview(body: RoutingPreviewRequest) -> dict[str, Any]:
    """發送前路由＋成本預覽（不呼叫 LLM）。"""
    return build_routing_preview(
        body.query,
        mode=body.mode,
        context=body.context,
        company_template=body.company_template,
    )


def _sse_path_resolved(preview: dict[str, Any]) -> str:
    return f"event: path_resolved\ndata: {json_mod.dumps(preview, ensure_ascii=False)}\n\n"


async def _client_disconnected(request: Request) -> bool:
    """客戶端是否已中止連線（SSE 協作式取消；偵測失敗視為未斷線）。"""
    try:
        return await request.is_disconnected()
    except Exception:
        return False


# ==================== 串流聊天 API（SSE 打字機效果） ====================


async def _minecraft_ops_stream(req: ChatRequest):
    """Minecraft 輕量路徑：走完整 LangGraph（含 MCP ReAct），SSE 僅推送階段與結果。"""
    session_id = req.session_id or uuid.uuid4().hex[:12]
    query = req.query
    lock = req.semantic_lock or {}
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])

    preview = build_routing_preview(
        query,
        mode=req.execution_strategy,
        company_template=req.company_template,
    )
    yield _sse_path_resolved(preview)

    initial_state: dict[str, Any] = {
        "query": query,
        "session_id": session_id,
        "task_id": session_id,
        "iteration": 0,
        "score": 0.0,
        "current_answer": "",
        "reflection": "",
        "memories": [],
        "history": req.history or [],
        "execution_strategy": req.execution_strategy,
        "company_template": req.company_template,
        "semantic_lock": lock if isinstance(lock, dict) else {},
        "ui_language": normalize_ui_language(req.ui_language),
        "task_complexity": resolve_task_complexity(query, req.execution_strategy),
        "resolved_execution_path": "minecraft_ops",
    }
    try:
        result = await evoloop_graph.ainvoke(initial_state)
        answer = result.get("current_answer", "") or result.get("final_answer", "")
        done = {
            "answer": answer,
            "score": result.get("score"),
            "iteration": result.get("iteration", 0),
            "resolved_path": result.get("resolved_execution_path") or "minecraft_ops",
            "complexity": preview.get("complexity"),
            "reflection_rounds_used": result.get("iteration", 0),
            "reflection_rounds_max": preview.get("max_reflection_rounds"),
        }
        yield f"event: done\ndata: {json_mod.dumps(done, ensure_ascii=False)}\n\n"
    except Exception as exc:
        logger.exception("minecraft_ops SSE 失敗")
        yield f"event: error\ndata: {json_mod.dumps({'error': str(exc)[:500]}, ensure_ascii=False)}\n\n"


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
