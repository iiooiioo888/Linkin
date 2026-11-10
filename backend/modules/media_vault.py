"""Media Vault 模組目錄契約（展示 + 監控雙面板）。"""

from __future__ import annotations

from typing import Any

from backend.modules.registry import (
    ModuleCapability,
    ModuleNavGroup,
    ModuleNavItem,
    ModuleSpec,
    register_module,
)

_PREFIX = "/media-vault"


def media_vault_health() -> dict[str, Any]:
    from backend.media_vault.monitor import monitor_summary

    try:
        summary = monitor_summary()
        return {"ok": True, "total_posts": summary.get("total_posts", 0)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_media_vault_spec() -> ModuleSpec:
    return ModuleSpec(
        id="media-vault",
        title="Media Vault",
        description="採集圖片展示與管線監控（共享媒資庫，面板互不依賴）",
        version="1.0.0",
        kind="integration",
        icon="generic",
        default_page="control",
        enabled=True,
        api_prefix=_PREFIX,
        capabilities=(
            ModuleCapability(
                id="control",
                title="控制",
                description="MediaCrawler 採集與入庫",
                api_prefix=_PREFIX,
                routes=("/control/overview", "/ingest/replay"),
            ),
            ModuleCapability(
                id="gallery",
                title="图库",
                description="瀏覽與篩選採集圖片",
                api_prefix=_PREFIX,
                routes=("/images", "/files/{asset_id}"),
            ),
            ModuleCapability(
                id="monitor",
                title="監控",
                description="ingest 管線健康度",
                api_prefix=_PREFIX,
                routes=("/monitor/summary",),
            ),
        ),
        nav_groups=(
            ModuleNavGroup(
                id="panels",
                label="採集媒資",
                items=(
                    ModuleNavItem(
                        key="control",
                        icon="⎈",
                        label="控制",
                        hint="採集任務與入庫",
                        capability="control",
                    ),
                    ModuleNavItem(
                        key="gallery",
                        icon="▦",
                        label="图库",
                        hint="篩選、網格與燈箱",
                        capability="gallery",
                    ),
                    ModuleNavItem(
                        key="monitor",
                        icon="◉",
                        label="監控",
                        hint="成功率、合規與儲存",
                        capability="monitor",
                    ),
                ),
            ),
        ),
        page_aliases=(("展示", "gallery"),),
        health=media_vault_health,
    )


def register_media_vault_module() -> ModuleSpec:
    return register_module(build_media_vault_spec())
