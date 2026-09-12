"""敘事草稿落庫：經既有 Linkin entity／store 路徑，禁止第二套圖譜寫入。

Phase 0（故事草稿工作區）草稿鍵：story_arc、quest、npc、item、build_brief。
- build_brief 落庫為 build_briefs 實體；後續 Phase 2 由 Builder / MineMCP 管線消費（見 docs/linkin/narrative-workspace.md）。
- 地圖生成、即時 MineMCP 建造不在本模組實作。
"""

from __future__ import annotations

import uuid
from typing import Any

from backend.linkin.knowledge import COL_EVENTS, COL_NPCS, COL_WORLDVIEW, get_store, upsert_entity
from backend.linkin.tools import TOOL_ITEM_CREATE, TOOL_NPC_CREATE, ToolValidationError, format_npc_text, invoke_tool

# Phase 0 草稿鍵（與前端／一鍵草案對齊）
KNOWN_DRAFT_KEYS = frozenset({"story_arc", "quest", "npc", "item", "build_brief"})

# 舊鍵別名：測試／書籤相容，commit 時映射到新 committer
_LEGACY_DRAFT_ALIASES: dict[str, str] = {
    "lore_note": "story_arc",
    "chapter_beat": "story_arc",
}


class NarrativeCommitError(ValueError):
    def __init__(self, message: str, *, key: str = "", code: str = "invalid"):
        super().__init__(message)
        self.key = key
        self.code = code


