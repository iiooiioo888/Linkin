"""反思閉環全鏈路 trace 輔助（P3）。

在 LangGraph 節點中依 session_id / task_id 寫入 TraceLogger，
為後續成本與品質優化提供數據基礎。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_tracers: dict[str, Any] = {}


def get_pipeline_tracer(state: dict[str, Any]):
    """取得或建立與 state 關聯的 TraceLogger。"""
    trace_id = state.get("task_id") or state.get("session_id")
    if not trace_id:
        return None
    if trace_id not in _tracers:
        try:
            from backend.services.trace_logger import TraceLogger
            _tracers[trace_id] = TraceLogger(str(trace_id))
        except Exception as exc:
            logger.debug("TraceLogger 不可用：%s", exc)
            return None
    return _tracers.get(trace_id)


def log_node(state: dict[str, Any], node: str, **fields: Any) -> None:
    """記錄節點事件到 trace。"""
    tracer = get_pipeline_tracer(state)
    if tracer is None:
        return
    try:
        tracer._write("pipeline_node", {"node": node, **fields})
    except Exception as exc:
        logger.debug("trace 寫入失敗：%s", exc)


def clear_tracer(trace_id: str) -> None:
    _tracers.pop(trace_id, None)
