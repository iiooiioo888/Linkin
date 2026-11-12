"""靈境 REST：世界總覽端點。"""

from __future__ import annotations

from typing import Any

from backend.linkin.constitution import load_constitution
from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_NPCS,
    COL_PLAYERS,
    get_store,
    list_entities,
)

from .router import linkin_router


@linkin_router.get("/overview")
def overview() -> dict[str, Any]:
    store = get_store()
    const = load_constitution()
    factions = const.get("factions") or []
    magic = const.get("magic") or {}
    return {
        "world_name": const.get("world_name"),
        "will": (const.get("foundation") or {}).get("will"),
        "npc_count": len(store.list(COL_NPCS)),
        "quest_count": len(list_entities("quests")),
        "event_count": len(store.list(COL_EVENTS)),
        "item_count": len(list_entities("items")),
        "player_records": len(store.list(COL_PLAYERS)),
        "factions": [f.get("name") for f in factions],
        "magic": magic.get("name"),
        "compliance": {
            "constitution_loaded": bool(const.get("world_name")),
            "factions_defined": len(factions) == 3,
            "magic_defined": bool(magic.get("name")) and "[待Phase" not in str(magic.get("name")),
            "rag": store.backend_status(),
        },
    }
