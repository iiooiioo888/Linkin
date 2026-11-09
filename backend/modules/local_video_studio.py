"""Local Video Studio 模組目錄契約（M0：health + 空殼頁）。"""

from __future__ import annotations

from typing import Any

from backend.modules.registry import (
    ModuleCapability,
    ModuleNavGroup,
    ModuleNavItem,
    ModuleSpec,
    register_module,
)

_PREFIX = "/local-video-studio"


def local_video_studio_health() -> dict[str, Any]:
    from backend.local_video_studio.config import load_config

    cfg = load_config()
    return {
        "ok": True,
        "module": "local-video-studio",
        "milestone": "M0",
        "cloud_enabled": cfg.cloud_enabled,
    }


def build_local_video_studio_spec() -> ModuleSpec:
    return ModuleSpec(
        id="local-video-studio",
        title="Local Video Studio",
        description="本機優先 AI 影片生成（創意→鏡頭→草稿→審核→合成）",
        version="0.0.1",
        kind="integration",
        icon="generic",
        default_page="home",
        enabled=True,
        api_prefix=_PREFIX,
        capabilities=(
            ModuleCapability(
                id="health",
                title="健康檢查",
                description="M0 探針",
                api_prefix=_PREFIX,
                routes=("/health", "/api/v1/health"),
            ),
            ModuleCapability(
                id="home",
                title="工作室",
                description="空殼首頁（M0）",
                api_prefix=_PREFIX,
                routes=("/health",),
            ),
        ),
        nav_groups=(
            ModuleNavGroup(
                id="studio",
                label="影片工作室",
                items=(
                    ModuleNavItem(
                        key="home",
                        icon="▶",
                        label="工作室",
                        hint="M0 空殼",
                        capability="home",
                    ),
                ),
            ),
        ),
        health=local_video_studio_health,
    )


def register_local_video_studio_module() -> ModuleSpec:
    return register_module(build_local_video_studio_spec())
