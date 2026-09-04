"""靈境 Chroma 四庫：寫入前四維評分 ≥80，失敗降級 JSON。"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.core.evaluation import DIMENSION_NAMES, EvaluationResult, MultiDimensionalEvaluator
from backend.linkin.tools import QUALITY_THRESHOLD, SIMILARITY_THRESHOLD

logger = logging.getLogger(__name__)

COL_WORLDVIEW = "linkin_worldview"
COL_NPCS = "linkin_npcs"
COL_EVENTS = "linkin_events"
COL_PLAYERS = "linkin_players"
COLLECTIONS = (COL_WORLDVIEW, COL_NPCS, COL_EVENTS, COL_PLAYERS)

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "linkin"

_lock = threading.Lock()
_store: "LinkinKnowledgeStore | None" = None


class QualityGateError(ValueError):
    """四維度評分未達 80。"""

    def __init__(self, message: str, evaluation: dict[str, Any]):
        super().__init__(message)
        self.evaluation = evaluation


class HashEmbeddingFunction:
    """離線雜湊嵌入，避免 Linkin RAG 依賴真實嵌入 API。"""

    def __init__(self, dim: int = 64):
        self.dim = dim

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [_hash_vec(text, self.dim) for text in input]

    @staticmethod
    def name() -> str:
        return "linkin_hash_embedding"


def _hash_vec(text: str, dim: int = 64) -> list[float]:
    digest = hashlib.sha256((text or "").encode("utf-8")).digest()
    raw: list[float] = []
    seed = digest
    while len(raw) < dim:
        seed = hashlib.sha256(seed).digest()
        raw.extend(b / 255.0 for b in seed)
    vec = raw[:dim]
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


def data_dir() -> Path:
    override = os.getenv("EVOL_LINKIN_DATA_DIR")
    path = Path(override) if override else DEFAULT_DATA_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def chroma_dir() -> Path:
    override = os.getenv("EVOL_LINKIN_CHROMA_DIR")
    if override:
        path = Path(override)
    else:
        path = data_dir() / "chroma"
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_path(collection: str) -> Path:
    return data_dir() / f"{collection}.json"


def entity_path(name: str) -> Path:
    return data_dir() / f"{name}.json"


def reset_store() -> None:
    global _store
    with _lock:
        _store = None


def get_store() -> "LinkinKnowledgeStore":
    global _store
    with _lock:
        if _store is None:
            _store = LinkinKnowledgeStore()
        return _store


def evaluate_for_write(query: str, answer: str) -> EvaluationResult:
    return MultiDimensionalEvaluator().evaluate(query, answer)


def evaluation_to_percent(result: EvaluationResult) -> dict[str, Any]:
    dims = {
        dim: round(getattr(result, dim).score * 10.0, 2) for dim in DIMENSION_NAMES
    }
    overall = round(result.overall * 10.0, 2)
    return {
        **{dim: {"score": dims[dim], "reason": getattr(result, dim).reason} for dim in DIMENSION_NAMES},
        "overall": overall,
        "source": result.source,
        "scale": "0-100",
    }


def passes_quality_gate(result: EvaluationResult, threshold: float = QUALITY_THRESHOLD) -> bool:
    percent = evaluation_to_percent(result)
    if percent["overall"] < threshold:
        return False
    return all(percent[dim]["score"] >= threshold for dim in DIMENSION_NAMES)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    return []


def _save_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _lexical_similarity(query: str, text: str) -> float:
    q = (query or "").strip()
    t = (text or "").strip()
    if not q or not t:
        return 0.0
    if q == t or q in t or t in q:
        return 1.0
    q_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", q.lower()))
    t_tokens = set(re.findall(r"[\w\u4e00-\u9fff]+", t.lower()))
    if q_tokens and t_tokens:
        overlap = len(q_tokens & t_tokens) / max(len(q_tokens), 1)
        if overlap:
            return overlap
    q_chars = set(q)
    t_chars = set(t)
    return len(q_chars & t_chars) / max(len(q_chars), 1)


def _distance_to_similarity(distance: float) -> float:
    # 雜湊向量使用 L2；正規化後 distance≈0 表示相同。保守映射到 0–1。
    return max(0.0, min(1.0, 1.0 - float(distance) / 2.0))


class LinkinKnowledgeStore:
    """Chroma 四庫 + JSON 降級。"""

    def __init__(self) -> None:
        self._client: Any = None
        self._collections: dict[str, Any] = {}
        self._chroma_ok = False
        self._chroma_error: str | None = None
        if os.getenv("EVOL_LINKIN_FORCE_JSON", "").strip().lower() in {"1", "true", "yes"}:
            self._chroma_error = "EVOL_LINKIN_FORCE_JSON"
            return
        try:
            self._init_chroma()
            self._chroma_ok = True
        except Exception as exc:  # noqa: BLE001
            self._chroma_error = str(exc)
            logger.warning("Linkin Chroma 初始化失敗，降級 JSON：%s", exc)

    def _init_chroma(self) -> None:
        from backend.memory.chroma_compat import apply_chromadb_sql_txt_compat
        import chromadb

        apply_chromadb_sql_txt_compat()
        persist = chroma_dir()
        self._client = chromadb.PersistentClient(path=str(persist))
        embed = HashEmbeddingFunction()
        for name in COLLECTIONS:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                embedding_function=embed,
            )

    def backend_status(self) -> dict[str, Any]:
        return {
            "chroma": self._chroma_ok,
            "fallback": "json" if not self._chroma_ok else None,
            "error": self._chroma_error,
            "collections": list(COLLECTIONS),
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "quality_threshold": QUALITY_THRESHOLD,
        }

    def upsert(
        self,
        collection: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        *,
        record_id: str | None = None,
        skip_quality: bool = False,
        query_hint: str | None = None,
    ) -> dict[str, Any]:
        if collection not in COLLECTIONS:
            raise ValueError(f"未知知識庫：{collection}")
        meta = dict(metadata or {})
        rec_id = record_id or str(meta.get("id") or uuid.uuid4())
        meta["id"] = rec_id
        meta.setdefault("created_at", _now())
        meta["updated_at"] = _now()

        evaluation_payload: dict[str, Any] | None = None
        if not skip_quality:
            result = evaluate_for_write(query_hint or "寫入靈境知識庫", text)
            evaluation_payload = evaluation_to_percent(result)
            if not passes_quality_gate(result):
                raise QualityGateError(
                    f"四維度評分未達 {QUALITY_THRESHOLD}（overall={evaluation_payload['overall']}）",
                    evaluation_payload,
                )
            meta["quality_overall"] = evaluation_payload["overall"]

        record = {"id": rec_id, "text": text, "metadata": meta}
        backend = "json"
        if self._chroma_ok:
            try:
                self._chroma_upsert(collection, rec_id, text, meta)
                backend = "chroma"
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chroma 寫入失敗，降級 JSON：%s", exc)
                self._chroma_ok = False
                self._chroma_error = str(exc)
        self._json_upsert(collection, record)
        return {
            "id": rec_id,
            "backend": backend,
            "collection": collection,
            "evaluation": evaluation_payload,
            "metadata": meta,
            "text": text,
        }

    def _chroma_upsert(self, collection: str, rec_id: str, text: str, meta: dict[str, Any]) -> None:
        col = self._collections[collection]
        clean = {
            k: v if isinstance(v, (str, int, float, bool)) else json.dumps(v, ensure_ascii=False)
            for k, v in meta.items()
            if v is not None
        }
        try:
            col.delete(ids=[rec_id])
        except Exception:  # noqa: BLE001
            pass
        col.add(ids=[rec_id], documents=[text], metadatas=[clean])

    def _json_upsert(self, collection: str, record: dict[str, Any]) -> None:
        path = json_path(collection)
        items = _load_json_list(path)
        items = [item for item in items if str(item.get("id")) != str(record["id"])]
        items.append(record)
        _save_json_list(path, items)

    def get(self, collection: str, rec_id: str) -> dict[str, Any] | None:
        for item in self.list(collection):
            if str(item.get("id")) == rec_id:
                return item
        return None

    def list(self, collection: str) -> list[dict[str, Any]]:
        return _load_json_list(json_path(collection))

    def delete(self, collection: str, rec_id: str) -> bool:
        path = json_path(collection)
        items = _load_json_list(path)
        kept = [item for item in items if str(item.get("id")) != rec_id]
        if len(kept) == len(items):
            return False
        _save_json_list(path, kept)
        if self._chroma_ok:
            try:
                self._collections[collection].delete(ids=[rec_id])
            except Exception:  # noqa: BLE001
                pass
        return True

    def search(
        self,
        collection: str,
        query: str,
        *,
        k: int = 5,
        threshold: float = SIMILARITY_THRESHOLD,
    ) -> list[dict[str, Any]]:
        if self._chroma_ok:
            try:
                return self._chroma_search(collection, query, k=k, threshold=threshold)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Chroma 檢索失敗，降級 JSON：%s", exc)
                self._chroma_ok = False
                self._chroma_error = str(exc)
        return self._json_search(collection, query, k=k, threshold=threshold)

    def _chroma_search(
        self, collection: str, query: str, *, k: int, threshold: float
    ) -> list[dict[str, Any]]:
        col = self._collections[collection]
        result = col.query(query_texts=[query], n_results=max(k, 1))
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        out: list[dict[str, Any]] = []
        for doc, meta, rec_id, dist in zip(docs, metas, ids, dists):
            similarity = _distance_to_similarity(float(dist or 0))
            if similarity < threshold:
                continue
            out.append(
                {
                    "id": rec_id,
                    "text": doc,
                    "metadata": meta or {},
                    "similarity": round(similarity, 4),
                    "backend": "chroma",
                }
            )
        return out[:k]

    def _json_search(
        self, collection: str, query: str, *, k: int, threshold: float
    ) -> list[dict[str, Any]]:
        scored: list[dict[str, Any]] = []
        for item in self.list(collection):
            similarity = _lexical_similarity(query, str(item.get("text") or ""))
            if similarity < threshold:
                continue
            scored.append(
                {
                    "id": item.get("id"),
                    "text": item.get("text"),
                    "metadata": item.get("metadata") or {},
                    "similarity": round(similarity, 4),
                    "backend": "json",
                }
            )
        scored.sort(key=lambda row: row["similarity"], reverse=True)
        return scored[:k]


def list_entities(name: str) -> list[dict[str, Any]]:
    return _load_json_list(entity_path(name))


def save_entities(name: str, items: list[dict[str, Any]]) -> None:
    _save_json_list(entity_path(name), items)


def upsert_entity(name: str, record: dict[str, Any]) -> dict[str, Any]:
    rec_id = str(record.get("id") or uuid.uuid4())
    record = {**record, "id": rec_id, "updated_at": _now()}
    record.setdefault("created_at", _now())
    items = [item for item in list_entities(name) if str(item.get("id")) != rec_id]
    items.append(record)
    save_entities(name, items)
    return record


def delete_entity(name: str, rec_id: str) -> bool:
    items = list_entities(name)
    kept = [item for item in items if str(item.get("id")) != rec_id]
    if len(kept) == len(items):
        return False
    save_entities(name, kept)
    return True
