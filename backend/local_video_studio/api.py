"""Local Video Studio HTTP API（M0：health only）。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from backend.local_video_studio.config import load_config

router = APIRouter(prefix="/local-video-studio", tags=["local-video-studio"])


@router.get("/health")
def health() -> dict[str, Any]:
    """模組探針：``{ok: true}``。不呼叫雲端或 ComfyUI。"""
    cfg = load_config()
    return {
        "ok": True,
        "module": "local-video-studio",
        "milestone": "M0",
        "cloud_enabled": cfg.cloud_enabled,
        "app_env": cfg.app_env,
    }


@router.get("/api/v1/health")
def health_v1() -> dict[str, Any]:
    """規格前綴相容別名（與 ``/local-video-studio/health`` 同內容）。"""
    return health()


def register_local_video_studio(app: FastAPI) -> None:
    app.include_router(router)
