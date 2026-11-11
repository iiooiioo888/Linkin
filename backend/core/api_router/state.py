"""API 路由的模組層狀態（鎖、加權輪詢計數、進行中請求）與 reset（自 backend.core.api_router 抽出）。"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger("backend.core.api_router")


_lock = threading.Lock()
_wrr_current: dict[str, int] = {}
_inflight: dict[str, int] = {}


def reset_router_state() -> None:
    """測試用：清空加權輪詢計數與進行中請求。"""
    with _lock:
        _wrr_current.clear()
        _inflight.clear()
