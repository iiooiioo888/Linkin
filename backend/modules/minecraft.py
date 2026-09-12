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
        default_page="monitor",
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
                    "/map/plans",
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
            ModuleCapability(
                id="monitor",
                title="監控",
                description="Minecraft 運維監控與 AI 可觀測性",
                api_prefix=_PREFIX,
                routes=(
                    "/minecraft/monitor/summary",
                    "/minecraft/ai/snapshot",
                    "/minecraft/ai/events",
                    "/minecraft/ai/context",
                    "/minecraft/layout-preview",
                ),
            ),
            ModuleCapability(
                id="plugins",
                title="插件／地圖",
                description="第三方插件目錄、地圖 URL 設定與內嵌檢視",
                api_prefix=_PREFIX,
                routes=(
                    "/minecraft/plugins/catalog",
                    "/minecraft/plugins/settings",
                    "/minecraft/plugins/{id}/probe",
                ),
            ),
        ),
        nav_groups=(
            ModuleNavGroup(
                id="monitor",
                label="總覽／監控",
                items=(
                    ModuleNavItem("monitor", "◎", "監控總覽", "KPI、管線、橋接與 AI 可見事件", capability="monitor"),
                    ModuleNavItem("map_monitor", "◇", "地圖監控", "地圖計畫與落地狀態", capability="monitor"),
                    ModuleNavItem("npc_monitor", "☺", "NPC 監控", "待落地／已落地／失敗", capability="monitor"),
                    ModuleNavItem("quest_item_monitor", "◆", "任務／道具監控", "世界意圖狀態帶", capability="monitor"),
                    ModuleNavItem("build_monitor", "⌂", "建築落地監控", "build-brief 任務與方塊", capability="monitor"),
                    ModuleNavItem("bridge_monitor", "⇄", "橋接健康", "MineMCP 連線與錯誤", capability="bridge"),
                ),
            ),
            ModuleNavGroup(
                id="narrative_group",
                label="敘事／RPG",
                items=(
                    ModuleNavItem("narrative", "✎", "敘事工作區", "Phase 0–5 一鍵管線", capability="content"),
                ),
            ),
            ModuleNavGroup(
                id="world_build",
                label="世界與建築",
                items=(
                    ModuleNavItem("building", "⌂", "建築", "Schematic 生成與派發", capability="building"),
                    ModuleNavItem("map_plan", "◫", "地圖計畫", "區域地圖生成／預覽／落地", capability="content"),
                    ModuleNavItem(
                        "layout-preview",
                        "▣",
                        "布局預覽",
                        "原生 2D 俯視（map_plan／建築意圖／POI，無需 Dynmap）",
                        capability="content",
                    ),
                    ModuleNavItem("minecraft", "⇄", "橋接", "MineMCP 探測與審計", capability="bridge"),
                ),
            ),
            ModuleNavGroup(
                id="entities",
                label="實體",
                items=(
                    ModuleNavItem("npcs", "☺", "NPC", "角色卡與對話", capability="content"),
                    ModuleNavItem("quests", "⚑", "任務", "主線／支線／日常", capability="content"),
                    ModuleNavItem("items", "◆", "道具", "稀有度平衡", capability="content"),
                ),
            ),
            ModuleNavGroup(
                id="plugins",
                label="插件／地圖",
                items=(
                    ModuleNavItem(
                        "plugin-hub",
                        "⚡",
                        "插件中心",
                        "Dynmap／BlueMap／Squaremap 等目錄與連線狀態",
                        capability="plugins",
                    ),
                    ModuleNavItem(
                        "server-map",
                        "🗺",
                        "伺服器地圖",
                        "內嵌網頁地圖（Dynmap／BlueMap／Squaremap）",
                        capability="plugins",
                    ),
                ),
            ),
            ModuleNavGroup(
                id="admin_group",
                label="憲章／工作室／管理",
                items=(
                    ModuleNavItem("world", "✧", "世界觀", "憲法與陣營", capability="worldview"),
                    ModuleNavItem("studio", "◈", "工作室角色", "建築／敘事班底", roster="agents"),
                    ModuleNavItem("admin", "⌘", "Admin", "健康、批准、巡檢、指令", capability="admin"),
                ),
            ),
        ),
        page_aliases=(
            ("mc", "minecraft"),
            ("minecraft_mcp", "minecraft"),
            ("bridge", "minecraft"),
            ("overview", "monitor"),
            ("monitor_hub", "monitor"),
            ("map", "map_monitor"),
            ("studio_roles", "studio"),
            ("linkin_roles", "studio"),
            ("server", "admin"),
            ("ops_admin", "admin"),
            ("plugins", "plugin-hub"),
            ("plugin_center", "plugin-hub"),
            ("server_map", "server-map"),
            ("dynmap", "server-map"),
            ("layout_preview", "layout-preview"),
        ),
        health=minecraft_health,
    )


def register_minecraft_module() -> ModuleSpec:
    return register_module(build_minecraft_spec())
