"""臨時容器任務狀態：記憶體 + Redis 持久化。"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from backend.ephemeral_containers.config import REDIS_KEY_PREFIX, TASK_TTL_SECONDS
from backend.ephemeral_containers.models import ContainerTaskCreate

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


@dataclass
class ContainerTaskRecord:
    task_id: str
    spec: ContainerTaskCreate
    status: str = "queued"  # queued | running | succeeded | failed | timed_out | cancelled
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    error: str = ""
    logs: str = ""
    logs_truncated: bool = False
    container_id: str = ""
    artifacts: list[str] = field(default_factory=list)
    submitted_by: str = ""

    def append_log(self, chunk: str) -> None:
        from backend.ephemeral_containers.config import MAX_LOG_CHARS, MAX_LOG_LINES_STORED

        if not chunk:
            return
        combined = self.logs + chunk
        if len(combined) > MAX_LOG_CHARS:
            self.logs = combined[-MAX_LOG_CHARS:]
            self.logs_truncated = True
        else:
            self.logs = combined
        lines = self.logs.count("\n")
        if lines > MAX_LOG_LINES_STORED:
            parts = self.logs.splitlines()
            self.logs = "\n".join(parts[-MAX_LOG_LINES_STORED:]) + "\n"
            self.logs_truncated = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "image": self.spec.image,
            "command": self.spec.command,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "exit_code": self.exit_code,
            "error": self.error,
            "logs_tail": self.logs[-12000:] if self.logs else "",
            "logs_truncated": self.logs_truncated,
            "container_id": self.container_id,
            "limits": self.spec.runtime_limits(),
            "artifacts": self.artifacts,
        }

    def to_snapshot(self) -> dict[str, Any]:
        data = self.to_dict()
        data["logs"] = self.logs
        data["spec"] = self.spec.model_dump()
        data["submitted_by"] = self.submitted_by
        return data

    @classmethod
    def from_snapshot(cls, data: dict[str, Any]) -> ContainerTaskRecord:
        spec_raw = data.get("spec")
        if not spec_raw:
            spec_raw = {
                "image": data.get("image", "python:3.12-slim"),
                "command": data.get("command") or ["echo", "ok"],
            }
        spec = ContainerTaskCreate.model_validate(spec_raw)
        rec = cls(
            task_id=data["task_id"],
            spec=spec,
            status=data.get("status", "failed"),
            created_at=float(data.get("created_at", time.time())),
            submitted_by=str(data.get("submitted_by", "")),
        )
        rec.started_at = data.get("started_at")
        rec.finished_at = data.get("finished_at")
        ec = data.get("exit_code")
        rec.exit_code = int(ec) if ec is not None else None
        rec.error = str(data.get("error", ""))
        rec.logs = str(data.get("logs", ""))
        rec.logs_truncated = bool(data.get("logs_truncated", False))
        rec.container_id = str(data.get("container_id", ""))
        rec.artifacts = list(data.get("artifacts") or [])
        return rec


class ContainerTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, ContainerTaskRecord] = {}
        self._redis: Any = None
        self._redis_failed = False

    def _get_redis(self) -> Any:
        if self._redis is not None:
            return self._redis
        if self._redis_failed:
            return None
        try:
            import redis

            client = redis.Redis.from_url(
                REDIS_URL, decode_responses=True, socket_connect_timeout=2
            )
            client.ping()
            self._redis = client
            return client
        except Exception as exc:
            logger.warning("臨時容器任務 Redis 不可用：%s", exc)
            self._redis_failed = True
            return None

    def _persist(self, record: ContainerTaskRecord) -> None:
        client = self._get_redis()
        if client is None:
            return
        try:
            client.set(
                REDIS_KEY_PREFIX + record.task_id,
                json.dumps(record.to_snapshot(), ensure_ascii=False),
                ex=TASK_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("臨時容器任務寫入 Redis 失敗：%s", exc)

    def create(self, spec: ContainerTaskCreate, submitted_by: str = "") -> ContainerTaskRecord:
        task_id = f"ect-{uuid.uuid4().hex[:12]}"
        record = ContainerTaskRecord(task_id=task_id, spec=spec, submitted_by=submitted_by)
        self._tasks[task_id] = record
        self._persist(record)
        return record

    def get(self, task_id: str) -> ContainerTaskRecord | None:
        rec = self._tasks.get(task_id)
        if rec is not None:
            return rec
        client = self._get_redis()
        if client is None:
            return None
        try:
            raw = client.get(REDIS_KEY_PREFIX + task_id)
            if not raw:
                return None
            loaded = ContainerTaskRecord.from_snapshot(json.loads(raw))
            self._tasks[task_id] = loaded
            return loaded
        except Exception:
            return None

    def save(self, record: ContainerTaskRecord) -> None:
        self._tasks[record.task_id] = record
        self._persist(record)


container_task_store = ContainerTaskStore()
