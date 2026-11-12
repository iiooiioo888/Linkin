"""MCP 註冊表：server 設定持久化、探測／呼叫、工具掛載與全域 mcp_registry。"""

from __future__ import annotations

import builtins
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

from . import _compat
from .models import DEFAULT_TIMEOUT, McpServer, _slug
from .sessions import _StdioSession

logger = logging.getLogger("backend.company.mcp_clients")

DATA_PATH = Path("backend/data/mcp_servers.json")


def probe_server(server: McpServer) -> dict[str, Any]:
    """連線探測：回傳 {ok, tool_count, tools[], error, latency_ms}。"""
    t0 = time.monotonic()
    try:
        sess = _compat._make_session(server)
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

    def sync_managed(
        self,
        *,
        server_id: str,
        name: str,
        transport: str,
        command: str = "",
        env: dict[str, str] | None = None,
        url: str = "",
        headers: dict[str, str] | None = None,
        enabled: bool = False,
        allowed_tools: builtins.list[str] | None = None,
        readonly: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
        description: str = "",
    ) -> tuple[McpServer, str]:
        """由 manifest 同步 MCP 設定；不覆蓋使用者手動建立的同名 server。

        若已存在且 id 相同：更新連線參數但保留 enabled 狀態與 last_probe。
        回傳 (server, action)，action 為 created | updated | unchanged。
        """
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
            old = self._servers.get(server_id)
            unchanged = (
                old
                and old.name == name
                and old.transport == transport
                and old.command == command.strip()
                and old.url == url.strip()
                and old.env == dict(env or {})
                and old.headers == dict(headers or {})
                and old.readonly == bool(readonly)
                and old.timeout == max(2.0, min(float(timeout or DEFAULT_TIMEOUT), 300.0))
                and (old.allowed_tools or []) == [str(t).strip() for t in (allowed_tools or []) if str(t).strip()]
            )
            if unchanged and old is not None:
                return old, "unchanged"
            srv = McpServer(
                id=server_id,
                name=name,
                transport=transport,
                command=command.strip(),
                env=dict(env or {}),
                url=url.strip(),
                headers=dict(headers or {}),
                enabled=old.enabled if old else bool(enabled),
                allowed_tools=[str(t).strip() for t in (allowed_tools or []) if str(t).strip()],
                readonly=bool(readonly),
                timeout=max(2.0, min(float(timeout or DEFAULT_TIMEOUT), 300.0)),
                created_at=old.created_at if old else now,
                updated_at=now,
                last_probe=old.last_probe if old else {},
            )
            action = "updated" if old else "created"
            self._servers[server_id] = srv
            self._save_locked()
            self._mounted = {m for m in self._mounted if not m.startswith(f"{server_id}::")}
            if description:
                logger.debug("MCP manifest %s: %s", server_id, description)
            return srv, action

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
        allowed_tools: builtins.list[str] | None = None,
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
        result = _compat.probe_server(snapshot)
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
        sess = _compat._make_session(snapshot)
        if isinstance(sess, _StdioSession):
            with sess as s:
                return s.call_tool(tool, args)
        return sess.call_tool(tool, args)

    # ── 動態掛載進 tool_registry ──

    def mount_tools(self, tool_registry: Any, *, force: bool = False) -> builtins.list[str]:
        """探測所有啟用 server，把其工具註冊進 tool_registry。

        回傳本次新增的內部工具名列表。已掛載的跳過（除非 force）。
        任何 server 探測失敗都只記警告，不影響其他 server。
        """
        mounted: builtins.list[str] = []
        for srv in self.list():
            if not srv.enabled:
                continue
            try:
                sess = _compat._make_session(srv)
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
