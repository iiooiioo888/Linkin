"""LLM 調用軌跡鉤子（contextvars + 全域鉤子表）。

所有 LLM 呼叫都匯流經 core.llm.call_llm；此模組提供：
- trace_task_id / trace_role / trace_item_id / trace_phase 四個 contextvars：
  由 task_manager 在任務協程開始時綁定 task_id，orchestrator 在執行/審查
  各段設定 role/item/phase；asyncio.to_thread 與 gather 子任務自動繼承。
- register_hook(fn)：task_manager 註冊鉤子，把每次 call_llm 的完整
  prompt/system/response/耗時 寫進對應任務的 TraceLogger（角色 I/O 全監）。

零依賴、寫入失敗靜默，絕不阻斷主流程。
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── 調用上下文（contextvars）──

trace_task_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "llm_trace_task_id", default=""
)
trace_role: contextvars.ContextVar[str] = contextvars.ContextVar(
    "llm_trace_role", default=""
)
trace_item_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "llm_trace_item_id", default=""
)
trace_phase: contextvars.ContextVar[str] = contextvars.ContextVar(
    "llm_trace_phase", default=""
)
# 僅公司模式任務啟用自動 llm_call 鉤子（simple/chat 路徑沿用顯式軌跡，避免重複）
trace_enabled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "llm_trace_enabled", default=False
)

# ── 鉤子表 ──

_HOOKS: list[Callable[[dict[str, Any]], None]] = []


def register_hook(fn: Callable[[dict[str, Any]], None]) -> None:
    """註冊一個 llm_call 鉤子（冪等：同一函數不重複註冊）。"""
    if fn not in _HOOKS:
        _HOOKS.append(fn)


def unregister_hook(fn: Callable[[dict[str, Any]], None]) -> None:
    try:
        _HOOKS.remove(fn)
    except ValueError:
        pass


def current_context() -> dict[str, str]:
    """讀取當前 trace 上下文（供鉤子與事件鏡像使用）。"""
    return {
        "task_id": trace_task_id.get(),
        "role": trace_role.get(),
        "item_id": trace_item_id.get(),
        "phase": trace_phase.get(),
    }


def emit(entry: dict[str, Any]) -> None:
    """把一筆 llm_call 記錄分發給所有鉤子；任何鉤子異常都不外洩。"""
    if not _HOOKS:
        return
    ctx = current_context()
    if not ctx["task_id"] or not trace_enabled.get():
        # 非任務上下文（例如啟動期探测、chat/simple 路徑）：跳過自動鏡像
        return
    record = {**entry, **ctx}
    for hook in _HOOKS:
        try:
            hook(record)
        except Exception as exc:  # noqa: BLE001
            logger.debug("llm_trace 鉤子失敗（已忽略）：%s", exc)
