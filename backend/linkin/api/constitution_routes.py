"""靈境 REST：世界觀憲法端點。"""

from __future__ import annotations

from typing import Any

from backend.linkin.constitution import (
    load_constitution,
    save_constitution,
    update_constitution,
)

from .router import linkin_router


@linkin_router.get("/constitution")
def get_constitution() -> dict[str, Any]:
    return load_constitution()


@linkin_router.put("/constitution")
def put_constitution(body: dict[str, Any]) -> dict[str, Any]:
    if body.get("replace") is True or body.get("world_name"):
        payload = {k: v for k, v in body.items() if k != "replace"}
        if body.get("replace"):
            return save_constitution(payload)
        if set(payload.keys()) <= {"world_name", "foundation", "magic", "factions", "regions", "content_boundaries", "consistency_rules", "item_balance", "builder", "version", "tagline", "world_name_zh_hant"}:
            return update_constitution(payload)
        return save_constitution(payload)
    return update_constitution(body)
