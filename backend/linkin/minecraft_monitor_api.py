"""Minecraft 監控與 AI 可觀測性 REST。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from backend.linkin.layout_preview import build_layout_preview
from backend.linkin.minecraft_observability import (
    build_ai_context,
    build_ai_snapshot,
    build_monitor_summary,
    list_minecraft_events,
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
) -> dict[str, Any]:
    return list_minecraft_events(since=since, cursor=cursor, limit=limit)


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
