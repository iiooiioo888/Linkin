"""靈境 REST：事件流端點。"""

from __future__ import annotations

from typing import Any

from backend.linkin.knowledge import COL_EVENTS, get_store

from .router import linkin_router


@linkin_router.get("/events")
def list_events() -> dict[str, Any]:
    items = []
    for rec in get_store().list(COL_EVENTS):
        meta = dict(rec.get("metadata") or {})
        items.append(
            {
                "id": rec.get("id") or meta.get("id"),
                "text": rec.get("text") or "",
                "kind": meta.get("kind") or "",
                "title": meta.get("title") or "",
                "updated_at": meta.get("updated_at"),
            }
        )
    return {"events": items, "count": len(items)}
