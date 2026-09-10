"""Phase 2 向量記憶庫：ChromaDB 封裝（Task 2.1 / 2.3）。

取代 Phase 1 的 JSON 暫存（json_store.py），介面保持一致
（add_memory / search_similar / all / reset），另提供
cleanup 供記憶維護使用。

連線方式：
- 設定 CHROMA_HOST（與 CHROMA_PORT）時使用 HttpClient，
  對應 docker-compose 中的 chroma 服務
- 未設定時使用本地 PersistentClient，目錄可透過
  EVOL_CHROMA_DIR 覆蓋（測試隔離）

嵌入模型走 LiteLLM 統一呼叫層（EVOL_EMBED_MODEL），
可注入自訂 embedding function（測試用，避免真實 API 呼叫）。
"""

import hashlib
import logging
import os
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from litellm import embedding

load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "evo_memory"
DEFAULT_EMBED_MODEL = "text-embedding-3-small"

# 預設本地持久目錄：backend/data/chroma
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "data" / "chroma"


class LiteLLMEmbeddingFunction:
    """符合 ChromaDB embedding function 協定的 LiteLLM 包裝。"""

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("EVOL_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    def __call__(self, input: Sequence[str]) -> list[list[float]]:
        response = embedding(model=self.model, input=list(input))
        return [item["embedding"] for item in response.data]

    @staticmethod
    def name() -> str:
        return "litellm_embedding"


def _sanitize_metadata(metadata: dict | None) -> dict:
    """ChromaDB metadata 僅支援純量型別，過濾 None 並轉換其餘值。"""
    cleaned: dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned


# ── 檢索快取（LRU）──
# 相同查詢短時間內重複檢索時，避免重複呼叫嵌入 API
_SEARCH_CACHE_MAX_SIZE = int(os.getenv("EVOL_SEARCH_CACHE_SIZE", "128"))
# 自適應相似度門檻（優化 #5）：基於歷史 distance 分布計算
_ADAPTIVE_THRESHOLD_PERCENTILE = float(os.getenv("EVOL_THRESHOLD_PERCENTILE", "75"))


class VectorMemoryStore:
    """以 ChromaDB 儲存的向量記憶庫。

    連線與 collection 皆惰性初始化，匯入本模組不會產生
    外部連線，方便測試替換與離線環境使用。

    檢索快取：LRU 快取查詢結果，減少重複嵌入 API 呼叫。
    相似度門檻：distance > EVOL_SIMILARITY_THRESHOLD 的結果不注入。
    """

    def __init__(
        self,
        collection_name: str | None = None,
        embedding_function: Any | None = None,
    ):
        self.collection_name = collection_name or os.getenv(
            "EVOL_CHROMA_COLLECTION", DEFAULT_COLLECTION
        )
        self._embedding_function = embedding_function
        self._client: Any = None
        self._collection: Any = None
        # LRU 快取：key = (query_hash, k) → results
        self._search_cache: OrderedDict[tuple[str, int], list[dict]] = OrderedDict()
        # 基礎相似度門檻（distance 越小越相似，超過此值不注入）
        self.similarity_threshold = float(os.getenv("EVOL_SIMILARITY_THRESHOLD", "1.2"))
        # 自適應門檻：基於歷史 distance 分布動態調整（優化 #5）
        self._distance_history: list[float] = []
        self._adaptive_threshold: float | None = None

    # ---- 連線（惰性） ----

    def _create_client(self) -> Any:
        import chromadb

        from backend.memory.chroma_compat import apply_chromadb_sql_txt_compat

        apply_chromadb_sql_txt_compat()
        host = os.getenv("CHROMA_HOST")
        port = int(os.getenv("CHROMA_PORT", "8100"))
        if host:
            logger.debug("連接 ChromaDB 伺服器 %s:%s", host, port)
            return chromadb.HttpClient(host=host, port=port)
        persist_dir = Path(os.getenv("EVOL_CHROMA_DIR", str(DEFAULT_PERSIST_DIR)))
        persist_dir.mkdir(parents=True, exist_ok=True)
        logger.debug("使用本地 ChromaDB 持久目錄 %s", persist_dir)
        return chromadb.PersistentClient(path=str(persist_dir))

    def _get_collection(self) -> Any:
        if self._collection is None:
            if self._client is None:
                self._client = self._create_client()
            if self._embedding_function is None:
                self._embedding_function = LiteLLMEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self._embedding_function,
            )
        return self._collection

    # ---- 核心介面 ----

    def add_memory(
        self, text: str, metadata: dict | None = None, memory_id: str | None = None
    ) -> str:
        """新增一筆記憶（文字嵌入後儲存），回傳記錄 ID。

        優化 #12：新增前檢查是否已存在高度相似的記憶（去重）。
        相似度 > 0.95 時跳過新增，避免重複記憶堆積。
        """
        # 去重檢查：查詢是否有高度相似的現有記憶
        try:
            existing = self.search_similar(text, k=1)
            if existing and existing[0].get("distance", 999) < 0.05:
                logger.debug("記憶去重：跳過高度相似的記憶（distance=%.4f）", existing[0]["distance"])
                return existing[0]["metadata"].get("_id", "duplicate")
        except Exception:
            pass  # 去重失敗不阻斷新增

        meta = _sanitize_metadata(metadata)
        meta.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record_id = memory_id or uuid.uuid4().hex
        self._get_collection().add(
            documents=[text], metadatas=[meta], ids=[record_id]
        )
        # 新增記憶後使快取失效，確保後續檢索能取得最新結果
        self.invalidate_cache()
        return record_id

    def search_similar(self, query: str, k: int = 3) -> list[dict]:
        """檢索與查詢最相似的 k 筆記憶（優化 #5）。

        回傳 [{"text": ..., "metadata": ..., "distance": ...}, ...]，
        distance 越小越相似；記憶庫為空時回傳空列表。

        優化：
        - LRU 快取：相同查詢直接回傳快取結果
        - 自適應相似度門檻：基於歷史 distance 分布動態調整
        - 高分正樣本也參與檢索
        """
        if k <= 0:
            return []

        # ── LRU 快取查詢（使用語義友好的 hash）──
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:24]
        cache_key = (query_hash, k)
        if cache_key in self._search_cache:
            self._search_cache.move_to_end(cache_key)
            return self._search_cache[cache_key]

        collection = self._get_collection()
        total = collection.count()
        if total == 0:
            self._search_cache[cache_key] = []
            return []

        results = collection.query(
            query_texts=[query], n_results=min(k, total)
        )

        # 取得當前有效門檻
        threshold = self._get_effective_threshold()

        memories = []
        for text, meta, distance in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # 自適應門檻過濾
            if distance > threshold:
                continue
            memories.append({"text": text, "metadata": meta, "distance": distance})
            # 記錄 distance 用於自適應門檻計算
            self._distance_history.append(distance)

        # 保持歷史記錄在合理範圍
        if len(self._distance_history) > 1000:
            self._distance_history = self._distance_history[-500:]
            self._adaptive_threshold = None  # 強制重新計算

        # ── 寫入快取（LRU 淘汰）──
        self._search_cache[cache_key] = memories
        if len(self._search_cache) > _SEARCH_CACHE_MAX_SIZE:
            self._search_cache.popitem(last=False)

        return memories

    def _get_effective_threshold(self) -> float:
        """取得有效的相似度門檻（自適應或靜態）。"""
        if not self._distance_history:
            return self.similarity_threshold

        # 定期重新計算自適應門檻
        if self._adaptive_threshold is None or len(self._distance_history) % 50 == 0:
            sorted_dists = sorted(self._distance_history)
            idx = int(len(sorted_dists) * _ADAPTIVE_THRESHOLD_PERCENTILE / 100)
            idx = min(idx, len(sorted_dists) - 1)
            adaptive = sorted_dists[idx]
            # 不低於靜態門檻的 50%，不超過靜態門檻
            self._adaptive_threshold = max(
                self.similarity_threshold * 0.5,
                min(adaptive, self.similarity_threshold),
            )

        return self._adaptive_threshold or self.similarity_threshold

    def invalidate_cache(self) -> None:
        """清空檢索快取（新增記憶後可呼叫）。"""
        self._search_cache.clear()

    def all(self) -> list[dict]:
        """回傳全部記憶（含 metadata）。"""
        data = self._get_collection().get(include=["documents", "metadatas"])
        ids = data.get("ids") or []
        documents = data.get("documents") or [""] * len(ids)
        metadatas = data.get("metadatas") or [{}] * len(ids)
        return [
            {"id": record_id, "text": text or "", "metadata": meta or {}}
            for record_id, text, meta in zip(ids, documents, metadatas)
        ]

    def count(self) -> int:
        """回傳記憶總數。"""
        return self._get_collection().count()

    def reset(self) -> None:
        """清空記憶庫（刪除並重建 collection）。"""
        if self._client is None:
            self._client = self._create_client()
        self._client.delete_collection(self.collection_name)
        self._collection = None
        self._get_collection()

    # ---- 維護（Task 2.3） ----

    def cleanup(self, max_age_days: int = 30, min_score: float | None = None) -> int:
        """刪除過期或低品質記憶，回傳刪除筆數。

        - 過期：created_at 早於 max_age_days 天前
        - 低品質：metadata.score 低於 min_score（有設定時）
        """
        collection = self._get_collection()
        data = collection.get(include=["metadatas"])
        if not data["ids"]:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        stale_ids = []
        for record_id, meta in zip(data["ids"], data["metadatas"]):
            meta = meta or {}
            expired = False
            try:
                created = datetime.fromisoformat(meta.get("created_at", ""))
                expired = created < cutoff
            except (TypeError, ValueError):
                pass
            score = meta.get("score")
            low_quality = (
                min_score is not None
                and isinstance(score, (int, float))
                and score < min_score
            )
            if expired or low_quality:
                stale_ids.append(record_id)

        if stale_ids:
            collection.delete(ids=stale_ids)
        return len(stale_ids)

    def distill(self, max_age_days: int = 7, batch_size: int = 20) -> int:
        """記憶蒸餾（優化 #15）：將同主題的舊記憶合併為摘要。

        當記憶庫累積大量相似記憶時，檢索噪音增大。
        蒸餾通過 LLM 將多條相關記憶合併為一條高質量摘要，
        減少數量同時保留核心知識。

        Args:
            max_age_days: 蒸餾幾天前的記憶
            batch_size: 每批處理數量

        Returns:
            蒸餾後刪除的記憶筆數
        """
        from backend.core.llm import call_llm

        collection = self._get_collection()
        data = collection.get(include=["documents", "metadatas"])
        if not data["ids"]:
            return 0

        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        # 篩選可蒸餾的記憶（舊的、經歷過反思的）
        candidates: list[tuple[str, str, dict]] = []
        for record_id, text, meta in zip(data["ids"], data["documents"], data["metadatas"]):
            meta = meta or {}
            try:
                created = datetime.fromisoformat(meta.get("created_at", ""))
                if created >= cutoff:
                    continue
            except (TypeError, ValueError):
                continue
            # 只蒸餾反思類記憶（正樣本保留）
            if meta.get("type") == "reflection":
                candidates.append((record_id, text, meta))

        if len(candidates) < 3:
            return 0  # 太少不值得蒸餾

        distilled_count = 0
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            if len(batch) < 2:
                continue

            # 將同批記憶合併為摘要
            texts = [f"{j+1}. {t[:500]}" for j, (_, t, _) in enumerate(batch)]
            prompt = (
                "請將以下記憶摘要合併為一條精煉的核心知識（保留關鍵經驗，去除重複）：\n\n"
                + "\n".join(texts)
                + "\n\n只輸出合併後的摘要文字，不要加編號或標題："
            )

            try:
                summary = call_llm(prompt, temperature=0.3)
                avg_score = sum(m.get("score", 7) for _, _, m in batch) / len(batch)

                # 用摘要替換原始記憶
                self.add_memory(
                    f"【蒸餾摘要】{summary}",
                    metadata={
                        "score": round(avg_score, 1),
                        "type": "distilled",
                        "source_count": len(batch),
                    },
                )

                # 刪除原始記憶
                ids_to_delete = [rid for rid, _, _ in batch]
                collection.delete(ids=ids_to_delete)
                distilled_count += len(ids_to_delete)

                logger.info("蒸餾 %d 條記憶為 1 條摘要", len(batch))

            except Exception as exc:
                logger.warning("記憶蒸餾失敗（跳過本批）：%s", exc)

        self.invalidate_cache()
        return distilled_count