def _as_dict(value: Any, *, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrativeCommitError(f"草稿「{key}」必須為 JSON 物件", key=key)
    return dict(value)


def _commit_story_arc(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "故事主線").strip() or "故事主線"
    summary = str(payload.get("summary") or payload.get("text") or "").strip()
    if not summary:
        raise NarrativeCommitError("story_arc 需要 summary 或 text", key="story_arc")
    region = str(payload.get("region") or "织庭都").strip()
    chapters = payload.get("chapters") or []
    if isinstance(chapters, str):
        chapters = [c.strip() for c in chapters.split("\n") if c.strip()]
    record_id = str(payload.get("id") or f"arc-{uuid.uuid4().hex[:10]}")
    arc = {
        "id": record_id,
        "title": title,
        "summary": summary,
        "region": region,
        "chapters": list(chapters),
        "tags": list(payload.get("tags") or []),
        "source": "narrative_workspace",
    }
    saved = upsert_entity("story_arcs", arc)
    get_store().upsert(
        COL_WORLDVIEW,
        f"故事主線：{title}\n{summary}",
        {"kind": "story_arc", "arc_id": saved["id"], "region": region, "source": "narrative_workspace"},
        record_id=f"arc-wv-{saved['id']}",
        skip_quality=True,
    )
    return saved


def _commit_quest(payload: dict[str, Any]) -> dict[str, Any]:
    quest_type = str(payload.get("quest_type") or payload.get("questType") or "支线").strip() or "支线"
    difficulty = str(payload.get("difficulty") or "普通").strip() or "普通"
    region = str(payload.get("region") or "织庭都").strip() or "织庭都"
    title = str(payload.get("title") or f"{quest_type}：{region}草稿").strip()
    description = str(payload.get("description") or "").strip() or f"敘事工作區提交的{quest_type}草稿。"
    quest = {
        "id": str(payload.get("id") or f"quest-{uuid.uuid4().hex[:10]}"),
        "player_id": str(payload.get("player_id") or payload.get("playerId") or "traveler-01"),
        "quest_type": quest_type,
        "difficulty": difficulty,
        "region": region,
        "title": title,
        "description": description,
        "rewards": payload.get("rewards") or {"灵丝碎片": 3},
        "source": "narrative_workspace",
    }
    saved = upsert_entity("quests", quest)
    get_store().upsert(
        COL_EVENTS,
        f"任務草稿提交：{saved['title']}\n{saved['description']}",
        {"kind": "quest", "quest_id": saved["id"], "player_id": saved["player_id"], "source": "narrative_workspace"},
        skip_quality=True,
    )
    return saved


def _commit_npc(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        invoked = invoke_tool(TOOL_NPC_CREATE, payload)
    except ToolValidationError as exc:
        raise NarrativeCommitError(str(exc), key="npc", code=exc.code) from exc
    card = dict(invoked["params"])
    card["id"] = str(card.get("id") or f"npc-{uuid.uuid4().hex[:10]}")
    stored = get_store().upsert(
        COL_NPCS,
        format_npc_text(card),
        dict(card),
        record_id=card["id"],
        query_hint=f"敘事工作區提交 NPC {card['name']}",
    )
    return {**card, "backend": stored["backend"]}


def _commit_item(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        invoked = invoke_tool(TOOL_ITEM_CREATE, payload)
    except ToolValidationError as exc:
        raise NarrativeCommitError(str(exc), key="item", code=exc.code) from exc
    params = invoked["params"]
    item = {"id": str(payload.get("id") or f"item-{uuid.uuid4().hex[:10]}"), **params}
    saved = upsert_entity("items", item)
    get_store().upsert(
        COL_WORLDVIEW,
        f"道具：{params['name']}（{params['type']} / {params['rarity']}）属性：{params['attributes']}",
        {"kind": "item", "item_id": saved["id"], "name": params["name"], "source": "narrative_workspace"},
        skip_quality=True,
    )
    return saved


def _commit_build_brief(payload: dict[str, Any]) -> dict[str, Any]:
    """建築／地圖意圖草稿。Phase 2：Builder.generate + MineMCP dispatch 消費此實體。"""
    title = str(payload.get("title") or "建築意圖").strip() or "建築意圖"
    prompt = str(payload.get("prompt") or payload.get("description") or "").strip()
    if not prompt:
        raise NarrativeCommitError("build_brief 需要 prompt 或 description", key="build_brief")
    brief = {
        "id": str(payload.get("id") or f"bb-{uuid.uuid4().hex[:10]}"),
        "title": title,
        "region": str(payload.get("region") or "织庭都").strip(),
        "location": payload.get("location") or payload.get("coords") or "0,64,0",
        "style": str(payload.get("style") or "织庭盟").strip(),
        "prompt": prompt,
        "block_count": int(payload.get("block_count") or payload.get("blockCount") or 800),
        "notes": str(payload.get("notes") or "").strip(),
        "status": "pending_builder",
        "source": "narrative_workspace",
    }
    saved = upsert_entity("build_briefs", brief)
    get_store().upsert(
        COL_WORLDVIEW,
        f"建築意圖：{title}\n{prompt}",
        {"kind": "build_brief", "brief_id": saved["id"], "region": brief["region"], "source": "narrative_workspace"},
        record_id=f"bb-wv-{saved['id']}",
        skip_quality=True,
    )
    return saved


_COMMITTERS: dict[str, Any] = {
    "story_arc": _commit_story_arc,
    "quest": _commit_quest,
    "npc": _commit_npc,
    "item": _commit_item,
    "build_brief": _commit_build_brief,
}


def _resolve_draft_key(key: str) -> str:
    return _LEGACY_DRAFT_ALIASES.get(key, key)


def commit_narrative_drafts(drafts: dict[str, Any]) -> dict[str, Any]:
    """把已知草稿鍵落庫；回傳 committed entity id 摘要。"""
    committed: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    normalized: dict[str, Any] = {}
    for raw_key, value in drafts.items():
        resolved = _resolve_draft_key(raw_key)
        if resolved in normalized and resolved != raw_key:
            continue
        normalized[resolved] = value

    unknown_keys = sorted(set(normalized.keys()) - KNOWN_DRAFT_KEYS)
    for key in unknown_keys:
        errors.append({"key": key, "code": "unknown_draft_key", "message": f"未知草稿鍵：{key}"})
    for key in sorted(KNOWN_DRAFT_KEYS & set(normalized.keys())):
        try:
            committed[key] = _COMMITTERS[key](_as_dict(normalized[key], key=key))
        except NarrativeCommitError as exc:
            errors.append({"key": exc.key or key, "code": exc.code, "message": str(exc)})
        except Exception as exc:
            errors.append({"key": key, "code": "commit_failed", "message": str(exc)})
    if errors and not committed:
        raise NarrativeCommitError(
            errors[0]["message"],
            key=errors[0]["key"],
            code=errors[0]["code"],
        )
    return {"committed": committed, "errors": errors}


__all__ = ["KNOWN_DRAFT_KEYS", "NarrativeCommitError", "commit_narrative_drafts"]
