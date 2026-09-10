"""統一狀態存儲接口（優化 #7）。

提供統一的 StateStore 抽象層，底層適配多種存儲後端：
- Redis: 高性能鍵值存儲（生產環境）
- JSONL: 文件系統持久化（輕量部署）
- Memory: 記憶體存儲（測試用）

解決原系統狀態管理碎片化問題：
- EvoLoopState（LangGraph）→ StateStore
- CompanyRunState → StateStore
- Redis 持久化 → StateStore
- JSONL 存檔 → StateStore
"""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class StateStore(ABC):
    """狀態存儲抽象基類。"""

    @abstractmethod
    async def get(self, key: str) -> dict[str, Any] | None:
        """讀取狀態。"""
        ...

    @abstractmethod
    async def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        """寫入狀態（可選 TTL 秒數）。"""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """刪除狀態。"""
        ...

    @abstractmethod
    async def list_keys(self, prefix: str = "") -> list[str]:
        """列出匹配前綴的所有鍵。"""
        ...

    async def append(self, key: str, entry: dict[str, Any]) -> None:
        """追加一條記錄到列表狀態。"""
        existing = await self.get(key) or {"entries": []}
        if not isinstance(existing.get("entries"), list):
            existing["entries"] = []
        existing["entries"].append(entry)
        await self.set(key, existing)


class MemoryStateStore(StateStore):
    """記憶體狀態存儲（測試用）。"""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}
        self._expiry: dict[str, float] = {}

    async def get(self, key: str) -> dict[str, Any] | None:
        if key in self._expiry and time.monotonic() > self._expiry[key]:
            del self._data[key]
            del self._expiry[key]
            return None
        return self._data.get(key)

    async def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        self._data[key] = value
        if ttl:
            self._expiry[key] = time.monotonic() + ttl
        elif key in self._expiry:
            del self._expiry[key]

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    async def list_keys(self, prefix: str = "") -> list[str]:
        now = time.monotonic()
        return [
            k for k in self._data
            if k.startswith(prefix) and (k not in self._expiry or now <= self._expiry[k])
        ]


class JSONLStateStore(StateStore):
    """JSONL 文件狀態存儲（輕量部署）。"""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        resolved = base_dir or os.getenv(
            "EVOL_STATE_DIR",
            str(Path(__file__).resolve().parent.parent / "data" / "state"),
        ) or str(Path(__file__).resolve().parent.parent / "data" / "state")
        self._base_dir = Path(resolved)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        safe_key = key.replace("/", "_").replace("\\", "_").replace(":", "_")
        return self._base_dir / f"{safe_key}.json"

    async def get(self, key: str) -> dict[str, Any] | None:
        path = self._path_for(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("讀取狀態 %s 失敗：%s", key, exc)
            return None

    async def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        path = self._path_for(key)
        try:
            value["_updated_at"] = datetime.now(timezone.utc).isoformat()
            if ttl:
                value["_expires_at"] = time.time() + ttl
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("寫入狀態 %s 失敗：%s", key, exc)

    async def delete(self, key: str) -> None:
        path = self._path_for(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("刪除狀態 %s 失敗：%s", key, exc)

    async def list_keys(self, prefix: str = "") -> list[str]:
        keys = []
        for path in self._base_dir.glob("*.json"):
            key = path.stem
            if key.startswith(prefix):
                # 檢查是否過期
                data = await self.get(key)
                if data and "_expires_at" in data:
                    if time.time() > data["_expires_at"]:
                        await self.delete(key)
                        continue
                keys.append(key)
        return keys


class RedisStateStore(StateStore):
    """Redis 狀態存儲（生產環境）。"""

    def __init__(self, redis_url: str | None = None) -> None:
        self._url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = aioredis.from_url(self._url, decode_responses=True)
            except ImportError:
                logger.warning("redis 套件未安裝，降級為 MemoryStateStore")
                self._client = MemoryStateStore()
        return self._client

    async def get(self, key: str) -> dict[str, Any] | None:
        client = self._get_client()
        if isinstance(client, MemoryStateStore):
            return await client.get(key)
        try:
            data = await client.get(f"evoloop:{key}")
            return json.loads(data) if data else None
        except Exception as exc:
            logger.warning("Redis 讀取 %s 失敗：%s", key, exc)
            return None

    async def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> None:
        client = self._get_client()
        if isinstance(client, MemoryStateStore):
            return await client.set(key, value, ttl)
        try:
            data = json.dumps(value, ensure_ascii=False)
            if ttl:
                await client.setex(f"evoloop:{key}", ttl, data)
            else:
                await client.set(f"evoloop:{key}", data)
        except Exception as exc:
            logger.warning("Redis 寫入 %s 失敗：%s", key, exc)

    async def delete(self, key: str) -> None:
        client = self._get_client()
        if isinstance(client, MemoryStateStore):
            return await client.delete(key)
        try:
            await client.delete(f"evoloop:{key}")
        except Exception as exc:
            logger.warning("Redis 刪除 %s 失敗：%s", key, exc)

    async def list_keys(self, prefix: str = "") -> list[str]:
        client = self._get_client()
        if isinstance(client, MemoryStateStore):
            return await client.list_keys(prefix)
        try:
            keys = []
            async for key in client.scan_iter(match=f"evoloop:{prefix}*"):
                keys.append(key.replace("evoloop:", ""))
            return keys
        except Exception as exc:
            logger.warning("Redis 列舉鍵失敗：%s", exc)
            return []


# ── 工廠函數 ──

def create_state_store(backend: str | None = None) -> StateStore:
    """根據配置創建狀態存儲實例。

    Args:
        backend: 存儲後端類型（"redis" | "jsonl" | "memory"），
                 None 時自動選擇（有 REDIS_URL 用 Redis，否則用 JSONL）

    Returns:
        StateStore 實例
    """
    backend = backend or os.getenv("EVOL_STATE_BACKEND", "auto")

    if backend == "redis" or (backend == "auto" and os.getenv("REDIS_URL")):
        return RedisStateStore()
    elif backend == "memory":
        return MemoryStateStore()
    else:
        return JSONLStateStore()


# ── 模組級單例 ──
_store: StateStore | None = None


def get_state_store() -> StateStore:
    """取得全域狀態存儲單例。"""
    global _store
    if _store is None:
        _store = create_state_store()
    return _store
