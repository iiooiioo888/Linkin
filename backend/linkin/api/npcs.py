"""靈境 REST：NPC 名冊、對話與關係端點。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException, Query

from backend.linkin.knowledge import COL_NPCS, COL_PLAYERS, QualityGateError, get_store
from backend.linkin.tools import (
    TOOL_NPC_CREATE,
    TOOL_NPC_DIALOGUE,
    ToolValidationError,
    format_npc_text,
    invoke_tool,
    npc_relationships,
)

from .router import linkin_router
from .shared import _tool_http, _try_call_llm


def _npc_from_record(record: dict[str, Any]) -> dict[str, Any]:
    meta = dict(record.get("metadata") or {})
    return {
        "id": record.get("id") or meta.get("id"),
        "name": meta.get("name") or "",
        "faction": meta.get("faction") or "",
        "occupation": meta.get("occupation") or "",
        "personality": meta.get("personality") or "",
        "backstory": meta.get("backstory") or record.get("text") or "",
        "location": meta.get("location") or "",
        "speech_style": meta.get("speech_style") or "",
        "relationships": npc_relationships(meta),
        "backend": record.get("backend"),
        "updated_at": meta.get("updated_at"),
    }

@linkin_router.get("/npcs")
def list_npcs() -> dict[str, Any]:
    items = [_npc_from_record(rec) for rec in get_store().list(COL_NPCS)]
    return {"npcs": items, "count": len(items)}


@linkin_router.post("/npcs")
def create_npc(body: dict[str, Any]) -> dict[str, Any]:
    try:
        invoked = invoke_tool(TOOL_NPC_CREATE, body)
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc
    card = invoked["params"]
    card["id"] = card.get("id") or f"npc-{uuid.uuid4().hex[:10]}"
    try:
        stored = get_store().upsert(
            COL_NPCS,
            format_npc_text(card),
            dict(card),
            record_id=card["id"],
            query_hint=f"创建NPC {card['name']}",
        )
    except QualityGateError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "evaluation": exc.evaluation},
        ) from exc
    return {"npc": {**card, "backend": stored["backend"]}, "evaluation": stored.get("evaluation")}


@linkin_router.put("/npcs")
def update_npc_collection(body: dict[str, Any]) -> dict[str, Any]:
    npc_id = str(body.get("id") or "").strip()
    if not npc_id:
        raise HTTPException(status_code=400, detail="PUT /linkin/npcs 需要 id")
    return update_npc(npc_id, body)


@linkin_router.delete("/npcs")
def delete_npc_collection(npc_id: str | None = Query(default=None)) -> dict[str, Any]:
    rec_id = str(npc_id or "").strip()
    if not rec_id:
        raise HTTPException(status_code=400, detail="DELETE /linkin/npcs 需要 id")
    return remove_npc(rec_id)


@linkin_router.put("/npcs/{npc_id}")
def update_npc(npc_id: str, body: dict[str, Any]) -> dict[str, Any]:
    existing = get_store().get(COL_NPCS, npc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="NPC 不存在")
    merged = {**_npc_from_record(existing), **body, "id": npc_id}
    try:
        invoked = invoke_tool(TOOL_NPC_CREATE, merged)
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc
    card = invoked["params"]
    card["id"] = npc_id
    try:
        stored = get_store().upsert(
            COL_NPCS,
            format_npc_text(card),
            dict(card),
            record_id=npc_id,
            query_hint=f"更新NPC {card['name']}",
        )
    except QualityGateError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "evaluation": exc.evaluation},
        ) from exc
    return {"npc": {**card, "backend": stored["backend"]}, "evaluation": stored.get("evaluation")}


@linkin_router.delete("/npcs/{npc_id}")
def remove_npc(npc_id: str) -> dict[str, Any]:
    if not get_store().delete(COL_NPCS, npc_id):
        raise HTTPException(status_code=404, detail="NPC 不存在")
    return {"deleted": True, "id": npc_id}


@linkin_router.post("/npcs/{npc_id}/dialogue")
def npc_dialogue(npc_id: str, body: dict[str, Any]) -> dict[str, Any]:
    payload = {"npcId": npc_id, "playerMessage": body.get("playerMessage") or body.get("message") or ""}
    try:
        invoked = invoke_tool(TOOL_NPC_DIALOGUE, payload)
    except ToolValidationError as exc:
        raise _tool_http(exc) from exc
    store = get_store()
    npc = store.get(COL_NPCS, npc_id)
    if npc is None:
        raise HTTPException(status_code=404, detail="NPC 不存在")
    card = _npc_from_record(npc)
    retrieved = store.search(COL_NPCS, f"{card['name']} {card['backstory'][:80]}", k=3)
    message = invoked["params"]["player_message"]
    context = "\n".join(item.get("text") or "" for item in retrieved) or (npc.get("text") or "")
    reply = _npc_reply(card, message, context)
    store.upsert(
        COL_PLAYERS,
        f"玩家对 {card['name']} 说：{message}\n回应：{reply}",
        {"kind": "dialogue", "npc_id": npc_id, "player_id": body.get("player_id") or "anonymous"},
        skip_quality=True,
    )
    return {
        "npc_id": npc_id,
        "reply": reply,
        "rag": {
            "hits": retrieved,
            "threshold": 0.75,
            "backend": store.backend_status(),
        },
    }

def _npc_reply(card: dict[str, Any], message: str, context: str) -> str:
    style = card.get("speech_style") or "沉稳"
    name = card.get("name") or "无名旅人"
    snippet = (card.get("backstory") or "")[:40]
    fallback = f"{name}（{style}）：「我记下了你的话。{snippet}……灵境不会遗忘约定。」"
    try:
        from backend.linkin.prompts import inherit_prompt

        system = inherit_prompt("npc_director")
    except Exception:
        system = "你是灵境·Linkin 的 NPC。回应必须符合角色卡，禁止现实政治与写实暴力。"
    prompt = (
        f"你正在扮演灵境 NPC「{name}」。性格：{card.get('personality')}。"
        f"背景：{card.get('backstory')}。语言风格：{style}。\n"
        f"检索到的角色资料：\n{context[:1200]}\n"
        f"玩家说：{message}\n"
        "只输出一句符合角色卡的对白，不要解释规则。"
    )
    return _try_call_llm(prompt, system=system, fallback=fallback)
