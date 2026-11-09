"""Local Video Studio 模組目錄契約（M0–M2）。"""

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
        "milestone": "M2",
        "cloud_enabled": cfg.cloud_enabled,
    }


def build_local_video_studio_spec() -> ModuleSpec:
    return ModuleSpec(
        id="local-video-studio",
        title="Local Video Studio",
        description="本機優先 AI 影片生成（創意→鏡頭→草稿→審核→合成）",
        version="0.2.0",
        kind="integration",
        icon="generic",
        default_page="projects",
        enabled=True,
        api_prefix=_PREFIX,
        capabilities=(
            ModuleCapability(
                id="health",
                title="健康檢查",
                description="探針",
                api_prefix=_PREFIX,
                routes=("/health", "/api/v1/health"),
            ),
            ModuleCapability(
                id="projects",
                title="專案",
                description="專案列表與建立",
                api_prefix=f"{_PREFIX}/api/v1",
                routes=("/projects",),
            ),
            ModuleCapability(
                id="detail",
                title="專案詳情",
                description="專案狀態與統計",
                api_prefix=f"{_PREFIX}/api/v1",
                routes=("/projects/{id}",),
            ),
            ModuleCapability(
                id="shots",
                title="鏡頭板",
                description="鏡頭列表與鏡頭表匯入",
                api_prefix=f"{_PREFIX}/api/v1",
                routes=("/projects/{id}/shots", "/projects/{id}/scripts", "/shots/{id}"),
            ),
            ModuleCapability(
                id="jobs",
                title="任務",
                description="GenerationJob claim／complete（mock ComfyUI）",
                api_prefix=f"{_PREFIX}/api/v1",
                routes=("/jobs", "/jobs/{id}/claim", "/jobs/{id}/complete"),
            ),
        ),
        nav_groups=(
            ModuleNavGroup(
                id="studio",
                label="影片工作室",
                items=(
                    ModuleNavItem(
                        key="projects",
                        icon="▶",
                        label="專案",
                        hint="列表／建立",
                        capability="projects",
                    ),
                    ModuleNavItem(
                        key="detail",
                        icon="☰",
                        label="詳情",
                        hint="專案狀態",
                        capability="detail",
                    ),
                    ModuleNavItem(
                        key="shots",
                        icon="▦",
                        label="鏡頭板",
                        hint="鏡頭表",
                        capability="shots",
                    ),
                    ModuleNavItem(
                        key="jobs",
                        icon="◎",
                        label="任務",
                        hint="Render jobs",
                        capability="jobs",
                    ),
                ),
            ),
        ),
        page_aliases=(("home", "projects"),),
        health=local_video_studio_health,
    )


def register_local_video_studio_module() -> ModuleSpec:
    return register_module(build_local_video_studio_spec())
