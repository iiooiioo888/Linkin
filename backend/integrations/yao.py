"""Yao Agents 平台客戶端（自架 agent 工作區／任務板 Open API）。

對接自架 Yao（Open API，SSE/WebSocket 支援；本客戶端先落 REST 面）：
- ``list_workspaces``：列出工作區
- ``create_task``：對話轉任務上板
- ``get_task``／``list_tasks``：任務板查詢
- ``ask_agent``：呼叫專家／任務 agent（整合進自家流程用）

設計定位：Yao 是**外部任務承載平台**；Linkin 只經 Open API 互動，
禁止在 Yao 側另開隱式指揮鏈（C-SEAT-005 精神：Linkin 工作項只經協調器下發，
Yao 任務的建立必須是顯式動作）。

環境變數：
- ``LINKIN_YAO_ENABLED``（預設 false）
- ``LINKIN_YAO_BASE_URL``（預設 http://localhost:5099）
- ``LINKIN_YAO_API_KEY``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:5099"


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="yao",
        base_url=e.get("LINKIN_YAO_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_YAO_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_YAO_API_KEY", ""),
    )


@dataclass
class YaoClient:
    """Yao Open API 的 fail-open 封裝。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)

    def list_workspaces(self) -> IntegrationResponse:
        return self.http.get("api/v1/workspaces")

    def list_tasks(self, workspace_id: str, *, status: str = "") -> IntegrationResponse:
        path = f"api/v1/workspaces/{workspace_id}/tasks"
        if status:
            path += f"?status={status}"
        return self.http.get(path)

    def create_task(
        self,
        workspace_id: str,
        *,
        title: str,
        prompt: str,
        agent_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> IntegrationResponse:
        """顯式建立任務（對話 → 任務板）；禁止在串流回調中自動呼叫。"""
        payload: dict[str, Any] = {"title": title, "prompt": prompt}
        if agent_id:
            payload["agent_id"] = agent_id
        if metadata:
            payload["metadata"] = metadata
        return self.http.post(f"api/v1/workspaces/{workspace_id}/tasks", payload)

    def get_task(self, workspace_id: str, task_id: str) -> IntegrationResponse:
        return self.http.get(f"api/v1/workspaces/{workspace_id}/tasks/{task_id}")

    def ask_agent(self, agent_id: str, message: str, *, context: dict[str, Any] | None = None) -> IntegrationResponse:
        payload: dict[str, Any] = {"message": message}
        if context:
            payload["context"] = context
        return self.http.post(f"api/v1/agents/{agent_id}/ask", payload)

    def health(self) -> dict:
        """模組健康檢查用。"""
        if not self.http.enabled:
            return {"ok": True, "enabled": False}
        resp = self.http.get("api/v1/health")
        return {"ok": resp.ok, "enabled": True, "reason_code": resp.reason_code}
