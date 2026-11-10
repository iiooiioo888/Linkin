"""POST /chat、POST /routing/preview 與 path_resolved SSE helper。"""

import json as json_mod
import uuid
from typing import Any

from backend.core.graph import evoloop_graph
from backend.core.locale_prompt import normalize_ui_language
from backend.core.routing_preview import build_routing_preview

from ._router import router
from .models import ChatRequest, ChatResponse, RoutingPreviewRequest


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
