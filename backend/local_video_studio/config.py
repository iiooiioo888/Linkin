"""Local Video Studio 環境變數（M0：僅讀取，不做雲端呼叫）。"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _truthy(raw: str | None, default: bool = False) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class LocalVideoStudioConfig:
    """Studio 執行設定。雲端預設關閉（``CLOUD_ENABLED=false``）。"""

    app_env: str = "dev"
    api_key: str = ""
    database_url: str = ""
    redis_url: str = ""
    storage_base: str = "/mnt/ai-media"
    comfyui_url: str = "http://127.0.0.1:8188"
    agent_id: str = "workstation-5090"
    cloud_enabled: bool = False
    module_enabled: bool = True
    use_mock_comfy: bool = True
    compliance_text: str = "AI 生成"
    compliance_position: str = "bottom-right"


def load_config() -> LocalVideoStudioConfig:
    """優先讀 ``LVS_*``，再回退規格中的通用鍵名（僅用於 studio overlay）。"""
    # LVS_USE_MOCK_COMFY 優先；未設時：有顯式 COMFYUI_URL 則走真實，否則 mock
    mock_env = os.getenv("LVS_USE_MOCK_COMFY")
    comfy_url = (
        os.getenv("LVS_COMFYUI_URL") or os.getenv("COMFYUI_URL") or ""
    ).strip()
    if mock_env is not None and str(mock_env).strip() != "":
        use_mock = _truthy(mock_env, default=True)
    else:
        use_mock = not bool(comfy_url)
    return LocalVideoStudioConfig(
        app_env=(os.getenv("LVS_APP_ENV") or os.getenv("APP_ENV") or "dev").strip(),
        api_key=(os.getenv("LVS_API_KEY") or os.getenv("API_KEY") or "").strip(),
        database_url=(
            os.getenv("LVS_DATABASE_URL")
            or os.getenv("LOCAL_VIDEO_STUDIO_DATABASE_URL")
            or ""
        ).strip(),
        redis_url=(os.getenv("LVS_REDIS_URL") or os.getenv("REDIS_URL") or "").strip(),
        storage_base=(
            os.getenv("LVS_STORAGE_BASE") or os.getenv("STORAGE_BASE") or "/mnt/ai-media"
        ).strip(),
        comfyui_url=comfy_url or "http://127.0.0.1:8188",
        agent_id=(
            os.getenv("LVS_AGENT_ID") or os.getenv("AGENT_ID") or "workstation-5090"
        ).strip(),
        cloud_enabled=_truthy(
            os.getenv("LVS_CLOUD_ENABLED") or os.getenv("CLOUD_ENABLED"),
            default=False,
        ),
        module_enabled=_truthy(os.getenv("LVS_ENABLED"), default=True),
        use_mock_comfy=use_mock,
        compliance_text=(
            os.getenv("LVS_COMPLIANCE_TEXT") or os.getenv("COMPLIANCE_TEXT") or "AI 生成"
        ).strip(),
        compliance_position=(
            os.getenv("LVS_COMPLIANCE_POSITION")
            or os.getenv("COMPLIANCE_POSITION")
            or "bottom-right"
        ).strip(),
    )
