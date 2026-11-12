"""MCP 連線管理（Model Context Protocol）。

讓 Linkin 能連上任意 MCP server，自動發現其 tools 並動態註冊進
公司工具註冊表（backend/company/tools.py），角色即可透過既有
tool_call 閉環調用。與 minecraft_mcp.py（MineMCP 專用、JSON-RPC）
互補：這裡是通用 MCP 客戶端。

支援三種傳輸：
- stdio：本地子行程，spawn command args...，走 stdin/stdout JSON-RPC
- sse  ：遠端 Server-Sent Events（舊版 MCP HTTP 傳輸）
- http ：streamable HTTP（新版 MCP，POST 回 JSON 或 SSE 串流）

安全界線：
- 連線、列工具、呼叫工具全部有逾時；失敗走降級不炸執行路徑。
- 每個 server 可設 enabled 與 allowed_tools（白名單），預設唯讀。
- 工具名加 server__tool 前綴，避免與內建／彼此撞名。

資料落盤 backend/data/mcp_servers.json。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- models：McpServer 設定模型、ID slug、JSON-RPC init 參數
- sessions：stdio／HTTP 連線、SSE 解析與內容展開
- registry：McpRegistry、server 探測與全域 mcp_registry
"""

from __future__ import annotations

import builtins
import hashlib
import json
import logging
import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Self

import httpx

from .models import DEFAULT_TIMEOUT, PROTOCOL_VERSION, McpServer, _slug
from .registry import DATA_PATH, McpRegistry, logger, mcp_registry, probe_server
from .sessions import _make_session, _parse_sse_payload, _unwrap_content

__all__ = [
    "DATA_PATH",
    "DEFAULT_TIMEOUT",
    "PROTOCOL_VERSION",
    "Any",
    "McpRegistry",
    "McpServer",
    "Path",
    "Self",
    "_make_session",
    "_parse_sse_payload",
    "_slug",
    "_unwrap_content",
    "annotations",
    "asdict",
    "builtins",
    "dataclass",
    "field",
    "hashlib",
    "httpx",
    "json",
    "logger",
    "logging",
    "mcp_registry",
    "os",
    "probe_server",
    "re",
    "shlex",
    "subprocess",
    "threading",
    "time",
]
