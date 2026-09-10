"""MemOS 本地部署客戶端（token 節省主力）。

對接本地 MemOS REST 服務（預設 ``http://localhost:8000/product``）：
- ``create_cube``：建立記憶 cube（跨任務的記憶容器）
- ``add``：寫入記憶（user/assistant 訊息對）
- ``search``：語義召回相關記憶片段

token 節省路徑：``recall_for_prompt`` 只回傳 top-k 記憶片段，
取代把完整對話歷史塞進 prompt。

環境變數：
- ``LINKIN_MEMOS_ENABLED``（預設 false，顯式啟用）
- ``LINKIN_MEMOS_BASE_URL``（預設 http://localhost:8000）
- ``LINKIN_MEMOS_API_KEY``（本地部署可留空）
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:8000"


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="memos",
        base_url=e.get("LINKIN_MEMOS_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_MEMOS_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_MEMOS_API_KEY", ""),
    )


@dataclass
class MemosClient:
    """MemOS 本地服務的 fail-open 封裝。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)

    # ── cube 管理 ──

    def create_cube(self, cube_id: str, *, owner_id: str, cube_name: str = "") -> IntegrationResponse:
        return self.http.post(
            "product/create_cube",
            {
                "cube_id": cube_id,
                "owner_id": owner_id,
                "cube_name": cube_name or cube_id,
            },
        )

    # ── 記憶寫入 ──

    def add_memory(
        self,
        cube_id: str,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        writable_cube_ids: list[str] | None = None,
        async_mode: str = "async",
    ) -> IntegrationResponse:
        return self.http.post(
            "product/add",
            {
                "user_id": user_id,
                "writable_cube_ids": writable_cube_ids or [cube_id],
                "messages": messages,
                "async_mode": async_mode,
            },
        )

    # ── 記憶召回（token 節省核心）──

    def search_memory(
        self,
        query: str,
        *,
        user_id: str,
        readable_cube_ids: list[str],
        top_k: int = 5,
    ) -> IntegrationResponse:
        return self.http.post(
            "product/search",
            {
                "query": query,
                "user_id": user_id,
                "readable_cube_ids": readable_cube_ids,
                "top_k": top_k,
            },
        )

    def recall_for_prompt(
        self,
        query: str,
        *,
        user_id: str,
        cube_ids: list[str],
        top_k: int = 5,
        max_chars: int = 1200,
    ) -> dict:
        """召回並壓縮為可直接注入 prompt 的片段清單。

        Returns:
            dict: ``fragments``（字串清單，已截斷至 ``max_chars`` 總量）、
            ``degraded``（服務不可用時 True）、``reason_code``。
        """
        resp = self.search_memory(query, user_id=user_id, readable_cube_ids=cube_ids, top_k=top_k)
        if not resp.ok:
            return {"fragments": [], "degraded": True, "reason_code": resp.reason_code}
        raw_items = self._extract_items(resp.data)
        fragments: list[str] = []
        budget = max_chars
        for item in raw_items:
            text = str(item.get("memory") or item.get("content") or "").strip()
            if not text:
                continue
            if len(text) > budget:
                text = text[: max(0, budget)]
            fragments.append(text)
            budget -= len(text)
            if budget <= 0:
                break
        return {"fragments": fragments, "degraded": False, "reason_code": resp.reason_code}

    @staticmethod
    def _extract_items(data: Any) -> list[dict]:
        """容忍 MemOS 回應的常見包裝層。"""
        if not isinstance(data, dict):
            return []
        for key in ("data", "result", "memories"):
            node = data.get(key)
            if isinstance(node, list):
                return [x for x in node if isinstance(x, dict)]
            if isinstance(node, dict):
                inner = node.get("memories") or node.get("memory_list")
                if isinstance(inner, list):
                    return [x for x in inner if isinstance(x, dict)]
        return []
