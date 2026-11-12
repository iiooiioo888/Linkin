"""MCP server 設定模型：McpServer dataclass、ID slug 與 JSON-RPC init 參數。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any

_ID_RE = re.compile(r"[^a-z0-9_\-]+")
PROTOCOL_VERSION = "2024-11-05"
DEFAULT_TIMEOUT = 20.0


def _slug(value: str) -> str:
    """ASCII 化 ID；純中文等名稱走穩定雜湊（同名同 ID，避免時間戳撞號）。"""
    slug = _ID_RE.sub("_", (value or "").strip().lower()).strip("_")
    if slug:
        return slug
    digest = hashlib.sha1((value or "").encode("utf-8")).hexdigest()[:8]
    return f"mcp_{digest}"


@dataclass
class McpServer:
    """一條 MCP server 連線設定。"""

    id: str
    name: str
    transport: str = "stdio"          # stdio | sse | http
    command: str = ""                 # stdio：可執行檔（可含參數）
    env: dict[str, str] = field(default_factory=dict)  # stdio：額外環境
    url: str = ""                     # sse/http：端點
    headers: dict[str, str] = field(default_factory=dict)  # sse/http：自訂標頭
    enabled: bool = True
    allowed_tools: list[str] = field(default_factory=list)  # 空 = 全部
    readonly: bool = True
    timeout: float = DEFAULT_TIMEOUT
    created_at: str = ""
    updated_at: str = ""
    # 執行期狀態（不落盤的探測結果另存 last_probe）
    last_probe: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ── JSON-RPC 訊息 ──

def _init_params() -> dict[str, Any]:
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "linkin-evoloop", "version": "1.0"},
    }
