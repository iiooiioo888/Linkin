"""單體裡的工具入口。預設 shadow：回舊結果，並抽樣記錄新路徑。"""

from __future__ import annotations

import sys
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import Any

legacy_only: ContextVar[bool] = ContextVar("tool_legacy_only", default=False)


def _bootstrap() -> None:
    root = Path(__file__).resolve().parents[2]
    for rel in ("services/guardrail-service", "services/tool-gateway"):
        path = str(root / rel)
        if path not in sys.path:
            sys.path.insert(0, path)


def _ctx(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    from linkin_core.contracts.version import SCHEMA_VERSION

    base = {"tenant_id": "default", "trace_id": uuid.uuid4().hex, "schema_version": SCHEMA_VERSION}
    if extra:
        base.update(extra)
    return base


def _adapters(registry: Any, request: Any, role: str | None, catalog_allowed: list[str] | None) -> dict[str, Any]:
    from linkin_core.contracts.signatures import is_sensitive

    def local(tool: str, args: dict[str, Any], _token: str) -> dict[str, Any]:
        token = legacy_only.set(True)
        try:
            outcome = registry.execute(request, role, catalog_allowed=catalog_allowed)
        finally:
            legacy_only.reset(token)
        return {"ok": outcome.success, "result": outcome.result, "error": outcome.error, "tool": tool, "args": args}

    def minecraft(tool: str, args: dict[str, Any], token: str) -> dict[str, Any]:
        from backend.linkin.minecraft import execute_named_tool

        if is_sensitive(tool) and not token:
            return {"ok": False, "error": "缺少護欄簽章"}
        result = execute_named_tool(tool, args)
        return {"ok": bool(result.get("ok", True)), "result": result, "tool": tool}

    def opc_read(tool: str, args: dict[str, Any], _token: str) -> dict[str, Any]:
        return {"ok": True, "tool": tool, "result": {"node_ids": args.get("node_ids") or []}}

    def opc_write(tool: str, args: dict[str, Any], token: str) -> dict[str, Any]:
        if not token:
            return {"ok": False, "error": "缺少護欄簽章", "tool": tool}
        return {"ok": True, "tool": tool, "result": {"accepted": True}}

    return {"local": local, "minecraft": minecraft, "opc_read": opc_read, "opc_write": opc_write}


def invoke_registered(registry: Any, request: Any, role: str | None, catalog_allowed: list[str] | None) -> Any:
    from backend.company.tools import ToolCallResult
    from linkin_core.contracts.signatures import args_hash

    _bootstrap()
    from tool_gateway import (
        dual_mode,
        execute_new_path,
        invoke,
        record_compare,
        result_hash,
        should_sample,
    )

    mode = dual_mode()
    tool = request.tool
    args = dict(request.args or {})

    def legacy() -> Any:
        token = legacy_only.set(True)
        try:
            return registry.execute(request, role, catalog_allowed=catalog_allowed)
        finally:
            legacy_only.reset(token)

    if mode == "disabled":
        new = invoke(tool, args, _ctx(), adapters=_adapters(registry, request, role, catalog_allowed), execute=True)
        if new["ok"]:
            return ToolCallResult(tool=tool, success=True, result=new.get("result"))
        return ToolCallResult(tool=tool, success=False, error=new.get("detail") or new.get("error_code") or "工具失敗")

    old = legacy()
    if mode == "shadow" and not should_sample(tool):
        return old
    try:
        new = invoke(
            tool,
            args,
            _ctx(),
            adapters=_adapters(registry, request, role, catalog_allowed),
            execute=execute_new_path(mode),
        )
    except Exception as exc:
        new = {
            "ok": False,
            "error_code": "upstream",
            "decision": "",
            "result": None,
            "latency_ms": 0,
            "detail": str(exc)[:160],
            "tool": tool,
            "tenant_id": "default",
        }
    record_compare(
        {
            "tool": tool,
            "ok": old.success,
            "error_code": "" if old.success else "legacy",
            "decision": "allow" if old.success else "deny",
            "args_hash": args_hash(args),
            "result_hash": result_hash(old.result if old.success else old.error),
            "tenant_id": "default",
        },
        {
            "tool": tool,
            "ok": new["ok"],
            "error_code": new.get("error_code") or "",
            "decision": new.get("decision") or "",
            "args_hash": args_hash(args),
            "result_hash": result_hash(new.get("result")),
            "tenant_id": "default",
            "latency_ms": new.get("latency_ms") or 0,
        },
    )
    return old


async def sense_opc_for_context(state: dict[str, Any]) -> dict[str, Any]:
    """OPC 讀數走 tool-gateway 的新路徑；shadow 仍回傳舊的 sense_opc 結果。"""
    from linkin_core.contracts.signatures import args_hash
    from opc_service.sense import sense_opc

    _bootstrap()
    from tool_gateway import (
        dual_mode,
        execute_new_path,
        invoke,
        record_compare,
        result_hash,
        should_sample,
    )

    legacy = await sense_opc(dict(state))
    mode = dual_mode()
    if mode == "disabled":
        invoke(
            "opc_read",
            {"node_ids": list((legacy.get("opc_readings") or {}).keys())},
            _ctx(),
            adapters=_read_adapters(legacy),
            execute=True,
        )
        return legacy
    if mode == "shadow" and not should_sample("opc_read"):
        return legacy
    try:
        new = invoke(
            "opc_read",
            {"node_ids": list((legacy.get("opc_readings") or {}).keys())},
            _ctx(),
            adapters=_read_adapters(legacy),
            execute=execute_new_path(mode),
        )
    except Exception as exc:
        new = {
            "ok": False,
            "error_code": "upstream",
            "decision": "",
            "result": None,
            "latency_ms": 0,
            "detail": str(exc)[:160],
            "tool": "opc_read",
            "tenant_id": "default",
        }
    record_compare(
        {
            "tool": "opc_read",
            "ok": True,
            "decision": "allow",
            "args_hash": args_hash({"status": legacy.get("opc_status")}),
            "result_hash": result_hash(legacy.get("opc_readings")),
            "error_code": "",
            "tenant_id": "default",
        },
        {
            "tool": "opc_read",
            "ok": new["ok"],
            "decision": new.get("decision") or "",
            "args_hash": args_hash({"status": legacy.get("opc_status")}),
            "result_hash": result_hash(new.get("result")),
            "error_code": new.get("error_code") or "",
            "tenant_id": "default",
            "latency_ms": new.get("latency_ms") or 0,
        },
    )
    return legacy


def _read_adapters(legacy: dict[str, Any]) -> dict[str, Any]:
    def opc_read(tool: str, args: dict[str, Any], _token: str) -> dict[str, Any]:
        return {"ok": True, "tool": tool, "result": legacy.get("opc_readings") or {}, "args": args}

    def reject(tool: str, args: dict[str, Any], _token: str) -> dict[str, Any]:
        return {"ok": False, "tool": tool, "error": "讀取鏈不呼叫寫入", "args": args}

    return {"opc_read": opc_read, "opc_write": reject, "minecraft": reject, "local": reject}
