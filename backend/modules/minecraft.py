"""Minecraft 世界模組：世界觀、內容、admin、建築、MineMCP 橋接。

實作仍在 ``backend/linkin/*`` 與 ``backend/tools/minecraft_mcp.py``；
本檔只宣告目錄契約，方便與後續世界模組並列。
"""

from __future__ import annotations

from typing import Any

from backend.modules.registry import (
    ModuleCapability,
    ModuleNavGroup,
    ModuleNavItem,
    ModuleSpec,
    register_module,
)

_PREFIX = "/linkin"


def minecraft_health() -> dict[str, Any]:
    from backend.linkin.constitution import load_constitution
    from backend.linkin.minecraft import monitor_status as minecraft_monitor_status

    const = load_constitution()
    factions = const.get("factions") or []
    magic = const.get("magic") or {}
    bridge = minecraft_monitor_status()
    admin: dict[str, Any]
    try:
        from backend.linkin.server_admin import health_snapshot

        admin = health_snapshot()
    except Exception as exc:
        admin = {"status": "unavailable", "error": str(exc)}
    return {
        "ok": bool(const.get("world_name")),
        "world": {
            "name": const.get("world_name"),
            "factions": len(factions),
            "magic": bool(magic.get("name")),
        },
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
            "world": bridge.get("world"),
        },
        "admin": admin,
    }


def build_minecraft_spec() -> ModuleSpec:
    return ModuleSpec(
        id="minecraft",
        title="Minecraft",
        description="靈境世界觀、伺服器 Admin、內容工作室與 MineMCP 橋接",
        version="1.0.0",
        kind="world",
        icon="minecraft",
        default_page="world",
        enabled=True,
        api_prefix=_PREFIX,
        capabilities=(
            ModuleCapability(
                id="worldview",
                title="世界觀",
                description="憲法、陣營、事件與總覽",
                api_prefix=_PREFIX,
                routes=("/constitution", "/overview", "/events"),
            ),
            ModuleCapability(
                id="content",
                title="世界內容",
                description="NPC、任務、道具",
                api_prefix=_PREFIX,
                routes=(
                    "/npcs",
                    "/quests",
                    "/items",
                    "/narrative/workspaces",
                    "/narrative/pipelines",
                    "/build-briefs",
                    "/world-intents",
                    "/map",
                ),
            ),
            ModuleCapability(
                id="admin",
                title="Admin",
                description="遊戲指令與伺服器運維（健康／批准／巡檢／審計）",
                api_prefix=_PREFIX,
                routes=(
                    "/admin/execute",
                    "/server/health",
                    "/server/ask",
                    "/server/approvals",
                    "/server/patrol",
                    "/server/report",
                    "/server/audit",
                ),
            ),
            ModuleCapability(
                id="building",
                title="建築",
                description="Schematic 生成、匯入與派發",
                api_prefix=_PREFIX,
                routes=("/buildings", "/buildings/generate", "/buildings/import", "/build-briefs"),
            ),
            ModuleCapability(
                id="bridge",
                title="橋接",
                description="MineMCP 狀態、探測與護欄呼叫",
                api_prefix=_PREFIX,
                routes=("/minecraft/status", "/minecraft/probe", "/minecraft/call"),
            ),
        ),
        nav_groups=(
            ModuleNavGroup(
                id="world",
                label="世界",
                items=(
                    ModuleNavItem("world", "✧", "世界觀", "憲法與陣營", capability="worldview"),
                    ModuleNavItem("npcs", "☺", "NPC", "角色卡與對話", capability="content"),
                    ModuleNavItem("quests", "⚑", "任務", "主線／支線／日常", capability="content"),
                    ModuleNavItem("narrative", "✎", "敘事工作區", "Phase 0 故事草稿桌", capability="content"),
                    ModuleNavItem("items", "◆", "道具", "稀有度平衡", capability="content"),
                ),
            ),
            ModuleNavGroup(
                id="studio",
                label="工作室",
                items=(
                    ModuleNavItem(
                        "studio",
                        "◈",
                        "工作室角色",
                        "建築／敘事／NPC／道具班底",
                        roster="agents",
                    ),
                ),
            ),
            ModuleNavGroup(
                id="server",
                label="伺服器",
                items=(
                    ModuleNavItem("admin", "⌘", "Admin", "健康、批准、巡檢、指令", capability="admin"),
                    ModuleNavItem("building", "⌂", "建築", "Schematic 生成與派發", capability="building"),
                    ModuleNavItem("minecraft", "⇄", "橋接", "MineMCP 探測與審計", capability="bridge"),
                ),
            ),
        ),
        page_aliases=(
            ("mc", "minecraft"),
            ("minecraft_mcp", "minecraft"),
            ("bridge", "minecraft"),
            ("studio_roles", "studio"),
            ("linkin_roles", "studio"),
            ("server", "admin"),
            ("ops_admin", "admin"),
        ),
        health=minecraft_health,
    )


def register_minecraft_module() -> ModuleSpec:
    return register_module(build_minecraft_spec())
