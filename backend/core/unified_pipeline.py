"""三軌收斂統一管線（P0：旗標、型別、請求建構；P1：路由前共用前置增強）。"""

from __future__ import annotations

import asyncio
import contextlib
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


DEFAULT_PRE_ENHANCE_TIMEOUT_MS = 300


def pre_enhance_timeout_ms() -> int:
    """前置增強總等待上限（ms）：環境變數 > ``cost_speed.json`` > 預設 300。

    非正值或無法解析時回退預設；配置沿用 ``cost_speed_router`` 的快取與熱重載。
    """
    raw = os.environ.get("EVOL_PRE_ENHANCE_TIMEOUT_MS", "").strip()
    if raw:
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            logger.warning("無效的 EVOL_PRE_ENHANCE_TIMEOUT_MS=%r，改用配置值", raw)
        else:
            if value > 0:
                return value
            logger.warning("EVOL_PRE_ENHANCE_TIMEOUT_MS=%r 非正值，改用配置值", raw)

    try:
        from backend.core.cost_speed_router import unified_pipeline_settings

        value = int(
            unified_pipeline_settings().get("pre_enhance_timeout_ms")
            or DEFAULT_PRE_ENHANCE_TIMEOUT_MS
        )
    except Exception as exc:  # pragma: no cover - 設定讀取失敗不應中斷管線
        logger.debug("讀取 unified_pipeline 設定失敗（用預設）：%s", exc)
        return DEFAULT_PRE_ENHANCE_TIMEOUT_MS
    return value if value > 0 else DEFAULT_PRE_ENHANCE_TIMEOUT_MS


async def run_pre_route_enhancements(
    state: dict[str, Any],
    *,
    timeout_ms: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """路由前的共用前置增強（設計 §7.4(b)）：OPC／靈境／整合召回並行 + 逾時降級。

    回傳 ``(state_update, degraded)``：

    - ``state_update``：已完成來源的欄位合併結果（逾時／例外者不併入）
    - ``degraded``：``{"context_degraded": bool, "degraded_sources": [...]}``

    逾時不硬等慢源：較快的來源結果照常併入，逾時／失敗的來源取消並記入
    ``degraded_sources``，首 token 不因慢源（OPC／RAG）無限延長。
    """
    from backend.core.company_nodes import enhance_with_opc_context
    from backend.integrations.recall_bridge import enhance_with_recall_context
    from backend.linkin.pipeline import enhance_with_linkin_context

    budget_ms = pre_enhance_timeout_ms() if timeout_ms is None else int(timeout_ms)
    tasks: dict[str, asyncio.Task[Any]] = {
        "opc": asyncio.ensure_future(enhance_with_opc_context(state)),
        "linkin": asyncio.ensure_future(asyncio.to_thread(enhance_with_linkin_context, state)),
        "recall": asyncio.ensure_future(asyncio.to_thread(enhance_with_recall_context, state)),
    }

    if budget_ms > 0:
        _done, pending = await asyncio.wait(set(tasks.values()), timeout=budget_ms / 1000)
    else:
        await asyncio.wait(set(tasks.values()))
        pending = set()

    update: dict[str, Any] = {}
    degraded_sources: list[str] = []
    for name, task in tasks.items():
        if task in pending:
            task.cancel()
            degraded_sources.append(name)
            continue
        exc = task.exception()
        if exc is not None:
            logger.warning("前置增強 %s 失敗：%s", name, exc)
            degraded_sources.append(name)
            continue
        partial = task.result()
        if isinstance(partial, dict):
            update.update(partial)

    for task in pending:
        with contextlib.suppress(BaseException):
            await task

    return update, {
        "context_degraded": bool(degraded_sources),
        "degraded_sources": sorted(degraded_sources),
    }


__all__ = [
    "DEFAULT_PRE_ENHANCE_TIMEOUT_MS",
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
    "pre_enhance_timeout_ms",
    "resolve_task_effective_query",
    "run_pre_route_enhancements",
    "run_unified_pipeline",
]
