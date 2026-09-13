"""Minecraft 任務進度運行時：每玩家持久化進度與 GM／手動套用路徑。

任務定義仍存於 ``quests.json``（含 ``objectives`` 模板）；玩家進度存於
``quest_progress.json``，避免高頻寫入污染實體目錄。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.linkin.knowledge import list_entities

_lock = threading.Lock()

QUEST_STATUS_ACTIVE = "active"
QUEST_STATUS_COMPLETED = "completed"
QUEST_STATUS_FAILED = "failed"

DEFAULT_OBJECTIVE_ID = "main"
ADVANCE_STATUSES = frozenset({"advance", "complete", "failed"})


def _data_dir() -> Path:
    return Path(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin"))


def _progress_path() -> Path:
    return _data_dir() / "quest_progress.json"


def reset_quest_progress() -> None:
    """測試用：清空任務進度檔。"""
    path = _progress_path()
    with _lock:
        if path.exists():
            path.unlink()


def _load_all() -> list[dict[str, Any]]:
    path = _progress_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw) if isinstance(raw, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_all(rows: list[dict[str, Any]]) -> None:
    path = _progress_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_player_id(player_id: str) -> str:
    return str(player_id or "").strip().lower()


def ensure_quest_objectives(quest: dict[str, Any]) -> list[dict[str, Any]]:
    """回傳任務目標列表；若未定義則產生預設單一目標。"""
    raw = quest.get("objectives")
    if isinstance(raw, list) and raw:
        out: list[dict[str, Any]] = []
        for idx, item in enumerate(raw):
            if not isinstance(item, dict):
                continue
            obj_id = str(item.get("id") or f"obj-{idx + 1}").strip()
            title = str(item.get("title") or item.get("name") or obj_id).strip()
            out.append(
                {
                    "id": obj_id,
                    "title": title,
                    "description": str(item.get("description") or "").strip(),
                }
            )
        if out:
            return out
    title = str(quest.get("title") or "任務").strip()
    return [{"id": DEFAULT_OBJECTIVE_ID, "title": f"完成：{title}", "description": ""}]


def get_quest_definition(quest_id: str) -> dict[str, Any] | None:
    return next((q for q in list_entities("quests") if str(q.get("id")) == quest_id), None)


def _progress_key(player_id: str, quest_id: str) -> tuple[str, str]:
    return (_norm_player_id(player_id), str(quest_id))


def _find_progress(rows: list[dict[str, Any]], player_id: str, quest_id: str) -> dict[str, Any] | None:
    pid, qid = _progress_key(player_id, quest_id)
    for row in rows:
        if _norm_player_id(str(row.get("player_id") or "")) == pid and str(row.get("quest_id") or "") == qid:
            return row
    return None


def _objective_state(progress: dict[str, Any], objective_id: str) -> dict[str, Any]:
    objectives = progress.get("objectives")
    if not isinstance(objectives, dict):
        objectives = {}
        progress["objectives"] = objectives
    state = objectives.get(objective_id)
    if not isinstance(state, dict):
        state = {"done": False, "updated_at": None}
        objectives[objective_id] = state
    return state


def _all_objectives_done(quest: dict[str, Any], progress: dict[str, Any]) -> bool:
    template = ensure_quest_objectives(quest)
    objectives = progress.get("objectives") or {}
    for obj in template:
        obj_id = str(obj["id"])
        state = objectives.get(obj_id) or {}
        if not state.get("done"):
            return False
    return bool(template)


def _validate_objective(quest: dict[str, Any], objective_id: str) -> str | None:
    """回傳錯誤碼或 None（合法）。"""
    template_ids = {str(o["id"]) for o in ensure_quest_objectives(quest)}
    if objective_id not in template_ids:
        return "invalid_objective_id"
    return None


def list_quest_progress(
    *,
    player_id: str | None = None,
    quest_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    rows = _load_all()
    out: list[dict[str, Any]] = []
    pid_filter = _norm_player_id(player_id) if player_id else ""
    qid_filter = str(quest_id or "")
    status_filter = str(status or "").strip().lower()
    for row in rows:
        if pid_filter and _norm_player_id(str(row.get("player_id") or "")) != pid_filter:
            continue
        if qid_filter and str(row.get("quest_id") or "") != qid_filter:
            continue
        if status_filter and str(row.get("status") or "") != status_filter:
            continue
        out.append(enrich_progress_row(row))
    out.sort(key=lambda r: float(r.get("updated_at") or 0), reverse=True)
    return out


def enrich_progress_row(row: dict[str, Any]) -> dict[str, Any]:
    """附加任務定義與目標完成摘要。"""
    quest_id = str(row.get("quest_id") or "")
    quest = get_quest_definition(quest_id)
    template = ensure_quest_objectives(quest or {})
    objectives_raw = row.get("objectives")
    objectives_state: dict[str, Any] = objectives_raw if isinstance(objectives_raw, dict) else {}
    objectives_out: list[dict[str, Any]] = []
    for obj in template:
        obj_id = str(obj["id"])
        raw_state = objectives_state.get(obj_id)
        state: dict[str, Any] = raw_state if isinstance(raw_state, dict) else {}
        objectives_out.append(
            {
                "id": obj_id,
                "title": obj.get("title"),
                "description": obj.get("description"),
                "done": bool(state.get("done")),
                "updated_at": state.get("updated_at"),
            }
        )
    done_count = sum(1 for o in objectives_out if o.get("done"))
    enriched = dict(row)
    enriched["objectives_detail"] = objectives_out
    enriched["objectives_done"] = done_count
    enriched["objectives_total"] = len(objectives_out)
    if quest:
        enriched["quest_title"] = quest.get("title")
        enriched["quest_type"] = quest.get("quest_type")
        enriched["quest_region"] = quest.get("region")
        enriched["world_status"] = quest.get("world_status")
    return enriched


def build_active_quests_for_player(player_id: str) -> list[dict[str, Any]]:
    """供 GM／AI context 使用的活躍任務摘要。"""
    return list_quest_progress(player_id=player_id, status=QUEST_STATUS_ACTIVE)


def build_active_quests_summary(*, limit: int = 12) -> list[dict[str, Any]]:
    """跨玩家活躍任務摘要（監控／AI context）。"""
    rows = list_quest_progress(status=QUEST_STATUS_ACTIVE)
    return rows[: max(1, min(limit, 50))]


def apply_quest_progress(
    *,
    player_id: str,
    quest_id: str,
    objective_id: str | None = None,
    status: str = "advance",
    note: str = "",
    last_event_id: str | None = None,
    dry_run: bool = False,
    source: str = "manual",
) -> dict[str, Any]:
    """驗證並套用任務進度。回傳 {ok, status, ...}。"""
    player_id = _norm_player_id(player_id)
    quest_id = str(quest_id or "").strip()
    if not player_id:
        return {"ok": False, "status": "error", "reason": "missing_player_id"}
    if not quest_id:
        return {"ok": False, "status": "error", "reason": "missing_quest_id"}

    quest = get_quest_definition(quest_id)
    if not quest:
        return {"ok": False, "status": "error", "reason": "quest_not_found", "quest_id": quest_id}

    action_status = str(status or "advance").strip().lower()
    if action_status not in ADVANCE_STATUSES:
        return {"ok": False, "status": "error", "reason": "invalid_status", "quest_id": quest_id}

    template = ensure_quest_objectives(quest)
    obj_id = str(objective_id or "").strip()
    if not obj_id:
        # 預設：第一個未完成目標，或 main
        progress_existing = _find_progress(_load_all(), player_id, quest_id)
        objectives_state = (progress_existing or {}).get("objectives") or {}
        pending = next((str(o["id"]) for o in template if not (objectives_state.get(str(o["id"])) or {}).get("done")), None)
        obj_id = pending or str(template[0]["id"])

    obj_err = _validate_objective(quest, obj_id)
    if obj_err:
        return {
            "ok": False,
            "status": "error",
            "reason": obj_err,
            "quest_id": quest_id,
            "objective_id": obj_id,
            "valid_objectives": [str(o["id"]) for o in template],
        }

    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "quest_id": quest_id,
            "player_id": player_id,
            "objective_id": obj_id,
            "action_status": action_status,
        }

    now = time.time()
    rows = _load_all()
    progress = _find_progress(rows, player_id, quest_id)
    if progress is None:
        progress = {
            "id": f"qprog-{uuid.uuid4().hex[:12]}",
            "player_id": player_id,
            "quest_id": quest_id,
            "status": QUEST_STATUS_ACTIVE,
            "objectives": {},
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "last_event_id": None,
            "notes": [],
        }
        rows.append(progress)

    if str(progress.get("status") or "") == QUEST_STATUS_COMPLETED and action_status != "failed":
        return {
            "ok": False,
            "status": "error",
            "reason": "quest_already_completed",
            "quest_id": quest_id,
            "player_id": player_id,
        }

    obj_state = _objective_state(progress, obj_id)
    if action_status in {"advance", "complete"}:
        obj_state["done"] = True
        obj_state["updated_at"] = now

    notes = list(progress.get("notes") or [])
    note_text = str(note or "").strip()[:200]
    if note_text:
        notes.append({"ts": now, "text": note_text, "objective_id": obj_id, "source": source})
    progress["notes"] = notes[-30:]
    progress["updated_at"] = now
    if last_event_id:
        progress["last_event_id"] = str(last_event_id)

    if action_status == "failed":
        progress["status"] = QUEST_STATUS_FAILED
        progress["completed_at"] = now
    elif action_status == "complete" or _all_objectives_done(quest, progress):
        progress["status"] = QUEST_STATUS_COMPLETED
        progress["completed_at"] = now
    else:
        progress["status"] = QUEST_STATUS_ACTIVE

    _save_all(rows)
    enriched = enrich_progress_row(progress)

    _log_progress_event(
        player_id=player_id,
        quest_id=quest_id,
        objective_id=obj_id,
        quest_status=str(progress.get("status")),
        note=note_text,
        source=source,
        last_event_id=last_event_id,
    )

    return {
        "ok": True,
        "status": "applied",
        "quest_id": quest_id,
        "player_id": player_id,
        "objective_id": obj_id,
        "quest_status": progress.get("status"),
        "progress": enriched,
    }


def _log_progress_event(
    *,
    player_id: str,
    quest_id: str,
    objective_id: str,
    quest_status: str,
    note: str,
    source: str,
    last_event_id: str | None,
) -> None:
    from backend.linkin.minecraft_observability import safe_append_minecraft_event

    quest = get_quest_definition(quest_id)
    title = str((quest or {}).get("title") or quest_id)
    summary = f"任務進度：{title} → {quest_status}（{objective_id}）"
    safe_append_minecraft_event(
        domain="quest",
        action="progress",
        status=quest_status,
        summary=summary,
        details={
            "quest_id": quest_id,
            "objective_id": objective_id,
            "note": note,
            "source": source,
            "last_event_id": last_event_id,
        },
        entity_refs={"player_id": player_id, "quest_id": quest_id},
    )


def evaluate_heuristics(
    event: dict[str, Any],
    *,
    player_id: str | None = None,
) -> list[dict[str, Any]]:
    """非 LLM 啟發式建議（dry signal，不自動套用）。"""
    pid = _norm_player_id(player_id or "")
    refs = event.get("entity_refs") or {}
    if not pid:
        pid = _norm_player_id(str(refs.get("player_id") or refs.get("player_name") or ""))
    if not pid:
        return []

    action = str(event.get("action") or "")
    details = event.get("details") or {}
    suggestions: list[dict[str, Any]] = []

    active = list_quest_progress(player_id=pid, status=QUEST_STATUS_ACTIVE)
    if not active:
        return []

    for prog in active:
        quest_id = str(prog.get("quest_id") or "")
        quest = get_quest_definition(quest_id)
        if not quest:
            continue
        q_title = str(quest.get("title") or "")
        region = str(quest.get("region") or "")

        if action == "chat":
            message = str(details.get("message") or details.get("text") or "").lower()
            keywords = [w for w in q_title.replace("：", " ").split() if len(w) >= 2]
            if keywords and any(kw.lower() in message for kw in keywords[:3]):
                suggestions.append(
                    {
                        "signal": "chat_keyword",
                        "quest_id": quest_id,
                        "player_id": pid,
                        "confidence": "low",
                        "hint": f"聊天提及任務「{q_title}」",
                    }
                )

        if action in {"move", "teleport", "join"}:
            pos = details.get("position") or refs.get("position")
            quest_loc = quest.get("location") or quest.get("coords") or quest.get("spawn")
            if isinstance(pos, dict) and isinstance(quest_loc, dict):
                try:
                    dx = float(pos.get("x", 0)) - float(quest_loc.get("x", 0))
                    dz = float(pos.get("z", 0)) - float(quest_loc.get("z", 0))
                    dist = (dx * dx + dz * dz) ** 0.5
                    if dist <= 32:
                        suggestions.append(
                            {
                                "signal": "near_poi",
                                "quest_id": quest_id,
                                "player_id": pid,
                                "confidence": "medium",
                                "hint": f"玩家接近任務區域（{region or q_title}，距約 {int(dist)} 格）",
                                "distance": round(dist, 1),
                            }
                        )
                except (TypeError, ValueError):
                    pass

        if action in {"inventory", "pickup"}:
            held = details.get("held") or details.get("item")
            inv = details.get("inventory") or details.get("items")
            reward_keys = list((quest.get("rewards") or {}).keys())
            item_names: list[str] = []
            if isinstance(held, dict):
                item_names.append(str(held.get("name") or held.get("id") or ""))
            if isinstance(inv, list):
                for it in inv[:12]:
                    if isinstance(it, dict):
                        item_names.append(str(it.get("name") or it.get("id") or ""))
            for name in item_names:
                if name and any(rk in name for rk in reward_keys if rk):
                    suggestions.append(
                        {
                            "signal": "item_held",
                            "quest_id": quest_id,
                            "player_id": pid,
                            "confidence": "low",
                            "hint": f"玩家持有與任務獎勵相關物品：{name}",
                            "item": name,
                        }
                    )

    return suggestions[:10]


__all__ = [
    "ADVANCE_STATUSES",
    "DEFAULT_OBJECTIVE_ID",
    "QUEST_STATUS_ACTIVE",
    "QUEST_STATUS_COMPLETED",
    "QUEST_STATUS_FAILED",
    "apply_quest_progress",
    "build_active_quests_for_player",
    "build_active_quests_summary",
    "enrich_progress_row",
    "ensure_quest_objectives",
    "evaluate_heuristics",
    "get_quest_definition",
    "list_quest_progress",
    "reset_quest_progress",
]
