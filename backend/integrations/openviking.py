"""OpenViking 上下文資料庫客戶端（L0/L1 分層召回，token 節省）。

對接本地 OpenViking HTTP 服務（``openviking-server``，預設 ``http://localhost:1933``）：
- ``find``：語義檢索（目錄遞迴，回傳帶 URI 的命中）
- ``read``／``abstract``／``overview``：按 L0（摘要 ~100 tokens）／L1（概覽 ~2k）分層讀取
- ``add_resource``：寫入資源（文件／repo／URL）

token 節省路徑：``recall_tiered`` 預設只載入 L0 摘要做相關性判斷，
必要時再升 L1；**永不**預設載入 L2 全文（對齊 OpenViking 分層載入設計）。

環境變數：
- ``LINKIN_OPENVIKING_ENABLED``（預設 false）
- ``LINKIN_OPENVIKING_BASE_URL``（預設 http://localhost:1933）
- ``LINKIN_OPENVIKING_API_KEY``
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import quote

from backend.integrations.base import IntegrationConfig, IntegrationResponse, ResilientHttpClient

DEFAULT_BASE_URL = "http://localhost:1933"


class VikingTier(str, Enum):
    L0_ABSTRACT = "abstract"   # ~100 tokens：快速相關性判斷
    L1_OVERVIEW = "overview"   # ~2k tokens：規劃用結構重點
    L2_DETAILS = "details"     # 全文：僅顯式需要時讀取


def config_from_env(env: dict[str, str] | None = None) -> IntegrationConfig:
    e = env if env is not None else os.environ
    return IntegrationConfig(
        name="openviking",
        base_url=e.get("LINKIN_OPENVIKING_BASE_URL", DEFAULT_BASE_URL),
        enabled=e.get("LINKIN_OPENVIKING_ENABLED", "false").lower() == "true",
        api_key=e.get("LINKIN_OPENVIKING_API_KEY", ""),
    )


@dataclass
class OpenVikingClient:
    """OpenViking 服務的 fail-open 封裝。"""

    http: ResilientHttpClient = field(init=False)

    def __init__(self, config: IntegrationConfig | None = None, **http_kwargs: Any) -> None:
        self.http = ResilientHttpClient(config or config_from_env(), **http_kwargs)

    def find(self, query: str, *, top_k: int = 5) -> IntegrationResponse:
        # 真實路徑為 /api/v1/search/find；分頁參數名是 limit（非 top_k）。
        return self.http.post("api/v1/search/find", {"query": query, "limit": top_k})

    def read(self, uri: str, *, tier: VikingTier = VikingTier.L0_ABSTRACT) -> IntegrationResponse:
        # L0/L1/L2 各為 GET 端點（query 參數 uri），非單一 POST /read。
        path = f"api/v1/content/{tier.value}?uri={quote(uri, safe='')}"
        return self.http.get(path)

    def add_resource(self, source: str) -> IntegrationResponse:
        # AddResourceRequest 的欄位是 path（交付來源：檔案／URL／repo）。
        return self.http.post("api/v1/resources", {"path": source})

    def recall_tiered(
        self,
        query: str,
        *,
        top_k: int = 5,
        max_tier: VikingTier = VikingTier.L1_OVERVIEW,
        l1_threshold: float = 0.75,
        max_chars: int = 2000,
    ) -> dict:
        """分層召回：先 find，再按相關分數決定讀 L0 或 L1（預設不進 L2）。

        Returns:
            dict: ``fragments``（含 uri/tier/text）、``degraded``、``reason_code``。
        """
        found = self.find(query, top_k=top_k)
        if not found.ok:
            return {"fragments": [], "degraded": True, "reason_code": found.reason_code}
        hits = self._extract_hits(found.data)[:top_k]
        fragments: list[dict] = []
        budget = max_chars
        for hit in hits:
            uri = str(hit.get("uri") or "")
            if not uri:
                continue
            score = float(hit.get("score") or 0.0)
            tier = VikingTier.L1_OVERVIEW if (score >= l1_threshold and max_tier is not VikingTier.L0_ABSTRACT) else VikingTier.L0_ABSTRACT
            if max_tier is VikingTier.L0_ABSTRACT:
                tier = VikingTier.L0_ABSTRACT
            content = self.read(uri, tier=tier)
            if not content.ok:
                continue
            text = str(self._extract_text(content.data) or "").strip()
            if not text:
                continue
            if len(text) > budget:
                text = text[: max(0, budget)]
            fragments.append({"uri": uri, "tier": tier.value, "text": text})
            budget -= len(text)
            if budget <= 0:
                break
        return {"fragments": fragments, "degraded": False, "reason_code": found.reason_code}

    @staticmethod
    def _extract_hits(data: Any) -> list[dict]:
        if not isinstance(data, dict):
            return []
        for key in ("results", "hits", "data"):
            node = data.get(key)
            if isinstance(node, list):
                return [x for x in node if isinstance(x, dict)]
        return []

    @staticmethod
    def _extract_text(data: Any) -> str:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("content", "text", "abstract", "overview"):
                value = data.get(key)
                if isinstance(value, str):
                    return value
        return ""
