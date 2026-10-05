"""三軌收斂統一管線（P0：旗標、型別、請求建構；尚未接入入口）。"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

logger = logging.getLogger(__name__)

PipelineLevel = Literal["off", "pre", "reflect", "batch", "full"]

_LEVEL_ORDER: dict[PipelineLevel, int] = {
    "off": 0,
    "pre": 1,
    "reflect": 2,
    "batch": 3,
    "full": 4,
}

_VALID_LEVELS: frozenset[str] = frozenset(_LEVEL_ORDER)
_unknown_env_logged = False


def pipeline_level() -> PipelineLevel:
    """解析 ``EVOL_UNIFIED_PIPELINE``；空／未設定／未知值均視為 ``off``。"""
    global _unknown_env_logged
    raw = os.environ.get("EVOL_UNIFIED_PIPELINE", "").strip().lower()
    if not raw or raw == "off":
        return "off"
    if raw in _VALID_LEVELS:
        return raw  # type: ignore[return-value]
    if not _unknown_env_logged:
        logger.warning("未知的 EVOL_UNIFIED_PIPELINE=%r，視為 off", raw)
        _unknown_env_logged = True
    return "off"


def pipeline_at_least(level: PipelineLevel) -> bool:
    """目前旗標是否已達指定階段（含更高階段）。"""
    return _LEVEL_ORDER[pipeline_level()] >= _LEVEL_ORDER[level]


class PipelineMode(str, Enum):
    BATCH = "batch"
    STREAM = "stream"
    TASK = "task"


PipelineEvent = dict[str, Any]

EmitCallback = Callable[[PipelineEvent], Awaitable[None]]
TokenSink = Callable[[str], Awaitable[None]]


@dataclass
class PipelineRequest:
    """三入口共用的管線請求（對齊 ``EvoLoopState`` 初始欄位子集）。

    路由與 preview 一律以 ``effective_query`` 為準；勿僅依 ``semantic_lock``
    推導 query（Task ticket JSON 等 case 與 lock 內 brief 可能不一致）。
    """

    query: str
    effective_query: str
    execution_strategy: str = "auto"
    company_template: str = "quick_task"
    session_id: str | None = None
    task_id: str | None = None
    history: list[dict[str, str]] = field(default_factory=list)
    ui_language: str | None = None
    semantic_lock: dict[str, Any] = field(default_factory=dict)
    skip_user_grill: bool = False
    options: dict[str, Any] = field(default_factory=dict)
    source_entry: Literal["chat", "chat_stream", "task"] | None = None


def effective_query_from_lock(raw_query: str, semantic_lock: dict[str, Any] | None) -> str:
    """與 ``/chat``／SSE 相同：``semantic_lock.locked_brief`` 覆寫路由用 query。"""
    lock = semantic_lock or {}
    brief = lock.get("locked_brief")
    if isinstance(brief, str) and brief.strip():
        return brief.strip()
    return (raw_query or "").strip()


def build_semantic_lock_from_task_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Task ``options`` → ``semantic_lock``（Q3：``auditor_ticket`` 併入 lock）。"""
    opts = options or {}
    lock: dict[str, Any] = {}
    existing = opts.get("semantic_lock")
    if isinstance(existing, dict):
        lock.update(existing)

    ticket = opts.get("auditor_ticket")
    if isinstance(ticket, dict):
        lock["auditor_ticket"] = ticket

    brief = opts.get("semantic_brief") or opts.get("locked_brief")
    if isinstance(brief, str) and brief.strip():
        lock["locked_brief"] = brief.strip()

    return lock


def resolve_task_effective_query(raw_query: str, options: dict[str, Any] | None) -> str:
    """與 ``TaskManager.create_task`` 相同的 query 解析（brief／ticket 優先序一致）。"""
    opts = options or {}
    brief = opts.get("semantic_brief") or opts.get("locked_brief")
    if isinstance(brief, str) and brief.strip():
        return brief.strip()
    ticket = opts.get("auditor_ticket")
    if isinstance(ticket, dict) and ticket.get("status") == "APPROVED_FOR_PLANNING":
        return json.dumps(ticket, ensure_ascii=False)
    return raw_query


def build_pipeline_request_from_chat(
    *,
    query: str,
    session_id: str | None = None,
    execution_strategy: str = "auto",
    company_template: str = "quick_task",
    history: list[dict[str, str]] | None = None,
    ui_language: str | None = None,
    semantic_lock: dict[str, Any] | None = None,
    skip_user_grill: bool = False,
) -> PipelineRequest:
    lock = dict(semantic_lock) if isinstance(semantic_lock, dict) else {}
    effective = effective_query_from_lock(query, lock)
    return PipelineRequest(
        query=query,
        effective_query=effective,
        session_id=session_id,
        execution_strategy=execution_strategy,
        company_template=company_template,
        history=list(history or []),
        ui_language=ui_language,
        semantic_lock=lock,
        skip_user_grill=skip_user_grill,
        source_entry="chat",
    )


def build_pipeline_request_from_task(
    *,
    query: str,
    execution_strategy: str = "auto",
    company_template: str = "quick_task",
    options: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> PipelineRequest:
    opts = dict(options or {})
    lock = build_semantic_lock_from_task_options(opts)
    effective = resolve_task_effective_query(query, opts)
    return PipelineRequest(
        query=query,
        effective_query=effective,
        task_id=task_id,
        execution_strategy=execution_strategy,
        company_template=company_template,
        history=[],
        ui_language=opts.get("ui_language") if isinstance(opts.get("ui_language"), str) else None,
        semantic_lock=lock,
        options=opts,
        source_entry="task",
    )


async def run_unified_pipeline(
    req: PipelineRequest,
    mode: PipelineMode,
    emit: EmitCallback | None = None,
    token_sink: TokenSink | None = None,
) -> dict[str, Any]:
    """統一管線編排（P1+ 實作；P0 不接入任何 HTTP 入口）。"""
    _ = (req, mode, emit, token_sink)
    raise NotImplementedError(
        "run_unified_pipeline 尚未實作；請設定 EVOL_UNIFIED_PIPELINE 分階段旗標後於 P1+ 接入"
    )


__all__ = [
    "PipelineEvent",
    "PipelineLevel",
    "PipelineMode",
    "PipelineRequest",
    "build_pipeline_request_from_chat",
    "build_pipeline_request_from_task",
    "build_semantic_lock_from_task_options",
    "effective_query_from_lock",
    "pipeline_at_least",
    "pipeline_level",
    "resolve_task_effective_query",
    "run_unified_pipeline",
]
