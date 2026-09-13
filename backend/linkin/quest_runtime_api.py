"""任務進度運行時 REST 端點。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from backend.linkin.quest_runtime import (
    apply_quest_progress,
    build_active_quests_summary,
    evaluate_heuristics,
    list_quest_progress,
)

quest_runtime_router = APIRouter(prefix="/linkin/minecraft/quests", tags=["linkin-minecraft-quests"])


@quest_runtime_router.get("/progress")
def api_list_quest_progress(
    player_id: str | None = Query(None),
    quest_id: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    rows = list_quest_progress(player_id=player_id, quest_id=quest_id, status=status)
    return {"progress": rows, "count": len(rows)}


@quest_runtime_router.get("/progress/summary")
def api_quest_progress_summary(limit: int = Query(12, ge=1, le=50)) -> dict[str, Any]:
    rows = build_active_quests_summary(limit=limit)
    active = len(rows)
    completed = len(list_quest_progress(status="completed"))
    failed = len(list_quest_progress(status="failed"))
    return {
        "active": active,
        "completed": completed,
        "failed": failed,
        "active_quests": rows,
    }


@quest_runtime_router.post("/progress/apply")
def api_apply_quest_progress(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    player_id = str(body.get("player_id") or "").strip()
    quest_id = str(body.get("quest_id") or "").strip()
    objective_id = body.get("objective_id") or body.get("objective")
    status_raw = str(body.get("status") or "advance").strip().lower()
    status = status_raw if status_raw in {"advance", "complete", "failed"} else "advance"
    note = str(body.get("note") or "")
    last_event_id = body.get("last_event_id")
    dry_run = bool(body.get("dry_run", False))
    source = str(body.get("source") or "api")
    result = apply_quest_progress(
        player_id=player_id,
        quest_id=quest_id,
        objective_id=str(objective_id) if objective_id else None,
        status=status,
        note=note,
        last_event_id=str(last_event_id) if last_event_id else None,
        dry_run=dry_run,
        source=source,
    )
    return result


@quest_runtime_router.post("/progress/heuristics")
def api_quest_heuristics(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    event = body.get("event")
    if not isinstance(event, dict):
        return {"ok": False, "error": "missing_event", "suggestions": []}
    player_id = body.get("player_id")
    suggestions = evaluate_heuristics(event, player_id=str(player_id) if player_id else None)
    return {"ok": True, "suggestions": suggestions, "count": len(suggestions)}


def register_quest_runtime_routes(app) -> None:
    app.include_router(quest_runtime_router)


__all__ = ["quest_runtime_router", "register_quest_runtime_routes"]
