"""靈境 REST：任務生成與任務清單端點。"""

from __future__ import annotations

import uuid
from typing import Any

from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_WORLDVIEW,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.tools import TOOL_QUEST_GENERATE, ToolValidationError, invoke_tool

from .router import linkin_router
from .shared import _delete_entity_or_404, _extract_json_object, _tool_http, _try_call_llm


@linkin_router.post("/quests/generate")
def generate_quest(body: dict[str, Any]) -> dict[str, Any]:
    try:
        invoked = invoke_tool(TOOL_QUEST_GENERATE, body)
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc
    params = invoked["params"]
    store = get_store()
    region = params.get("region") or "织庭都"
    lore = store.search(COL_WORLDVIEW, f"{region} {params.get('faction')} 阵营 任务", k=3)
    lore_text = "；".join((hit.get("text") or "")[:80] for hit in lore) or "三大阵营张力"
    title = f"{params['quest_type']}：{region}的灵丝回响"
    description = (
        f"在{region}调查与「{lore_text[:60]}」相关的异动。"
        f"难度：{params['difficulty']}。须遵守世界观宪法，不得改写已记载历史。"
    )
    try:
        from backend.linkin.prompts import inherit_prompt

        system = inherit_prompt("narrative_director")
    except Exception:
        system = "你是灵境·Linkin 的叙事总监。任务必须源自三大阵营张力。"
    llm_raw = _try_call_llm(
        (
            "根据世界观资料生成一个灵境任务。只输出 JSON："
            '{"title":"...","description":"..."}\n'
            f"区域：{region}\n类型：{params['quest_type']}\n难度：{params['difficulty']}\n"
            f"资料：{lore_text[:800]}"
        ),
        system=system,
        fallback="",
    )
    parsed = _extract_json_object(llm_raw) if llm_raw else None
    if parsed:
        title = str(parsed.get("title") or title).strip() or title
        description = str(parsed.get("description") or description).strip() or description
    from backend.linkin.quest_objectives import attach_objectives_if_missing

    quest = attach_objectives_if_missing(
        {
            "id": f"quest-{uuid.uuid4().hex[:10]}",
            "player_id": params["player_id"],
            "quest_type": params["quest_type"],
            "difficulty": params["difficulty"],
            "region": region,
            "title": title,
            "description": description,
            "rewards": {"灵丝碎片": 3 if params["difficulty"] == "简单" else 8},
        }
    )
    upsert_entity("quests", quest)
    store.upsert(
        COL_EVENTS,
        f"任务生成：{quest['title']}\n{quest['description']}",
        {"kind": "quest", "quest_id": quest["id"], "player_id": params["player_id"]},
        skip_quality=True,
    )
    return {"quest": quest, "rag": lore}

@linkin_router.get("/quests")
def list_quests() -> dict[str, Any]:
    items = list_entities("quests")
    return {"quests": items, "count": len(items)}

@linkin_router.delete("/quests/{quest_id}")
def remove_quest(quest_id: str) -> dict[str, Any]:
    return _delete_entity_or_404("quests", quest_id)
