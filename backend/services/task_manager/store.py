"""任務儲存 mixin（StoreMixin）：記憶體狀態、Redis 連線與持久化／回填。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from backend.company.orchestrator import CompanyOrchestrator

from ._base import (
    COMPANY_PERSIST_DEBOUNCE_SEC,
    COMPANY_PERSIST_EVERY_N,
    REDIS_URL,
    TASK_KEY_PREFIX,
    TASK_TTL_SECONDS,
    TaskManagerBase,
)
from ._compat import load_checkpoint
from .models import TaskRecord

if TYPE_CHECKING:
    import redis

logger = logging.getLogger(__name__)


class StoreMixin(TaskManagerBase):
    """記憶體狀態、Redis 連線與持久化／回填。"""

    def __init__(self) -> None:
        self.tasks: dict[str, TaskRecord] = {}
        self._redis: redis.Redis | None = None
        self._redis_failed = False
        # 執行中的公司 orchestrator 引用（task_id → orchestrator），供取消使用
        self._orchestrators: dict[str, CompanyOrchestrator] = {}
        # 執行中的 asyncio.Task 引用（task_id → Task）：取消時寬限期後強制中斷
        self._running_tasks: dict[str, asyncio.Task] = {}
        # 主 event loop（lifespan 設定）：供 worker 執行緒／外部行程安全派發任務
        self._loop: asyncio.AbstractEventLoop | None = None
        # 公司任務 Redis 快照防抖（執行中事件批寫）
        self._persist_pending: dict[str, asyncio.TimerHandle] = {}
        self._persist_event_counters: dict[str, int] = {}

    # ── Redis 持久化 ──

    def _get_redis(self) -> redis.Redis | None:
        """惰性取得 Redis 連線；失敗後不再重試（降級為記憶體）。"""
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
            logger.info("任務持久化：Redis 連線成功")
            return client
        except Exception as exc:
            logger.warning("任務持久化：Redis 不可用，降級為記憶體：%s", exc)
            self._redis_failed = True
            return None

    def _persist(self, record: TaskRecord) -> None:
        """將任務快照寫入 Redis（盡力而為）。"""
        client = self._get_redis()
        if client is None:
            return
        try:
            client.set(
                TASK_KEY_PREFIX + record.task_id,
                json.dumps(record.to_snapshot(), ensure_ascii=False),
                ex=TASK_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("任務持久化寫入失敗：%s", exc)

    def _should_batch_persist(self, record: TaskRecord) -> bool:
        return record.resolved_path == "company" and record.status == "running"

    def _cancel_scheduled_persist(self, task_id: str) -> None:
        handle = self._persist_pending.pop(task_id, None)
        if handle is not None:
            handle.cancel()

    def _flush_persist(self, task_id: str) -> None:
        record = self.tasks.get(task_id) or self.get_task(task_id)
        if record is not None:
            self._persist(record)

    def _schedule_persist(self, record: TaskRecord, *, force: bool = False) -> None:
        if force or not self._should_batch_persist(record):
            self._cancel_scheduled_persist(record.task_id)
            self._persist(record)
            return
        tid = record.task_id
        count = self._persist_event_counters.get(tid, 0) + 1
        self._persist_event_counters[tid] = count
        if count % COMPANY_PERSIST_EVERY_N == 0:
            self._cancel_scheduled_persist(tid)
            self._persist(record)
            return
        self._cancel_scheduled_persist(tid)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._persist(record)
            return

        def _fire() -> None:
            self._persist_pending.pop(tid, None)
            self._flush_persist(tid)

        self._persist_pending[tid] = loop.call_later(COMPANY_PERSIST_DEBOUNCE_SEC, _fire)

    def _load_from_redis(self, task_id: str) -> TaskRecord | None:
        client = self._get_redis()
        if client is None:
            return None
        try:
            raw = client.get(TASK_KEY_PREFIX + task_id)
            if not raw:
                return None
            if not isinstance(raw, (str, bytes, bytearray)):
                return None
            record = TaskRecord.from_snapshot(json.loads(raw))
            # 唯讀回傳：interrupted 標記只由啟動時 rehydrate 負責。
            # 這裡若改狀態，跨行程讀取（MCP stdio 子行程讀主服務正在跑的
            # 任務）會把活任務誤標中斷並持久化。
            return record
        except Exception as exc:
            logger.warning("任務記錄讀取失敗：%s", exc)
            return None

    def rehydrate(self) -> int:
        """啟動時從 Redis 載回任務記錄（修復：重啟後任務列表／管線清空）。

        掃描 evoloop:task:* 全部快照還原進記憶體；殘留的 pending/running
        標記為中斷失敗（與 _load_from_redis 同一語意）。
        """
        client = self._get_redis()
        if client is None:
            return 0
        loaded = 0
        try:
            keys = list(client.scan_iter(match=TASK_KEY_PREFIX + "*", count=500))
        except Exception as exc:
            logger.warning("任務 rehydrate 掃描失敗：%s", exc)
            return 0
        for key in keys:
            try:
                raw = client.get(key)
                if not raw or not isinstance(raw, (str, bytes, bytearray)):
                    continue
                record = TaskRecord.from_snapshot(json.loads(raw))
                if record.status in ("pending", "running"):
                    record.status = "interrupted"
                    record.error = record.error or "後端服務重啟，任務中斷"
                    if record.resolved_path == "company":
                        record.resumable = load_checkpoint(record.task_id) is not None
                    self._persist(record)
                self.tasks.setdefault(record.task_id, record)
                loaded += 1
            except Exception as exc:
                logger.debug("任務 rehydrate 跳過 %s：%s", key, exc)
        if loaded:
            logger.info("任務 rehydrate：自 Redis 載回 %d 筆記錄", loaded)
        return loaded

    def delete_task_record(self, task_id: str) -> bool:
        """自記憶體與 Redis 移除任務記錄（過期清理用）。"""
        self.tasks.pop(task_id, None)
        client = self._get_redis()
        if client is None:
            return True
        try:
            client.delete(TASK_KEY_PREFIX + task_id)
            return True
        except Exception as exc:
            logger.warning("任務記錄刪除失敗：task_id=%s, %s", task_id, exc)
            return False

    def iter_all_records(self) -> list[TaskRecord]:
        """合併記憶體與 Redis 中的任務記錄（清理掃描用）。"""
        seen: set[str] = set()
        records: list[TaskRecord] = []
        for record in self.tasks.values():
            if record.task_id not in seen:
                seen.add(record.task_id)
                records.append(record)
        client = self._get_redis()
        if client is None:
            return records
        try:
            keys = list(client.scan_iter(match=TASK_KEY_PREFIX + "*", count=500))
        except Exception as exc:
            logger.warning("任務掃描失敗：%s", exc)
            return records
        for key in keys:
            task_id = key.removeprefix(TASK_KEY_PREFIX) if isinstance(key, str) else str(key)[len(TASK_KEY_PREFIX):]
            if task_id in seen:
                continue
            loaded = self._load_from_redis(task_id)
            if loaded is not None:
                seen.add(task_id)
                records.append(loaded)
        return records
