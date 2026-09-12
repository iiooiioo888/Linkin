"""Phase 3：敘事 commit 的 NPC／任務／道具 → Linkin 世界層 + MineMCP 落地。

消費 narrative commit 寫入且 ``world_status: pending_world`` 的實體，
經既有 store／橋接護欄註冊並嘗試遊戲內標記（summon／tellraw／place_block）。
預覽不連線 MineMCP；落地需使用者明確 ``confirm: true``。
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.linkin.knowledge import (
    COL_EVENTS,
    COL_NPCS,
    COL_WORLDVIEW,
    get_store,
    list_entities,
    upsert_entity,
)
from backend.linkin.minecraft import execute_named_tool, monitor_status
from backend.linkin.tools import ToolValidationError
from backend.tools import minecraft_mcp as mcp

WORLD_STATUS_PENDING = "pending_world"
WORLD_STATUS_APPLIED = "applied"
WORLD_STATUS_PARTIAL = "partial"

INTENT_KINDS = frozenset({"npc", "quest", "item"})

DEFAULT_SPAWN = (0, 64, 0)

_NPC_MARKER_MATERIAL = "EMERALD_BLOCK"
_QUEST_MARKER_MATERIAL = "GOLD_BLOCK"
_ITEM_MARKER_MATERIAL = "DIAMOND_BLOCK"


class WorldIntentError(ValueError):
    """世界意圖校驗或落地失敗。"""

    def __init__(self, message: str, *, code: str = "invalid", extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


def _npc_from_record(record: dict[str, Any]) -> dict[str, Any]:
    meta = dict(record.get("metadata") or record.get("meta") or {})
    if record.get("id"):
        meta.setdefault("id", record["id"])
    for key in ("name", "faction", "occupation", "personality", "backstory", "location", "speech_style", "relationships"):
        if key in record and key not in meta:
            meta[key] = record[key]
    return meta


def _is_narrative_pending(entity: dict[str, Any]) -> bool:
    if str(entity.get("source") or "") != "narrative_workspace":
        return False
    status = str(entity.get("world_status") or WORLD_STATUS_PENDING)
    return status == WORLD_STATUS_PENDING


def _resolve_spawn_coords(entity: dict[str, Any]) -> tuple[int, int, int]:
    for key in ("coords", "location", "spawn"):
        raw = entity.get(key)
        if raw is None:
            continue
        xyz = mcp.parse_xyz(raw)
        if xyz is not None:
            return xyz
    return DEFAULT_SPAWN


def _safe_label(text: str, *, limit: int = 48) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff·\- ]+", "", str(text or "")).strip()
    return (cleaned[:limit] or "Linkin").replace('"', "'")


def list_pending_intents() -> dict[str, Any]:
    """列出尚未落地至世界層的敘事意圖。"""
    npcs = [
        {**_npc_from_record(rec), "kind": "npc"}
        for rec in get_store().list(COL_NPCS)
        if _is_narrative_pending(_npc_from_record(rec))
    ]
    quests = [{**q, "kind": "quest"} for q in list_entities("quests") if _is_narrative_pending(q)]
    items = [{**i, "kind": "item"} for i in list_entities("items") if _is_narrative_pending(i)]
    return {
        "npcs": npcs,
        "quests": quests,
        "items": items,
        "count": len(npcs) + len(quests) + len(items),
    }


def _get_npc(npc_id: str) -> dict[str, Any]:
    record = get_store().get(COL_NPCS, npc_id)
    if record is None:
        raise WorldIntentError(f"NPC 不存在：{npc_id}", code="not_found")
    return _npc_from_record(record)


def _get_quest(quest_id: str) -> dict[str, Any]:
    for quest in list_entities("quests"):
        if str(quest.get("id")) == quest_id:
            return quest
    raise WorldIntentError(f"任務不存在：{quest_id}", code="not_found")


def _get_item(item_id: str) -> dict[str, Any]:
    for item in list_entities("items"):
        if str(item.get("id")) == item_id:
            return item
    raise WorldIntentError(f"道具不存在：{item_id}", code="not_found")


def _resolve_intents(
    *,
    npc_ids: list[str] | None = None,
    quest_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
    apply_all: bool = False,
) -> list[tuple[str, dict[str, Any]]]:
    pending = list_pending_intents()
    selected: list[tuple[str, dict[str, Any]]] = []

    if apply_all:
        for row in pending["npcs"]:
            selected.append(("npc", row))
        for row in pending["quests"]:
            selected.append(("quest", row))
        for row in pending["items"]:
            selected.append(("item", row))
        return selected

    for npc_id in npc_ids or []:
        selected.append(("npc", _get_npc(npc_id)))
    for quest_id in quest_ids or []:
        selected.append(("quest", _get_quest(quest_id)))
    for item_id in item_ids or []:
        selected.append(("item", _get_item(item_id)))

    if not selected:
        raise WorldIntentError("需要 npc_ids／quest_ids／item_ids 或 apply_all=true", code="missing_intents")
    return selected


def _bridge_status_for_apply(dry_run: bool) -> dict[str, Any]:
    status = monitor_status()
    if dry_run:
        return {**status, "spawn_mode": "dry_run", "note": "請求 dry_run：不呼叫 MineMCP"}
    if status.get("dry_run"):
        return {**status, "spawn_mode": "dry_run", "note": "MineMCP 乾跑模式"}
    if not status.get("enabled"):
        return {**status, "spawn_mode": "store_only", "note": "MineMCP 未啟用，僅更新 Linkin 世界資料"}
    if not status.get("connected"):
        return {
            **status,
            "spawn_mode": "store_only",
            "bridge_offline": True,
            "note": "MineMCP 橋接未連線，僅更新 Linkin 世界資料；遊戲內生成待橋接恢復後重試",
        }
    return {**status, "spawn_mode": "live"}


def _preview_npc(npc: dict[str, Any]) -> dict[str, Any]:
    x, y, z = _resolve_spawn_coords(npc)
    name = _safe_label(npc.get("name") or "NPC")
    return {
        "kind": "npc",
        "id": npc.get("id"),
        "title": name,
        "spawn": {"x": x, "y": y, "z": z},
        "actions": [
            {
                "tool": mcp.PLACE_BLOCK,
                "description": f"在 ({x},{y},{z}) 放置 NPC 標記方塊",
                "material": _NPC_MARKER_MATERIAL,
            },
            {
                "tool": mcp.EXECUTE_COMMAND,
                "description": f"嘗試 summon villager 並命名為「{name}」",
                "command": f"summon villager {x} {y} {z}",
            },
        ],
        "store": "linkin_npcs",
        "world_status": npc.get("world_status") or WORLD_STATUS_PENDING,
    }


def _preview_quest(quest: dict[str, Any]) -> dict[str, Any]:
    title = _safe_label(quest.get("title") or "任務")
    region = str(quest.get("region") or "织庭都")
    x, y, z = _resolve_spawn_coords(quest)
    return {
        "kind": "quest",
        "id": quest.get("id"),
        "title": title,
        "region": region,
        "spawn": {"x": x, "y": y, "z": z},
        "actions": [
            {
                "tool": mcp.PLACE_BLOCK,
                "description": f"在 ({x},{y},{z}) 放置任務標記方塊",
                "material": _QUEST_MARKER_MATERIAL,
            },
            {
                "tool": mcp.EXECUTE_COMMAND,
                "description": f"向全服公告新任務「{title}」",
                "command": f"tellraw @a {json.dumps({'text': f'[Linkin] 新任務：{title}'}, ensure_ascii=False)}",
            },
        ],
        "store": "quests",
        "world_status": quest.get("world_status") or WORLD_STATUS_PENDING,
    }


def _preview_item(item: dict[str, Any]) -> dict[str, Any]:
    name = _safe_label(item.get("name") or "道具")
    x, y, z = _resolve_spawn_coords(item)
    return {
        "kind": "item",
        "id": item.get("id"),
        "title": name,
        "spawn": {"x": x, "y": y, "z": z},
        "actions": [
            {
                "tool": mcp.PLACE_BLOCK,
                "description": f"在 ({x},{y},{z}) 放置道具標記方塊",
                "material": _ITEM_MARKER_MATERIAL,
            },
            {
                "tool": mcp.EXECUTE_COMMAND,
                "description": f"向全服公告新道具「{name}」",
                "command": f"tellraw @a {json.dumps({'text': f'[Linkin] 新道具：{name}'}, ensure_ascii=False)}",
            },
        ],
        "store": "items",
        "world_status": item.get("world_status") or WORLD_STATUS_PENDING,
    }


def preview_world_intents(
    *,
    npc_ids: list[str] | None = None,
    quest_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
    apply_all: bool = False,
) -> dict[str, Any]:
    intents = _resolve_intents(
        npc_ids=npc_ids,
        quest_ids=quest_ids,
        item_ids=item_ids,
        apply_all=apply_all,
    )
    previews = []
    for kind, entity in intents:
        if kind == "npc":
            previews.append(_preview_npc(entity))
        elif kind == "quest":
            previews.append(_preview_quest(entity))
        else:
            previews.append(_preview_item(entity))
    bridge = monitor_status()
    return {
        "intents": previews,
        "count": len(previews),
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
        },
        "dry_run": True,
    }


def _persist_npc(npc: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    from backend.linkin.tools import format_npc_text

    merged = {**npc, **patch}
    npc_id = str(merged.get("id") or "")
    stored = get_store().upsert(
        COL_NPCS,
        format_npc_text(merged),
        dict(merged),
        record_id=npc_id,
        query_hint=f"世界落地 NPC {merged.get('name')}",
        skip_quality=True,
    )
    return {**merged, "backend": stored["backend"]}


def _persist_quest(quest: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return upsert_entity("quests", {**quest, **patch})


def _persist_item(item: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    return upsert_entity("items", {**item, **patch})


def _try_place_marker(
    x: int,
    y: int,
    z: int,
    material: str,
    *,
    dry_run: bool,
    bridge: dict[str, Any],
) -> dict[str, Any]:
    if dry_run or bridge.get("spawn_mode") != "live":
        return {
            "ok": True,
            "dry_run": True,
            "skipped": True,
            "note": bridge.get("note") or "預覽模式或未連線，未呼叫 MineMCP",
        }
    try:
        result = execute_named_tool(
            mcp.PLACE_BLOCK,
            {"x": x, "y": y, "z": z, "material": material},
        )
        return {
            "ok": bool(result.get("ok")),
            "dry_run": bool(result.get("dry_run")),
            "tool": mcp.PLACE_BLOCK,
            "material": material,
            "coords": {"x": x, "y": y, "z": z},
            "error": result.get("error"),
        }
    except ToolValidationError as exc:
        return {"ok": False, "tool": mcp.PLACE_BLOCK, "error": str(exc), "code": exc.code}


def _try_execute_command(command: str, *, dry_run: bool, bridge: dict[str, Any]) -> dict[str, Any]:
    if dry_run or bridge.get("spawn_mode") != "live":
        return {
            "ok": True,
            "dry_run": True,
            "skipped": True,
            "command": command,
            "note": bridge.get("note") or "預覽模式或未連線，未呼叫 MineMCP",
        }
    try:
        result = execute_named_tool(mcp.EXECUTE_COMMAND, {"command": command})
        return {
            "ok": bool(result.get("ok")),
            "dry_run": bool(result.get("dry_run")),
            "tool": mcp.EXECUTE_COMMAND,
            "command": command,
            "error": result.get("error"),
        }
    except ToolValidationError as exc:
        return {"ok": False, "tool": mcp.EXECUTE_COMMAND, "command": command, "error": str(exc), "code": exc.code}


def _apply_npc(npc: dict[str, Any], *, dry_run: bool, bridge: dict[str, Any]) -> dict[str, Any]:
    npc_id = str(npc.get("id") or "")
    if str(npc.get("world_status") or "") == WORLD_STATUS_APPLIED:
        return {
            "kind": "npc",
            "id": npc_id,
            "title": npc.get("name"),
            "world_status": WORLD_STATUS_APPLIED,
            "skipped": True,
            "store": {"ok": True, "note": "已落地，略過重複套用"},
            "minecraft": {"ok": True, "skipped": True},
        }

    x, y, z = _resolve_spawn_coords(npc)
    name = _safe_label(npc.get("name") or "NPC")
    marker = _try_place_marker(x, y, z, _NPC_MARKER_MATERIAL, dry_run=dry_run, bridge=bridge)
    summon = _try_execute_command(
        f'summon villager {x} {y} {z} {{CustomName:\'{{"text":"{name}"}}\',PersistenceRequired:1b}}',
        dry_run=dry_run,
        bridge=bridge,
    )

    store_ok = True
    minecraft_ok = marker.get("ok") and (summon.get("ok") or summon.get("skipped"))
    if bridge.get("spawn_mode") == "live" and not summon.get("ok"):
        minecraft_ok = marker.get("ok", False)

    if bridge.get("spawn_mode") != "live":
        world_status = WORLD_STATUS_PARTIAL if not dry_run else WORLD_STATUS_PENDING
        next_steps = [
            "Linkin NPC 資料已就緒",
            "啟用並連線 MineMCP 後可重試落地以在遊戲內生成實體",
        ]
    elif minecraft_ok:
        world_status = WORLD_STATUS_APPLIED
        next_steps = []
    else:
        world_status = WORLD_STATUS_PARTIAL
        next_steps = ["檢查 summon 指令是否被伺服器拒絕", "可手動在遊戲內放置 NPC 或調整座標後重試"]

    patch = {
        "world_status": world_status if not dry_run else npc.get("world_status", WORLD_STATUS_PENDING),
        "world_apply": {
            "applied_at": time.time(),
            "spawn": {"x": x, "y": y, "z": z},
            "marker": marker,
            "summon": summon,
            "dry_run": dry_run,
        },
    }
    saved = _persist_npc(npc, patch) if not dry_run else {**npc, **patch}

    return {
        "kind": "npc",
        "id": npc_id,
        "title": name,
        "world_status": patch["world_status"],
        "skipped": False,
        "store": {"ok": store_ok, "entity": saved},
        "minecraft": {"ok": minecraft_ok, "marker": marker, "summon": summon},
        "next_steps": next_steps,
    }


def _apply_quest(quest: dict[str, Any], *, dry_run: bool, bridge: dict[str, Any]) -> dict[str, Any]:
    quest_id = str(quest.get("id") or "")
    if str(quest.get("world_status") or "") == WORLD_STATUS_APPLIED:
        return {
            "kind": "quest",
            "id": quest_id,
            "title": quest.get("title"),
            "world_status": WORLD_STATUS_APPLIED,
            "skipped": True,
            "store": {"ok": True, "note": "已落地，略過重複套用"},
            "minecraft": {"ok": True, "skipped": True},
        }

    title = _safe_label(quest.get("title") or "任務")
    x, y, z = _resolve_spawn_coords(quest)
    marker = _try_place_marker(x, y, z, _QUEST_MARKER_MATERIAL, dry_run=dry_run, bridge=bridge)
    announce = _try_execute_command(
        f"tellraw @a {json.dumps({'text': f'[Linkin] 新任務：{title}'}, ensure_ascii=False)}",
        dry_run=dry_run,
        bridge=bridge,
    )

    if bridge.get("spawn_mode") != "live":
        world_status = WORLD_STATUS_PARTIAL if not dry_run else WORLD_STATUS_PENDING
        next_steps = ["任務已寫入 quests store", "連線 MineMCP 後可重試以在遊戲內公告"]
    elif marker.get("ok") and announce.get("ok"):
        world_status = WORLD_STATUS_APPLIED
        next_steps = []
    else:
        world_status = WORLD_STATUS_PARTIAL
        next_steps = ["任務資料已就緒；遊戲內公告可能失敗，請檢查橋接日誌"]

    patch = {
        "world_status": world_status if not dry_run else quest.get("world_status", WORLD_STATUS_PENDING),
        "world_apply": {
            "applied_at": time.time(),
            "spawn": {"x": x, "y": y, "z": z},
            "marker": marker,
            "announce": announce,
            "dry_run": dry_run,
        },
    }
    saved = _persist_quest(quest, patch) if not dry_run else {**quest, **patch}
    get_store().upsert(
        COL_EVENTS,
        f"任務落地：{title}",
        {"kind": "quest_apply", "quest_id": quest_id, "world_status": patch["world_status"]},
        skip_quality=True,
    )

    minecraft_ok = marker.get("ok") and (announce.get("ok") or announce.get("skipped"))
    return {
        "kind": "quest",
        "id": quest_id,
        "title": title,
        "world_status": patch["world_status"],
        "skipped": False,
        "store": {"ok": True, "entity": saved},
        "minecraft": {"ok": minecraft_ok, "marker": marker, "announce": announce},
        "next_steps": next_steps,
    }


def _apply_item(item: dict[str, Any], *, dry_run: bool, bridge: dict[str, Any]) -> dict[str, Any]:
    item_id = str(item.get("id") or "")
    if str(item.get("world_status") or "") == WORLD_STATUS_APPLIED:
        return {
            "kind": "item",
            "id": item_id,
            "title": item.get("name"),
            "world_status": WORLD_STATUS_APPLIED,
            "skipped": True,
            "store": {"ok": True, "note": "已落地，略過重複套用"},
            "minecraft": {"ok": True, "skipped": True},
        }

    name = _safe_label(item.get("name") or "道具")
    x, y, z = _resolve_spawn_coords(item)
    marker = _try_place_marker(x, y, z, _ITEM_MARKER_MATERIAL, dry_run=dry_run, bridge=bridge)
    announce = _try_execute_command(
        f"tellraw @a {json.dumps({'text': f'[Linkin] 新道具：{name}'}, ensure_ascii=False)}",
        dry_run=dry_run,
        bridge=bridge,
    )

    if bridge.get("spawn_mode") != "live":
        world_status = WORLD_STATUS_PARTIAL if not dry_run else WORLD_STATUS_PENDING
        next_steps = ["道具已寫入 items store", "連線 MineMCP 後可重試以在遊戲內標記"]
    elif marker.get("ok") and announce.get("ok"):
        world_status = WORLD_STATUS_APPLIED
        next_steps = []
    else:
        world_status = WORLD_STATUS_PARTIAL
        next_steps = ["道具資料已就緒；遊戲內標記可能失敗"]

    patch = {
        "world_status": world_status if not dry_run else item.get("world_status", WORLD_STATUS_PENDING),
        "world_apply": {
            "applied_at": time.time(),
            "spawn": {"x": x, "y": y, "z": z},
            "marker": marker,
            "announce": announce,
            "dry_run": dry_run,
        },
    }
    saved = _persist_item(item, patch) if not dry_run else {**item, **patch}
    get_store().upsert(
        COL_WORLDVIEW,
        f"道具落地：{name}（{item.get('type')}）",
        {"kind": "item_apply", "item_id": item_id, "world_status": patch["world_status"]},
        skip_quality=True,
    )

    minecraft_ok = marker.get("ok") and (announce.get("ok") or announce.get("skipped"))
    return {
        "kind": "item",
        "id": item_id,
        "title": name,
        "world_status": patch["world_status"],
        "skipped": False,
        "store": {"ok": True, "entity": saved},
        "minecraft": {"ok": minecraft_ok, "marker": marker, "announce": announce},
        "next_steps": next_steps,
    }


def _summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    applied = partial = skipped = failed = 0
    for row in results:
        if row.get("skipped"):
            skipped += 1
            continue
        status = str(row.get("world_status") or "")
        if status == WORLD_STATUS_APPLIED:
            applied += 1
        elif status == WORLD_STATUS_PARTIAL:
            partial += 1
        else:
            failed += 1
    overall = "applied"
    if partial:
        overall = "partial"
    elif failed and not applied:
        overall = "failed"
    elif skipped and not applied and not partial:
        overall = "skipped"
    return {
        "overall_status": overall,
        "applied": applied,
        "partial": partial,
        "skipped": skipped,
        "failed": failed,
        "total": len(results),
    }


def apply_world_intents(
    *,
    npc_ids: list[str] | None = None,
    quest_ids: list[str] | None = None,
    item_ids: list[str] | None = None,
    apply_all: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """落地世界意圖：更新 store 狀態並嘗試 MineMCP 操作。"""
    intents = _resolve_intents(
        npc_ids=npc_ids,
        quest_ids=quest_ids,
        item_ids=item_ids,
        apply_all=apply_all,
    )
    bridge = _bridge_status_for_apply(dry_run)
    results: list[dict[str, Any]] = []
    for kind, entity in intents:
        if kind == "npc":
            results.append(_apply_npc(entity, dry_run=dry_run, bridge=bridge))
        elif kind == "quest":
            results.append(_apply_quest(entity, dry_run=dry_run, bridge=bridge))
        else:
            results.append(_apply_item(entity, dry_run=dry_run, bridge=bridge))

    summary = _summarize_results(results)
    return {
        "results": results,
        "summary": summary,
        "bridge": bridge,
        "dry_run": dry_run,
    }
