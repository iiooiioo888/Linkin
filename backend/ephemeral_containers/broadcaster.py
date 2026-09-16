"""臨時容器任務 WebSocket 廣播。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ContainerTaskBroadcaster:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._subscribers.setdefault(task_id, set()).add(websocket)

    async def unsubscribe(self, task_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if task_id in self._subscribers:
                self._subscribers[task_id].discard(websocket)
                if not self._subscribers[task_id]:
                    del self._subscribers[task_id]

    async def broadcast(self, task_id: str, event: str, data: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(task_id, set()).copy()
        if not subscribers:
            return
        message = {"task_id": task_id, "event": event, "data": data}
        dead: list[WebSocket] = []
        for ws in subscribers:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    if task_id in self._subscribers:
                        self._subscribers[task_id].discard(ws)


container_task_broadcaster = ContainerTaskBroadcaster()
