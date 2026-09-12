"""敘事草稿落庫：經既有 Linkin entity／store 路徑，禁止第二套圖譜寫入。"""

from __future__ import annotations

import uuid
from typing import Any

from backend.linkin.knowledge import COL_EVENTS, COL_NPCS, COL_WORLDVIEW, get_store, upsert_entity
from backend.linkin.tools import TOOL_NPC_CREATE, ToolValidationError, format_npc_text, invoke_tool

KNOWN_DRAFT_KEYS = frozenset({"quest", "npc", "lore_note", "chapter_beat"})


class NarrativeCommitError(ValueError):
    def __init__(self, message: str, *, key: str = "", code: str = "invalid"):
        super().__init__(message)
        self.key = key
        self.code = code


def _as_dict(value: Any, *, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise NarrativeCommitError(f"草稿「{key}」必須為 JSON 物件", key=key)
    return dict(value)


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
    store = get_store()
    store.upsert(
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


def _commit_lore_note(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "設定筆記").strip() or "設定筆記"
    text = str(payload.get("text") or payload.get("content") or "").strip()
    if not text:
        raise NarrativeCommitError("lore_note 需要 text 或 content", key="lore_note")
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    record_id = str(payload.get("id") or f"lore-{uuid.uuid4().hex[:10]}")
    stored = get_store().upsert(
        COL_WORLDVIEW,
        f"{title}\n{text}",
        {
            "kind": "lore_note",
            "title": title,
            "tags": list(tags),
            "source": "narrative_workspace",
        },
        record_id=record_id,
        query_hint=f"敘事設定筆記 {title}",
        skip_quality=True,
    )
    return {"id": stored.get("id") or record_id, "title": title, "kind": "lore_note"}


def _commit_chapter_beat(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "章節節拍").strip() or "章節節拍"
    text = str(payload.get("text") or payload.get("beat") or "").strip()
    if not text:
        raise NarrativeCommitError("chapter_beat 需要 text 或 beat", key="chapter_beat")
    chapter = str(payload.get("chapter") or "").strip()
    beat_order = payload.get("beat_order") or payload.get("order") or 0
    record_id = str(payload.get("id") or f"beat-{uuid.uuid4().hex[:10]}")
    meta = {
        "kind": "chapter_beat",
        "title": title,
        "chapter": chapter,
        "beat_order": beat_order,
        "source": "narrative_workspace",
    }
    stored = get_store().upsert(
        COL_EVENTS,
        f"【{chapter or '未命名章'}】{title}\n{text}",
        meta,
        record_id=record_id,
        skip_quality=True,
    )
    return {"id": stored.get("id") or record_id, "title": title, "kind": "chapter_beat"}


_COMMITTERS: dict[str, Any] = {
    "quest": _commit_quest,
    "npc": _commit_npc,
    "lore_note": _commit_lore_note,
    "chapter_beat": _commit_chapter_beat,
}


def commit_narrative_drafts(drafts: dict[str, Any]) -> dict[str, Any]:
    """把已知草稿鍵落庫；回傳 committed entity id 摘要。"""
    committed: dict[str, Any] = {}
    errors: list[dict[str, str]] = []
    unknown_keys = sorted(set(drafts.keys()) - KNOWN_DRAFT_KEYS)
    for key in unknown_keys:
        errors.append({"key": key, "code": "unknown_draft_key", "message": f"未知草稿鍵：{key}"})
    for key in sorted(KNOWN_DRAFT_KEYS & set(drafts.keys())):
        try:
            committed[key] = _COMMITTERS[key](_as_dict(drafts[key], key=key))
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
