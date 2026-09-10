"""MCP 連線管理（Model Context Protocol）。

讓 Linkin 能連上任意 MCP server，自動發現其 tools 並動態註冊進
公司工具註冊表（backend/company/tools.py），角色即可透過既有
tool_call 閉環調用。與 minecraft_mcp.py（MineMCP 專用、JSON-RPC）
互補：這裡是通用 MCP 客戶端。

支援三種傳輸：
- stdio：本地子行程，spawn `command args...`，走 stdin/stdout JSON-RPC
- sse  ：遠端 Server-Sent Events（舊版 MCP HTTP 傳輸）
- http ：streamable HTTP（新版 MCP，POST 回 JSON 或 SSE 串流）

安全界線：
- 連線、列工具、呼叫工具全部有逾時；失敗走降級不炸執行路徑。
- 每個 server 可設 enabled 與 allowed_tools（白名單），預設唯讀。
- 工具名加 `<server>__<tool>` 前綴，避免與內建／彼此撞名。

資料落盤 backend/data/mcp_servers.json。
"""

from __future__ import annotations

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
from typing import Any, List, Self

import httpx

logger = logging.getLogger(__name__)

DATA_PATH = Path("backend/data/mcp_servers.json")
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


def probe_server(server: McpServer) -> dict[str, Any]:
    """連線探測：回傳 {ok, tool_count, tools[], error, latency_ms}。"""
    t0 = time.monotonic()
    try:
        sess = _make_session(server)
        # stdio 用 context manager；http 的 list_tools 自帶 client
        if isinstance(sess, _StdioSession):
            with sess as s:
                tools = s.list_tools()
        else:
            tools = sess.list_tools()
        names = [str(t.get("name", "")) for t in tools if isinstance(t, dict)]
        return {
            "ok": True,
            "tool_count": len(names),
            "tools": names,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "error": "",
        }
    except Exception as exc:
        logger.warning("MCP 探測失敗 %s：%s", server.name, exc)
        return {
            "ok": False,
            "tool_count": 0,
            "tools": [],
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "error": str(exc)[:400],
        }


