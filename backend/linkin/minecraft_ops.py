"""輕量 Minecraft 操作路徑：單席位 ReAct + MCP 工具（不走 story_studio／公司分解）。"""

from __future__ import annotations

import logging
from typing import Any

from backend.core.pipeline_trace import log_node
from backend.core.stage_router import resolve_stage_model
from backend.core.state import StateInput

logger = logging.getLogger(__name__)

_MC_OPS_ROLE = "custom_linkin_build_executor"
_MAX_TOOL_STEPS = 5


def run_minecraft_ops(state: StateInput) -> dict[str, Any]:
    """執行單次 ReAct 工具迴圈，完成放置／查詢等短操作。"""
    from backend.company.react_loop import ReActExecutor
    from backend.company.tools import tool_registry
    from backend.linkin.pipeline import prefix_query_with_linkin

    query = str(state.get("query") or "")
    lock = state.get("semantic_lock") or {}
    if isinstance(lock, dict) and lock.get("locked_brief"):
        query = str(lock["locked_brief"])

    task = prefix_query_with_linkin(query, state)
    linkin_ctx = state.get("linkin_context") or {}
    context_parts: list[str] = []
    if isinstance(linkin_ctx, dict):
        summary = str(linkin_ctx.get("summary") or "").strip()
        if summary:
            context_parts.append(summary)
        overlay = str(linkin_ctx.get("system_overlay") or "").strip()
        if overlay:
            context_parts.append(overlay)
    context = "\n\n".join(context_parts) if context_parts else "（無額外上下文）"

    model = resolve_stage_model(
        "generate",
        query=query,
        complexity="simple",
        execution_path="minecraft_ops",
    )
    log_node(
        state,
        "run_minecraft_ops",
        model=model,
        role=_MC_OPS_ROLE,
        execution_path="minecraft_ops",
    )

    executor = ReActExecutor(tool_registry, max_steps=_MAX_TOOL_STEPS, model=model)
    result = executor.run(task=task, role=_MC_OPS_ROLE, context=context)

    answer = (result.final_answer or "").strip()
    if not answer and result.error:
        answer = f"Minecraft 操作未完成：{result.error}"
    elif not answer:
        answer = "Minecraft 操作已執行，但未產出文字摘要。"

    if not result.success and result.error and "未完成" not in answer:
        answer = f"{answer}\n（{result.error}）"

    logger.info(
        "minecraft_ops 完成 success=%s steps=%d tools=%s",
        result.success,
        result.total_steps,
        result.used_tools,
    )

    return {
        "current_answer": answer,
        "initial_answer": answer,
        "iteration": 0,
        "task_complexity": "simple",
        "resolved_execution_path": "minecraft_ops",
        "minecraft_ops_result": {
            "success": result.success,
            "total_steps": result.total_steps,
            "tools": result.used_tools,
            "error": result.error,
        },
    }


__all__ = ["run_minecraft_ops"]
