"""記憶庫管理 API：列出／刪除記憶與過期清理。

自 backend.main 抽出；保留原本模組層 lazy 建立的 `_memory_store_api`（VectorMemoryStore）。
"""

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from backend.memory.json_store import JsonMemoryStore
from backend.memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["memories"])

_memory_store_api = VectorMemoryStore()


def _json_memories() -> list[dict]:
    rows: list[dict] = []
    for item in JsonMemoryStore().all():
        meta = item.get("metadata") or {}
        rec_id = str(item.get("id") or meta.get("_id") or "")
        if not rec_id:
            rec_id = str(abs(hash(item.get("text") or "")))
        rows.append(
            {
                "id": rec_id,
                "text": item.get("text") or "",
                "metadata": meta,
            }
        )
    return rows


# ==================== 記憶庫管理 API ====================

@router.get("/memories")
async def list_memories(limit: int = 100, offset: int = 0):
    """列出記憶庫中的記憶（分頁，按建立時間降序）。"""
    chroma_error = ""
    try:
        all_memories = await asyncio.to_thread(_memory_store_api.all)
    except Exception as exc:
        logger.warning("記憶庫讀取失敗：%s", exc)
        chroma_error = str(exc)
        all_memories = []
    if not all_memories:
        all_memories = await asyncio.to_thread(_json_memories)
    total = len(all_memories)
    all_memories.sort(
        key=lambda m: (m.get("metadata") or {}).get("created_at", ""),
        reverse=True,
    )
    page = all_memories[offset : offset + limit]
    payload: dict = {"total": total, "offset": offset, "limit": limit, "memories": page}
    if chroma_error and not page:
        payload["error"] = chroma_error
    return payload


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    """刪除單條記憶。"""
    try:
        collection = await asyncio.to_thread(_memory_store_api._get_collection)
        collection.delete(ids=[memory_id])
        _memory_store_api.invalidate_cache()
        return {"deleted": True, "id": memory_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"刪除失敗：{exc}") from exc


@router.post("/memories/cleanup")
async def cleanup_memories(max_age_days: int = 30, min_score: float | None = None):
    """清理過期或低品質記憶。"""
    try:
        deleted = await asyncio.to_thread(
            _memory_store_api.cleanup, max_age_days, min_score
        )
        return {"deleted_count": deleted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"清理失敗：{exc}") from exc
