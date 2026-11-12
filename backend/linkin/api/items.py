"""靈境 REST：道具清單、建立與刪除端點。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

from backend.linkin.knowledge import (
    COL_WORLDVIEW,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.tools import TOOL_ITEM_CREATE, ToolValidationError, invoke_tool

from .router import linkin_router
from .shared import _delete_entity_or_404, _tool_http


@linkin_router.get("/items")
def list_items() -> dict[str, Any]:
    items = list_entities("items")
    return {"items": items, "count": len(items)}

@linkin_router.delete("/items/{item_id}")
def remove_item(item_id: str) -> dict[str, Any]:
    return _delete_entity_or_404("items", item_id)

@linkin_router.post("/items")
def create_item(body: dict[str, Any]) -> dict[str, Any]:
    duplicates = get_store().search(COL_WORLDVIEW, str(body.get("name") or ""), k=3)
    try:
        invoked = invoke_tool(TOOL_ITEM_CREATE, body)
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc
    params = invoked["params"]
    for hit in duplicates:
        meta = hit.get("metadata") or {}
        if meta.get("kind") == "item" and str(meta.get("name") or "") == params["name"]:
            raise HTTPException(status_code=409, detail="道具名稱重複")
    item = {"id": f"item-{uuid.uuid4().hex[:10]}", **params}
    upsert_entity("items", item)
    get_store().upsert(
        COL_WORLDVIEW,
        f"道具：{params['name']}（{params['type']} / {params['rarity']}）属性：{params['attributes']}",
        {"kind": "item", "item_id": item["id"], "name": params["name"]},
        skip_quality=True,
    )
    return {"item": item, "rag_checked": True}