class McpRegistry:
    """MCP server 註冊表 + 動態工具掛載。執行緒安全，mtime 感知。"""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else DATA_PATH
        self._lock = threading.Lock()
        self._servers: dict[str, McpServer] = {}
        self._loaded = False
        self._mtime: float = 0.0
        self._mounted: set[str] = set()  # 已掛進 tool_registry 的 "serverId::tool"

    # ── 持久化 ──

    def load(self) -> None:
        with self._lock:
            self._load_locked()

    def _load_locked(self) -> None:
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            mtime = 0.0
        if self._loaded and mtime == self._mtime:
            return
        self._loaded = True
        self._mtime = mtime
        if not self._path.exists():
            self._servers = {}
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("MCP 設定讀取失敗（保留記憶體版本）：%s", exc)
            return
        servers: dict[str, McpServer] = {}
        for row in raw.get("servers", []) if isinstance(raw, dict) else []:
            try:
                srv = McpServer(
                    id=str(row.get("id") or _slug(str(row.get("name", "")))),
                    name=str(row.get("name", "")).strip(),
                    transport=str(row.get("transport", "stdio")).strip() or "stdio",
                    command=str(row.get("command", "")),
                    env=dict(row.get("env") or {}),
                    url=str(row.get("url", "")),
                    headers=dict(row.get("headers") or {}),
                    enabled=bool(row.get("enabled", True)),
                    allowed_tools=[str(t).strip() for t in (row.get("allowed_tools") or []) if str(t).strip()],
                    readonly=bool(row.get("readonly", True)),
                    timeout=float(row.get("timeout", DEFAULT_TIMEOUT)),
                    created_at=str(row.get("created_at", "")),
                    updated_at=str(row.get("updated_at", "")),
                    last_probe=dict(row.get("last_probe") or {}),
                )
                if srv.name:
                    servers[srv.id] = srv
            except (TypeError, ValueError):
                continue
        self._servers = servers

    def _save_locked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "servers": [s.to_dict() for s in self._servers.values()]}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)
        self._mtime = self._path.stat().st_mtime

    # ── CRUD ──

    def list(self) -> list[McpServer]:
        with self._lock:
            self._load_locked()
            return list(self._servers.values())

    def get(self, server_id: str) -> McpServer | None:
        with self._lock:
            self._load_locked()
            return self._servers.get(server_id)

    def upsert(
        self,
        name: str,
        transport: str,
        *,
        server_id: str | None = None,
        command: str = "",
        env: dict[str, str] | None = None,
        url: str = "",
        headers: dict[str, str] | None = None,
        enabled: bool = True,
        allowed_tools: List[str] | None = None,
        readonly: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> McpServer:
        name = (name or "").strip()
        transport = (transport or "stdio").strip().lower()
        if transport not in ("stdio", "sse", "http"):
            raise ValueError("transport 只能是 stdio / sse / http")
        if not name:
            raise ValueError("server 名稱不可為空")
        if transport == "stdio" and not command.strip():
            raise ValueError("stdio server 需要 command")
        if transport in ("sse", "http") and not url.strip():
            raise ValueError(f"{transport} server 需要 url")
        now = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        with self._lock:
            self._load_locked()
            sid = server_id or _slug(name)
            old = self._servers.get(sid)
            srv = McpServer(
                id=sid,
                name=name,
                transport=transport,
                command=command.strip(),
                env=dict(env or {}),
                url=url.strip(),
                headers=dict(headers or {}),
                enabled=bool(enabled),
                allowed_tools=[str(t).strip() for t in (allowed_tools or []) if str(t).strip()],
                readonly=bool(readonly),
                timeout=max(2.0, min(float(timeout or DEFAULT_TIMEOUT), 300.0)),
                created_at=old.created_at if old else now,
                updated_at=now,
                last_probe=old.last_probe if old else {},
            )
            self._servers[sid] = srv
            self._save_locked()
            # 設定變更 → 讓下次 mount 重抓
            self._mounted = {m for m in self._mounted if not m.startswith(f"{sid}::")}
            logger.info("MCP server 已保存：%s（%s）", srv.name, srv.transport)
            return srv

    def set_enabled(self, server_id: str, enabled: bool) -> McpServer:
        with self._lock:
            self._load_locked()
            srv = self._servers.get(server_id)
            if not srv:
                raise KeyError(f"server 不存在：{server_id}")
            srv.enabled = bool(enabled)
            srv.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            self._save_locked()
            self._mounted = {m for m in self._mounted if not m.startswith(f"{server_id}::")}
            return srv

    def delete(self, server_id: str) -> bool:
        with self._lock:
            self._load_locked()
            if server_id not in self._servers:
                return False
            del self._servers[server_id]
            self._save_locked()
            self._mounted = {m for m in self._mounted if not m.startswith(f"{server_id}::")}
            return True

    def probe(self, server_id: str) -> dict[str, Any]:
        with self._lock:
            self._load_locked()
            srv = self._servers.get(server_id)
            if not srv:
                raise KeyError(f"server 不存在：{server_id}")
            snapshot = McpServer(**{k: v for k, v in srv.to_dict().items() if k != "last_probe"})
        result = probe_server(snapshot)
        with self._lock:
            self._load_locked()
            cur = self._servers.get(server_id)
            if cur:
                cur.last_probe = result
                self._save_locked()
        return result

    def call(self, server_id: str, tool: str, args: dict[str, Any]) -> Any:
        """直接呼叫某 server 的工具（手動測試用，繞過 tool_registry）。"""
        with self._lock:
            self._load_locked()
            srv = self._servers.get(server_id)
            if not srv:
                raise KeyError(f"server 不存在：{server_id}")
            snapshot = McpServer(**{k: v for k, v in srv.to_dict().items() if k != "last_probe"})
        sess = _make_session(snapshot)
        if isinstance(sess, _StdioSession):
            with sess as s:
                return s.call_tool(tool, args)
        return sess.call_tool(tool, args)

    # ── 動態掛載進 tool_registry ──

    def mount_tools(self, tool_registry: Any, *, force: bool = False) -> List[str]:
        """探測所有啟用 server，把其工具註冊進 tool_registry。

        回傳本次新增的內部工具名列表。已掛載的跳過（除非 force）。
        任何 server 探測失敗都只記警告，不影響其他 server。
        """
        mounted: List[str] = []
        for srv in self.list():
            if not srv.enabled:
                continue
            try:
                sess = _make_session(srv)
                if isinstance(sess, _StdioSession):
                    with sess as s:
                        tools = s.list_tools()
                else:
                    tools = sess.list_tools()
            except Exception as exc:
                logger.warning("MCP mount 探測 %s 失敗：%s", srv.name, exc)
                continue
            allowed = set(srv.allowed_tools) if srv.allowed_tools else None
            for tool in tools:
                if not isinstance(tool, dict):
                    continue
                raw_name = str(tool.get("name", "")).strip()
                if not raw_name or (allowed and raw_name not in allowed):
                    continue
                internal = f"{srv.id}__{raw_name}"
                if internal in self._mounted and not force:
                    continue
                schema = tool.get("inputSchema") or tool.get("input_schema") or {}
                params = schema.get("properties") if isinstance(schema, dict) else {}
                desc = str(tool.get("description", "")).strip() or f"MCP 工具 {srv.name}/{raw_name}"
                tool_registry.register(
                    name=internal,
                    description=f"[MCP:{srv.name}] {desc}",
                    parameters=params if isinstance(params, dict) else {},
                    execute=lambda _sid=srv.id, _t=raw_name, **kwargs: self.call(_sid, _t, kwargs),
                    allowed_roles=[],           # 空 = 全角色（再經 catalog_allowed 收斂）
                    readonly=bool(srv.readonly),
                    timeout_seconds=srv.timeout,
                )
                self._mounted.add(internal)
                mounted.append(internal)
        if mounted:
            logger.info("MCP 工具已掛載 %d 個：%s", len(mounted), ", ".join(mounted))
        return mounted


mcp_registry = McpRegistry()
