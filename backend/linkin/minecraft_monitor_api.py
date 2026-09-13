"""Minecraft 監控與 AI 可觀測性 REST。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query

from backend.linkin.layout_preview import build_layout_preview
from backend.linkin.minecraft_observability import (
    build_ai_context,
    build_ai_snapshot,
    build_monitor_summary,
    list_minecraft_events,
)
from backend.linkin.minecraft_players import (
    get_player_detail,
    ingest_player_event,
    list_player_events,
    list_players_snapshot,
)

monitor_router = APIRouter(prefix="/linkin/minecraft", tags=["linkin-minecraft-monitor"])


@monitor_router.get("/monitor/summary")
def api_monitor_summary() -> dict[str, Any]:
    return build_monitor_summary()


@monitor_router.get("/ai/snapshot")
def api_ai_snapshot() -> dict[str, Any]:
    return build_ai_snapshot()


@monitor_router.get("/ai/events")
def api_ai_events(
    since: float | None = Query(None, description="Unix timestamp 下限"),
    cursor: str | None = Query(None, description="上一頁最後一筆事件 id"),
    limit: int = Query(50, ge=1, le=200),
    domain: str | None = Query(None, description="依 domain 篩選，例如 player"),
) -> dict[str, Any]:
    page = list_minecraft_events(since=since, cursor=cursor, limit=limit)
    if domain:
        events = [e for e in page.get("events") or [] if str(e.get("domain")) == domain]
        page = {**page, "events": events, "count": len(events)}
    return page


@monitor_router.get("/players")
def api_list_players(sync: bool = Query(True, description="是否觸發橋接輪詢")) -> dict[str, Any]:
    return list_players_snapshot(sync=sync)


@monitor_router.get("/players/events")
def api_player_events(
    since: float | None = Query(None),
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    player_id: str | None = Query(None),
    action: str | None = Query(None),
) -> dict[str, Any]:
    return list_player_events(
        since=since,
        cursor=cursor,
        limit=limit,
        player_id=player_id,
        action=action,
    )


@monitor_router.get("/players/{player_id}")
def api_player_detail(
    player_id: str,
    sync: bool = Query(False, description="強制向橋接拉取最新詳情"),
) -> dict[str, Any]:
    return get_player_detail(player_id, sync=sync)


@monitor_router.post("/players/ingest")
def api_ingest_player_event(body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    return ingest_player_event(body)


@monitor_router.get("/ai/context")
def api_ai_context(
    max_chars: int = Query(8000, ge=500, le=32000),
    format: str = Query("markdown", pattern="^(markdown|json)$"),
) -> dict[str, Any]:
    return build_ai_context(max_chars=max_chars, fmt=format)


@monitor_router.get("/layout-preview")
def api_layout_preview(
    plan_id: str | None = Query(None, description="指定 map_plan id；省略則取最新"),
    region: str | None = Query(None, description="依區域篩選"),
) -> dict[str, Any]:
    return build_layout_preview(plan_id=plan_id, region=region)


def register_minecraft_monitor_routes(app) -> None:
    app.include_router(monitor_router)


__all__ = ["monitor_router", "register_minecraft_monitor_routes"]
