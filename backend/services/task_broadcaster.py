"""任务事件广播器：WebSocket 实时推送任务进度。

支持：
- 按 task_id 订阅/取消订阅
- 事件广播到所有订阅者
- 连接断开自动清理
- 降级兼容：无 WebSocket 时仍可轮询
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class TaskBroadcaster:
    """管理 WebSocket 连接并广播任务事件。"""

    def __init__(self) -> None:
        # task_id -> set of WebSocket connections
        self._subscribers: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str, websocket: WebSocket) -> None:
        """订阅任务事件。"""
        async with self._lock:
            if task_id not in self._subscribers:
                self._subscribers[task_id] = set()
            self._subscribers[task_id].add(websocket)
            logger.debug("WebSocket 订阅任务 %s（当前 %d 个连接）", 
                        task_id, len(self._subscribers[task_id]))

    async def unsubscribe(self, task_id: str, websocket: WebSocket) -> None:
        """取消订阅任务事件。"""
        async with self._lock:
            if task_id in self._subscribers:
                self._subscribers[task_id].discard(websocket)
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]
                logger.debug("WebSocket 取消订阅任务 %s", task_id)

    async def broadcast(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        """向任务的所有订阅者广播事件。

        自动清理已断开的连接。
        """
        async with self._lock:
            subscribers = self._subscribers.get(task_id, set()).copy()

        if not subscribers:
            return

        message = {"task_id": task_id, "event": event, "data": data}
        dead_connections: list[WebSocket] = []

        for websocket in subscribers:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_connections.append(websocket)

        # 清理断开的连接
        if dead_connections:
            async with self._lock:
                if task_id in self._subscribers:
                    for ws in dead_connections:
                        self._subscribers[task_id].discard(ws)
                    if not self._subscribers[task_id]:
                        del self._subscribers[task_id]

    def get_subscriber_count(self, task_id: str) -> int:
        """获取任务的订阅者数量。"""
        return len(self._subscribers.get(task_id, set()))

    def has_subscribers(self, task_id: str) -> bool:
        """检查任务是否有订阅者。"""
        return task_id in self._subscribers and len(self._subscribers[task_id]) > 0


# 全局单例
task_broadcaster = TaskBroadcaster()