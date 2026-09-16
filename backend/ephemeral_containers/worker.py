"""背景 worker：從隊列取出臨時容器任務並執行。"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Any

from backend.ephemeral_containers.broadcaster import container_task_broadcaster
from backend.ephemeral_containers.docker_exec import get_docker_executor
from backend.ephemeral_containers.store import ContainerTaskRecord, container_task_store

logger = logging.getLogger(__name__)


class ContainerTaskWorker:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_events: dict[str, threading.Event] = {}

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def enqueue(self, task_id: str) -> None:
        self._queue.put_nowait(task_id)

    async def _run_loop(self) -> None:
        while True:
            task_id = await self._queue.get()
            try:
                await asyncio.to_thread(self._execute_sync, task_id)
            except Exception as exc:
                logger.exception("worker 執行失敗 %s", task_id)
            finally:
                self._queue.task_done()

    def _execute_sync(self, task_id: str) -> None:
        record = container_task_store.get(task_id)
        if record is None or record.status not in {"queued"}:
            return
        executor = get_docker_executor()
        if not executor.available():
            record.status = "failed"
            record.error = "Docker 不可用"
            record.finished_at = time.time()
            container_task_store.save(record)
            self._notify_done(record)
            return

        record.status = "running"
        record.started_at = time.time()
        container_task_store.save(record)
        self._notify_event(record, "status", {"status": "running"})

        stop_event = threading.Event()
        self._stop_events[task_id] = stop_event
        loop = self._loop

        def on_log(chunk: str) -> None:
            record.append_log(chunk)
            if loop and loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    container_task_broadcaster.broadcast(
                        task_id,
                        "log",
                        {"chunk": chunk},
                    ),
                    loop,
                )

        result = executor.run(task_id, record.spec, on_log, stop_event=stop_event)
        self._stop_events.pop(task_id, None)

        record.container_id = result.container_id
        record.exit_code = result.exit_code
        record.finished_at = time.time()
        if result.error == "timeout":
            record.status = "timed_out"
            record.error = f"超過 {record.spec.timeout_sec}s 已強制終止"
        elif result.error == "cancelled":
            record.status = "cancelled"
            record.error = "已取消"
        elif result.error:
            record.status = "failed"
            record.error = result.error
        elif result.exit_code == 0:
            record.status = "succeeded"
        else:
            record.status = "failed"
            record.error = f"exit code {result.exit_code}"

        container_task_store.save(record)
        self._notify_done(record)

    def _notify_event(self, record: ContainerTaskRecord, event: str, data: dict[str, Any]) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(
                container_task_broadcaster.broadcast(record.task_id, event, data),
                self._loop,
            )

    def _notify_done(self, record: ContainerTaskRecord) -> None:
        self._notify_event(
            record,
            "finished",
            {
                "status": record.status,
                "exit_code": record.exit_code,
                "error": record.error,
                "snapshot": record.to_dict(),
            },
        )


container_task_worker = ContainerTaskWorker()
