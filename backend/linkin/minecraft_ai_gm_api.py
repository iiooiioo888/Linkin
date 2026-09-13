"""Minecraft AI GM REST 端點。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from backend.linkin.minecraft_ai_gm import (
    get_gm_config,
    gm_tick,
    list_gm_runs,
    react_to_event_id,
    update_gm_config,
)

gm_router = APIRouter(prefix="/linkin/minecraft/gm", tags=["linkin-minecraft-gm"])


@gm_router.get("/config")
def api_gm_config() -> dict[str, Any]:
    return {"config": get_gm_config()}


@gm_router.put("/config")
def api_gm_config_update(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return {"config": update_gm_config(body)}


@gm_router.get("/runs")
def api_gm_runs(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    return list_gm_runs(limit=limit)


@gm_router.post("/tick")
def api_gm_tick(limit: int = Query(5, ge=1, le=20)) -> dict[str, Any]:
    return gm_tick(limit=limit)


@gm_router.post("/react")
def api_gm_react(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    event_id = str(body.get("event_id") or "").strip()
    force = bool(body.get("force"))
    if not event_id:
        return {"ok": False, "error": "missing_event_id"}
    return react_to_event_id(event_id, force=force)


def register_minecraft_gm_routes(app) -> None:
    app.include_router(gm_router)


__all__ = ["gm_router", "register_minecraft_gm_routes"]
