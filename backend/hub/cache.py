"""語義快取：Redis Key = semantic:md5(user_id:strategy:意圖摘要)，TTL=86400。"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

SEMANTIC_TTL_S = 86400
INTENT_MAX_CHARS = 512


def normalize_intent(text: str) -> str:
    nfkc = unicodedata.normalize("NFKC", text or "")
    collapsed = re.sub(r"\s+", " ", nfkc).strip().lower()
    return collapsed[:INTENT_MAX_CHARS]


def last_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                str(p.get("text") or "")
                for p in content
                if isinstance(p, dict) and p.get("type") == "text"
            ]
            return " ".join(parts)
    return ""


def semantic_key(user_id: str, strategy: str, messages: list[dict[str, Any]]) -> str:
    digest = hashlib.md5(
        f"{user_id}:{strategy}:{normalize_intent(last_user_text(messages))}".encode(),
        usedforsecurity=False,
    ).hexdigest()
    return f"semantic:{digest}"


def should_bypass_cache(
    temperature: float,
    stream: bool,
    multimodal: bool,
) -> bool:
    return temperature > 0.2 or stream or multimodal


class SemanticCache:
    """進程內語義快取（無 Redis 時使用）；介面與 Redis STRING + ZSET 對齊。"""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._hot: dict[str, int] = {}
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict[str, Any] | None:
        raw = self._store.get(key)
        if not raw:
            self.misses += 1
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._store.pop(key, None)
            self.misses += 1
            return None
        self.hits += 1
        md5 = key.split(":", 1)[-1]
        self._hot[md5] = self._hot.get(md5, 0) + 1
        return payload

    def set(self, key: str, value: dict[str, Any]) -> None:
        self._store[key] = json.dumps(value, ensure_ascii=False)

    def hit_rate(self) -> float:
        total = self.hits + self.misses
        if total == 0:
            return 0.0
        return self.hits / total

    def reset(self) -> None:
        self._store.clear()
        self._hot.clear()
        self.hits = 0
        self.misses = 0
