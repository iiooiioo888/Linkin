"""WeKnora 企業級 RAG 知識庫客戶端。

對接本地 WeKnora（docker compose，Backend API 預設 ``http://localhost:8080``）：
- ``list_knowledge_bases``：列出知識庫（scope 檢索範圍用）
- ``search``：hybrid 檢索（向量＋關鍵字），回傳原文段落＋knowledge_id
- ``ask``：由 WeKnora 自帶 RAG/ReAct 管線直接給含引用答案（可選）

token 節省路徑：``recall_passages`` 只取 top-k 段落注入，而非整份文件。

環境變數：
- ``LINKIN_WEKNORA_ENABLED``（預設 false）
- ``LINKIN_WEKNORA_BASE_URL``（預設 http://localhost:8080）
- ``LINKIN_WEKNORA_API_KEY``（scoped API key，建議唯讀能力）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:8080"


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="weknora",
        base_url=e.get("LINKIN_WEKNORA_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_WEKNORA_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_WEKNORA_API_KEY", ""),
    )


@dataclass
class WeKnoraClient:
    """WeKnora 服務的 fail-open 封裝（對齊 dsh-weknora 唯讀四工具語義）。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)

    def list_knowledge_bases(self) -> IntegrationResponse:
        return self.http.get("api/v1/knowledge-bases")

    def search(
        self,
        query: str,
        *,
        knowledge_base_id: str = "",
        top_k: int = 5,
    ) -> IntegrationResponse:
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if knowledge_base_id:
            payload["knowledge_base_id"] = knowledge_base_id
        return self.http.post("api/v1/knowledge-search", payload)

    def ask(self, query: str, *, knowledge_base_id: str = "", mode: str = "rag") -> IntegrationResponse:
        payload: dict[str, Any] = {"query": query, "mode": mode}
        if knowledge_base_id:
            payload["knowledge_base_id"] = knowledge_base_id
        return self.http.post("api/v1/ask", payload)

    def recall_passages(
        self,
        query: str,
        *,
        knowledge_base_id: str = "",
        top_k: int = 5,
        max_chars: int = 1500,
    ) -> dict:
        """召回 top-k 段落並壓縮為注入片段（含來源 knowledge_id，可供引用）。"""
        resp = self.search(query, knowledge_base_id=knowledge_base_id, top_k=top_k)
        if not resp.ok:
            return {"fragments": [], "degraded": True, "reason_code": resp.reason_code}
        items = self._extract_items(resp.data)[:top_k]
        fragments: list[dict] = []
        budget = max_chars
        for item in items:
            text = str(item.get("content") or item.get("passage") or "").strip()
            if not text:
                continue
            if len(text) > budget:
                text = text[: max(0, budget)]
            fragments.append({"knowledge_id": item.get("knowledge_id") or item.get("id"), "text": text})
            budget -= len(text)
            if budget <= 0:
                break
        return {"fragments": fragments, "degraded": False, "reason_code": resp.reason_code}

    @staticmethod
    def _extract_items(data: Any) -> list[dict]:
        if not isinstance(data, dict):
            return []
        for key in ("data", "results", "passages"):
            node = data.get(key)
            if isinstance(node, list):
                return [x for x in node if isinstance(x, dict)]
        return []
