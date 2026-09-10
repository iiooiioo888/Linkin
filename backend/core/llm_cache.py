"""LLM 呼叫快取層（優化 #3）。

提供兩級快取：
1. 精確匹配快取：相同 prompt hash → 直接回傳歷史結果
2. 語義快取：embedding 相似度 > 閾值時復用（避免重複 API 呼叫）

快取策略：
- 反思迴圈中 evaluate/reflect/improve 的 prompt 高度相似
- 只快取成功的 LLM 回應（失敗/重試不快取）
- TTL 過期自動淘汰，記憶體用量有上限
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)

# ── 配置 ──
_CACHE_MAX_SIZE = int(os.getenv("EVOL_LLM_CACHE_SIZE", "512"))
_CACHE_TTL_SECONDS = int(os.getenv("EVOL_LLM_CACHE_TTL", "3600"))  # 1 小時
_SEMANTIC_CACHE_ENABLED = os.getenv("EVOL_SEMANTIC_CACHE", "true").lower() == "true"
_SEMANTIC_THRESHOLD = float(os.getenv("EVOL_SEMANTIC_THRESHOLD", "0.92"))  # 相似度 > 0.92 復用


class _CacheEntry:
    """快取條目。"""

    __slots__ = ("created_at", "hit_count", "model", "value")

    def __init__(self, value: str, model: str) -> None:
        self.value = value
        self.created_at = time.monotonic()
        self.hit_count = 0
        self.model = model

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > _CACHE_TTL_SECONDS

    def touch(self) -> str:
        self.hit_count += 1
        return self.value


class LLMCache:
    """兩級 LLM 回應快取。

    Level 1 — 精確匹配（O(1) hash lookup）
    Level 2 — 語義匹配（embedding cosine similarity）
    """

    def __init__(self) -> None:
        # Level 1: 精確快取 (prompt_hash, model) → _CacheEntry
        self._exact: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()
        # Level 2: 語義快取 (embedding_hash, model) → (embedding_vec, _CacheEntry)
        self._semantic: OrderedDict[tuple[str, str], tuple[list[float], _CacheEntry]] = OrderedDict()
        self._stats = {"hits": 0, "misses": 0, "semantic_hits": 0, "evictions": 0}

    # ── 公開介面 ──

    def get(self, prompt: str, system: str | None, model: str) -> str | None:
        """查詢快取，命中時回傳結果，否則回傳 None。"""
        cache_key = self._make_key(prompt, system, model)

        # Level 1: 精確匹配
        entry = self._exact.get(cache_key)
        if entry is not None:
            if entry.expired:
                del self._exact[cache_key]
                self._stats["evictions"] += 1
            else:
                self._exact.move_to_end(cache_key)
                self._stats["hits"] += 1
                logger.debug("LLM 快取命中（精確）：key=%s", cache_key[0][:12])
                return entry.touch()

        # Level 2: 語義匹配（需要 embedding 計算，僅在啟用時執行）
        if _SEMANTIC_CACHE_ENABLED and self._semantic:
            result = self._semantic_search(prompt, model)
            if result is not None:
                self._stats["semantic_hits"] += 1
                return result

        self._stats["misses"] += 1
        return None

    def put(self, prompt: str, system: str | None, model: str, response: str) -> None:
        """將成功的 LLM 回應存入快取。"""
        cache_key = self._make_key(prompt, system, model)
        entry = _CacheEntry(response, model)

        # Level 1: 精確快取
        self._exact[cache_key] = entry
        self._evict_if_needed(self._exact)

        # Level 2: 語義快取（計算 embedding 並儲存）
        if _SEMANTIC_CACHE_ENABLED:
            try:
                vec = self._compute_embedding(prompt)
                sem_key = self._semantic_key(prompt, model)
                self._semantic[sem_key] = (vec, entry)
                self._evict_if_needed(self._semantic)
            except Exception as exc:
                logger.debug("語義快取 embedding 計算失敗（跳過）：%s", exc)

    def invalidate(self) -> None:
        """清空所有快取。"""
        self._exact.clear()
        self._semantic.clear()

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    @property
    def size(self) -> int:
        """目前快取條目數（精確 + 語義）。"""
        return len(self._exact) + len(self._semantic)

    # ── 內部方法 ──

    @staticmethod
    def _make_key(prompt: str, system: str | None, model: str) -> tuple[str, str]:
        """生成精確快取 key（prompt + system 的 hash）。"""
        content = f"{system or ''}\x00{prompt}"
        h = hashlib.sha256(content.encode()).hexdigest()[:32]
        return (h, model)

    @staticmethod
    def _semantic_key(prompt: str, model: str) -> tuple[str, str]:
        """生成語義快取 key。"""
        h = hashlib.md5(prompt.encode()).hexdigest()[:16]
        return (h, model)

    def _semantic_search(self, prompt: str, model: str) -> str | None:
        """在語義快取中查找最相似的條目。"""
        try:
            query_vec = self._compute_embedding(prompt)
        except Exception:
            return None

        best_sim = 0.0
        best_entry: _CacheEntry | None = None

        for key, (vec, entry) in list(self._semantic.items()):
            if key[1] != model:
                continue
            if entry.expired:
                del self._semantic[key]
                self._stats["evictions"] += 1
                continue
            sim = self._cosine_similarity(query_vec, vec)
            if sim > best_sim:
                best_sim = sim
                best_entry = entry

        if best_entry is not None and best_sim >= _SEMANTIC_THRESHOLD:
            self._stats["hits"] += 1
            logger.debug(
                "LLM 快取命中（語義）：sim=%.4f threshold=%.4f",
                best_sim, _SEMANTIC_THRESHOLD,
            )
            return best_entry.touch()

        return None

    @staticmethod
    def _compute_embedding(text: str) -> list[float]:
        """計算文本 embedding（使用 LiteLLM）。"""
        from litellm import embedding as litellm_embedding

        embed_model = os.getenv("EVOL_EMBED_MODEL", "text-embedding-3-small")
        response = litellm_embedding(model=embed_model, input=[text])
        return response.data[0]["embedding"]

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """計算兩個向量的餘弦相似度。"""
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _evict_if_needed(self, cache: OrderedDict) -> None:
        """LRU 淘汰：超過上限時移除最舊條目。"""
        while len(cache) > _CACHE_MAX_SIZE:
            cache.popitem(last=False)
            self._stats["evictions"] += 1


# ── 模組級單例 ──
_llm_cache: LLMCache | None = None


def get_llm_cache() -> LLMCache:
    """取得全域 LLM 快取單例。"""
    global _llm_cache
    if _llm_cache is None:
        _llm_cache = LLMCache()
    return _llm_cache
