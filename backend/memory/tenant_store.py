"""依登入帳號分開的向量記憶庫。

未綁定租戶時沿用 ``EVOL_CHROMA_COLLECTION``（預設 ``evo_memory``），
既有單機與測試行為不變。已登入則各自一個 collection。
"""

from __future__ import annotations

import os
import re
import threading

from backend.memory.vector_store import VectorMemoryStore

_lock = threading.Lock()
_stores: dict[str, VectorMemoryStore] = {}


def collection_name_for(user_id: str | None) -> str:
    base = os.getenv("EVOL_CHROMA_COLLECTION", "evo_memory").strip() or "evo_memory"
    if not user_id:
        return _chroma_name(base)
    safe = re.sub(r"[^A-Za-z0-9]", "", user_id)[:24] or "user"
    return _chroma_name(f"u{safe}mem")


def _chroma_name(raw: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]", "", raw)
    if len(text) < 3:
        text = "evomemory"
    if not text[0].isalnum():
        text = f"c{text}"
    if not text[-1].isalnum():
        text = f"{text}x"
    return text[:63]


def vector_store_for_request() -> VectorMemoryStore:
    from backend.core.user_settings import active_settings_user

    name = collection_name_for(active_settings_user())
    with _lock:
        store = _stores.get(name)
        if store is None:
            store = VectorMemoryStore(collection_name=name)
            _stores[name] = store
        return store


def reset_tenant_memory_stores() -> None:
    with _lock:
        _stores.clear()
