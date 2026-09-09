"""Linkin MCP server 的 stdio 傳輸入口。

用法（Claude Desktop / Cursor mcp 設定）：
    {"mcpServers": {"linkin": {"command": "/opt/linkin/.venv/bin/python",
                               "args": ["-m", "backend.mcp_server_stdio"],
                               "cwd": "/opt/linkin"}}}

stdin 逐行讀 JSON-RPC，stdout 逐行回。免 token（本機子行程信任）。
"""

from __future__ import annotations

import json
import sys

from backend.mcp_server import handle_message


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle_message(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
