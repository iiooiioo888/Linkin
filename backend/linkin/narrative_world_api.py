"""Phase 3 REST：敘事 NPC／任務／道具預覽與落地（需使用者明確觸發 apply）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from backend.linkin.narrative_world_apply import (
    WorldIntentError,
    apply_world_intents,
    list_pending_intents,
    preview_world_intents,
)

world_intent_router = APIRouter(prefix="/linkin/world-intents", tags=["linkin-world-intents"])


def _intent_http(exc: WorldIntentError) -> HTTPException:
    status = 404 if exc.code == "not_found" else 400
    return HTTPException(status_code=status, detail={"message": str(exc), "code": exc.code, **exc.extra})


def _ids_from_body(body: dict[str, Any], kind: str) -> list[str]:
    plural = f"{kind}_ids"
    camel = f"{kind}Ids"
    raw = body.get(plural) or body.get(camel) or body.get(kind) or []
    if isinstance(raw, str):
        return [raw] if raw.strip() else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _selection_from_body(body: dict[str, Any]) -> dict[str, Any]:
    return {
        "npc_ids": _ids_from_body(body, "npc"),
        "quest_ids": _ids_from_body(body, "quest"),
        "item_ids": _ids_from_body(body, "item"),
        "apply_all": bool(body.get("apply_all") or body.get("applyAll")),
    }


@world_intent_router.get("")
def api_list_pending_intents() -> dict[str, Any]:
    pending = list_pending_intents()
    return {"pending": pending, "count": pending["count"]}


@world_intent_router.post("/preview")
def api_preview_world_intents(body: dict[str, Any]) -> dict[str, Any]:
    try:
        return preview_world_intents(**_selection_from_body(body))
    except WorldIntentError as exc:
        raise _intent_http(exc) from exc


@world_intent_router.post("/apply")
def api_apply_world_intents(body: dict[str, Any]) -> dict[str, Any]:
    if not body.get("confirm"):
        raise HTTPException(
            status_code=400,
            detail={"message": "落地 NPC／任務／道具需 confirm=true 明確確認", "code": "confirm_required"},
        )
    try:
        return apply_world_intents(
            **_selection_from_body(body),
            dry_run=bool(body.get("dry_run")),
        )
    except WorldIntentError as exc:
        raise _intent_http(exc) from exc
