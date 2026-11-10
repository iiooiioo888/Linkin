"""靈境 REST 路由：憲法、NPC、任務、道具、事件、總覽、運維與 grill-me。"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.linkin.constitution import (
    load_constitution,
    save_constitution,
    update_constitution,
)
from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_NPCS,
    COL_PLAYERS,
    COL_WORLDVIEW,
    QualityGateError,
    delete_entity,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.tools import (
    TOOL_ITEM_CREATE,
    TOOL_NPC_CREATE,
    TOOL_NPC_DIALOGUE,
    TOOL_QUEST_GENERATE,
    ToolValidationError,
    format_npc_text,
    invoke_tool,
    npc_relationships,
)
from backend.tools.server_admin import ServerAdminError

logger = logging.getLogger(__name__)

linkin_router = APIRouter(prefix="/linkin", tags=["linkin"])


def register_linkin(app) -> None:
    app.include_router(linkin_router)


def _llm_ready() -> bool:
    if os.getenv("EVOL_LINKIN_NO_LLM", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")


def _try_call_llm(prompt: str, *, system: str, fallback: str) -> str:
    if not _llm_ready():
        return fallback
    try:
        from backend.core.llm import call_llm

        text = call_llm(prompt, system=system)
        return (text or "").strip() or fallback
    except Exception:
        logger.warning("靈境 LLM 呼叫失敗，改用本地模板", exc_info=True)
        return fallback


def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


def _delete_entity_or_404(collection: str, rec_id: str) -> dict[str, Any]:
    if not delete_entity(collection, rec_id):
        raise HTTPException(status_code=404, detail=f"{collection} 不存在")
    return {"deleted": True, "id": rec_id}



def _tool_http(exc: ToolValidationError) -> HTTPException:
    status = 409 if exc.code == "needs_confirmation" else 400
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code, **exc.extra},
    )


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

# ── 服務器運維智能體（本地定制，恢復自 server_admin 模組）──
_SERVER_ERROR_STATUS = {
    "unknown_tool": 400,
    "invalid": 400,
    "invalid_service": 400,
    "path_denied": 403,
    "service_denied": 403,
    "dangerous_input": 403,
    "expired": 409,
    "invalid_state": 409,
    "needs_confirmation": 409,
}


def _server_http(exc: ServerAdminError) -> HTTPException:
    status = _SERVER_ERROR_STATUS.get(str(exc.code), 500)
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code, **exc.extra},
    )


@linkin_router.get("/server/health")
def server_health() -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    return server_ops.health_snapshot()


@linkin_router.post("/server/ask")
def server_ask(body: dict[str, Any]) -> dict[str, Any]:
    """自然語言運維問答：讀操作即執行；寫操作轉 pending_approval。"""
    from backend.linkin import server_admin as server_ops

    question = str(body.get("question") or body.get("command") or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="需要 question")
    auto_approve = bool(body.get("auto_approve"))
    role = str(body.get("role") or "").strip()
    try:
        return server_ops.ask_agent(question, auto_approve=auto_approve, role=role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.get("/server/approvals")
def server_approvals(include_done: bool = Query(False)) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    items = server_ops.list_approvals(include_done=include_done)
    return {"approvals": items, "count": len(items)}


@linkin_router.post("/server/approvals/{approval_id}/confirm")
def server_approval_confirm(approval_id: str) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    try:
        return server_ops.confirm_approval(approval_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.post("/server/approvals/{approval_id}/cancel")
def server_approval_cancel(approval_id: str) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    try:
        return server_ops.cancel_approval(approval_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ServerAdminError as exc:
        raise _server_http(exc) from exc


@linkin_router.post("/server/patrol")
def server_patrol(body: dict[str, Any] | None = None) -> dict[str, Any]:
    """主動巡檢：健康快照 + 規則提案（預設轉人工批准；不自動執行破壞性操作）。"""
    from backend.linkin import server_admin as server_ops

    auto_approve = bool((body or {}).get("auto_approve"))
    return server_ops.patrol(auto_approve=auto_approve)


@linkin_router.get("/server/report")
def server_report() -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    return {"report": server_ops.daily_report()}


@linkin_router.get("/server/audit")
def server_audit(limit: int = Query(100, ge=1, le=1000)) -> dict[str, Any]:
    from backend.linkin import server_admin as server_ops

    rows = server_ops.audit_tail(limit)
    return {"entries": rows, "count": len(rows)}


# ── grill-me 嚴刑拷打模式（本地定制，上游無此區塊）──


@linkin_router.post("/grill/start")
def grill_start(body: dict[str, Any]) -> dict[str, Any]:
    """開一場拷問會話：body={"topic": "<計畫/決策/想法>"}。"""
    from backend.linkin import grill_me

    topic = str((body or {}).get("topic") or (body or {}).get("question") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_start(topic)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 啟動失敗：%s", exc)
        raise HTTPException(
            status_code=503, detail={"message": f"grill-me 不可用（LLM 未配置或呼叫失敗）：{exc}"}
        ) from exc


@linkin_router.post("/grill/turn")
def grill_turn(body: dict[str, Any]) -> dict[str, Any]:
    """繼續拷問：body={"session_id": "...", "answer": "<使用者回答>"}。"""
    from backend.linkin import grill_me

    session_id = str((body or {}).get("session_id") or "").strip()
    answer = str((body or {}).get("answer") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_turn(session_id, answer)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 回合失敗：%s", exc)
        raise HTTPException(status_code=503, detail={"message": f"grill-me 不可用：{exc}"}) from exc


@linkin_router.post("/grill/summary")
def grill_summary(body: dict[str, Any]) -> dict[str, Any]:
    """強制收尾：body={"session_id": "..."} → 🟢🟡🔴 總結 + GO/NO-GO 裁決。"""
    from backend.linkin import grill_me

    session_id = str((body or {}).get("session_id") or "").strip()
    try:
        return {"status": "ok", **grill_me.grill_summary(session_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"message": str(exc)}) from exc
    except Exception as exc:
        logger.warning("grill_me 總結失敗：%s", exc)
        raise HTTPException(status_code=503, detail={"message": f"grill-me 不可用：{exc}"}) from exc


@linkin_router.get("/grill/status")
def grill_status() -> dict[str, Any]:
    from backend.linkin import grill_me

    return grill_me.grill_status()
