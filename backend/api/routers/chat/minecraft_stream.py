"""Minecraft 輕量路徑的 SSE 串流（_minecraft_ops_stream）。"""

import json as json_mod
import logging
import uuid
from typing import Any

from backend.core.graph import evoloop_graph
from backend.core.locale_prompt import normalize_ui_language
from backend.core.reflection_limits import resolve_task_complexity
from backend.core.routing_preview import build_routing_preview

from .models import ChatRequest
from .routes import _sse_path_resolved

logger = logging.getLogger(__name__)


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
