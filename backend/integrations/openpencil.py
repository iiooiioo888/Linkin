"""OpenPencil 客戶端（AI-native 向量設計工具，Design-as-Code）。

對接自架 OpenPencil 服務（預設 ``http://localhost:4300``）：
- ``generate_design``：prompt → 畫布上的 UI 設計（Design-as-Code）
- ``list_projects``／``get_project``：設計專案查詢

定位：OpenPencil 是**外部設計生成平台**；Linkin 經 Open API 顯式觸發
設計生成，結果（設計稿 URL／DSL）回寫對話。禁止在串流完成時自動觸發
（C-PLUGIN-001 精神）。

環境變數：
- ``LINKIN_OPENPENCIL_ENABLED``（預設 false）
- ``LINKIN_OPENPENCIL_BASE_URL``（預設 http://localhost:4300）
- ``LINKIN_OPENPENCIL_API_KEY``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:4300"


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="openpencil",
        base_url=e.get("LINKIN_OPENPENCIL_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_OPENPENCIL_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_OPENPENCIL_API_KEY", ""),
    )


@dataclass
class OpenPencilClient:
    """OpenPencil 服務的 fail-open 封裝。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)

    def generate_design(
        self,
        prompt: str,
        *,
        project_id: str = "",
        style: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationResponse:
        """顯式觸發設計生成（prompt → UI 畫布）。"""
        payload: dict[str, Any] = {"prompt": prompt}
        if project_id:
            payload["project_id"] = project_id
        if style:
            payload["style"] = style
        if metadata:
            payload["metadata"] = metadata
        return self.http.post("api/v1/designs/generate", payload)

    def list_projects(self) -> IntegrationResponse:
        return self.http.get("api/v1/projects")

    def get_project(self, project_id: str) -> IntegrationResponse:
        return self.http.get(f"api/v1/projects/{project_id}")

    def health(self) -> dict:
        if not self.http.enabled:
            return {"ok": True, "enabled": False}
        resp = self.http.get("api/v1/health")
        return {"ok": resp.ok, "enabled": True, "reason_code": resp.reason_code}
