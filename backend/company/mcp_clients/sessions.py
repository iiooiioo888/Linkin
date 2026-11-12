"""MCP 連線 session：stdio／HTTP 傳輸、SSE payload 解析與內容展開。"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Any, Self

import httpx

from .models import DEFAULT_TIMEOUT, McpServer, _init_params


class _StdioSession:
    """stdio 傳輸：spawn 子行程，逐行 JSON-RPC。"""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._proc: subprocess.Popen | None = None
        self._id = 0

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def __enter__(self) -> Self:
        argv = shlex.split(self.server.command)
        if not argv:
            raise ValueError("stdio server 缺少 command")
        env = dict(os.environ)
        env.update(self.server.env or {})
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            bufsize=1,
        )
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._proc:
            try:
                if self._proc.stdin is not None:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass

    def _send(self, method: str, params: dict[str, Any] | None) -> dict[str, Any]:
        assert self._proc and self._proc.stdin and self._proc.stdout
        req = {"jsonrpc": "2.0", "id": self._next_id(), "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(req) + "\n")
        self._proc.stdin.flush()
        line = self._proc.stdout.readline()
        if not line:
            err = self._proc.stderr.read() if self._proc.stderr else ""
            raise RuntimeError(f"stdio server 無回應：{err.strip()[:200]}")
        msg = json.loads(line)
        if "error" in msg:
            raise RuntimeError(f"MCP 錯誤：{msg['error']}")
        return msg.get("result", {})

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        assert self._proc and self._proc.stdin
        note = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._proc.stdin.write(json.dumps(note) + "\n")
        self._proc.stdin.flush()

    def list_tools(self) -> list[dict[str, Any]]:
        self._send("initialize", _init_params())
        self._notify("notifications/initialized")
        res = self._send("tools/list", {})
        return res.get("tools", []) or []

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        self._send("initialize", _init_params())
        self._notify("notifications/initialized")
        res = self._send("tools/call", {"name": name, "arguments": args or {}})
        return _unwrap_content(res)


class _HttpSession:
    """sse / http 傳輸：httpx 走 JSON-RPC over HTTP。"""

    def __init__(self, server: McpServer) -> None:
        self.server = server
        self._id = 0
        self._session_id: str | None = None

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _client(self) -> httpx.Client:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        headers.update(self.server.headers or {})
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        return httpx.Client(timeout=self.server.timeout or DEFAULT_TIMEOUT, headers=headers)

    def _post(self, client: httpx.Client, method: str, params: dict[str, Any] | None, notify: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notify:
            payload["id"] = self._next_id()
        resp = client.post(self.server.url, json=payload)
        sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
        if sid:
            self._session_id = sid
        if notify:
            return {}
        ctype = resp.headers.get("content-type", "")
        text = resp.text
        if "text/event-stream" in ctype:
            data = _parse_sse_payload(text)
        else:
            data = resp.json()
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(f"MCP 錯誤：{data['error']}")
        return data.get("result", {}) if isinstance(data, dict) else {}

    def list_tools(self) -> list[dict[str, Any]]:
        with self._client() as client:
            self._post(client, "initialize", _init_params())
            self._post(client, "notifications/initialized", None, notify=True)
            res = self._post(client, "tools/list", {})
            return res.get("tools", []) or []

    def call_tool(self, name: str, args: dict[str, Any]) -> Any:
        with self._client() as client:
            self._post(client, "initialize", _init_params())
            self._post(client, "notifications/initialized", None, notify=True)
            res = self._post(client, "tools/call", {"name": name, "arguments": args or {}})
            return _unwrap_content(res)


def _parse_sse_payload(text: str) -> dict[str, Any]:
    """從 SSE 串流取最後一個 data: 行的 JSON。"""
    last: dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if not chunk:
                continue
            try:
                parsed = json.loads(chunk)
                if isinstance(parsed, dict):
                    last = parsed
            except json.JSONDecodeError:
                continue
    return last


def _unwrap_content(res: dict[str, Any]) -> Any:
    """把 MCP tools/call 的 content[] 攤平成字串。"""
    if not isinstance(res, dict):
        return res
    content = res.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(str(block))
                continue
            if block.get("type") == "text" and "text" in block or "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(parts) if parts else json.dumps(res, ensure_ascii=False)
    if "structuredContent" in res:
        return json.dumps(res["structuredContent"], ensure_ascii=False)
    return json.dumps(res, ensure_ascii=False)


def _make_session(server: McpServer) -> Any:
    if server.transport == "stdio":
        return _StdioSession(server)
    if server.transport in ("sse", "http"):
        if not server.url:
            raise ValueError(f"{server.transport} server 缺少 url")
        return _HttpSession(server)
    raise ValueError(f"未知傳輸：{server.transport}")
