"""工具呼叫唯一入口：校驗、限流、護欄、路由與雙跑對比。"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import uuid
from collections import deque
from collections.abc import Callable
from typing import Any

from guardrail_service import check_decision as guardrail_check

from linkin_core.contracts.guardrail import GuardrailVerdict
from linkin_core.contracts.signatures import POLICY_VERSION, args_hash, is_sensitive

Adapter = Callable[[str, dict[str, Any], str], dict[str, Any]]
_WINDOW: dict[str, deque[float]] = {}
COMPARE: list[dict[str, Any]] = []
AUDITS: list[dict[str, Any]] = []


def reset_state() -> None:
    _WINDOW.clear()
    COMPARE.clear()
    AUDITS.clear()


def dual_mode() -> str:
    raw = os.getenv("TOOL_DUAL_RUN", "shadow").strip().lower()
    if raw in {"enabled", "shadow", "disabled"}:
        return raw
    return "shadow"


def sample_rate() -> float:
    try:
        return min(1.0, max(0.0, float(os.getenv("TOOL_DUAL_RUN_SAMPLE_RATE", "0.1"))))
    except ValueError:
        return 0.1


def should_sample(tool: str, rng: Callable[[], float] | None = None) -> bool:
    if is_sensitive(tool):
        return True
    roll = rng() if rng else random.random()
    return roll < sample_rate()


def execute_new_path(mode: str, tool: str = "") -> bool:
    """shadow／enabled 下敏感工具一律不執行適配器，只做護欄 dry-run。"""
    if tool and is_sensitive(tool) and mode in {"shadow", "enabled"}:
        return False
    if mode == "disabled":
        return True
    if mode == "enabled":
        return os.getenv("TOOL_DUAL_RUN_EXECUTE_NEW", "1") != "0"
    return os.getenv("TOOL_DUAL_RUN_EXECUTE_NEW", "0") == "1"


def _rate_ok(tenant_id: str) -> bool:
    limit = int(os.getenv("TOOL_GATEWAY_RATE_LIMIT", "60"))
    if limit <= 0:
        return True
    now = time.time()
    bucket = _WINDOW.setdefault(tenant_id, deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _valid_tool(tool: str) -> bool:
    if not tool or len(tool) > 64:
        return False
    return all(ch.isalnum() or ch in "._:-" for ch in tool)


def invoke(
    tool: str,
    args: dict[str, Any] | None,
    ctx: dict[str, Any],
    *,
    adapters: dict[str, Adapter],
    execute: bool = True,
) -> dict[str, Any]:
    """治理後路由。execute 為假時只做到決策，不打適配器。"""
    started = time.perf_counter()
    payload = dict(args or {})
    tenant_id = str(ctx.get("tenant_id") or "default")
    trace_id = str(ctx.get("trace_id") or uuid.uuid4().hex)
    if not _valid_tool(tool):
        return _done(tool, False, "invalid_schema", None, "", started, tenant_id)
    if not _rate_ok(tenant_id):
        return _done(tool, False, "rate_limited", None, "", started, tenant_id)
    decision = ""
    token = str(ctx.get("guardrail_token") or "")
    if is_sensitive(tool):
        row = guardrail_check(
            tool=tool,
            args=payload,
            tenant_id=tenant_id,
            trace_id=trace_id,
            caller="tool-gateway",
        )
        decision = row["verdict"]
        if decision == GuardrailVerdict.deny.value:
            return _done(tool, False, "guardrail_denied", None, decision, started, tenant_id, row["reason"])
        if decision == GuardrailVerdict.confirm.value and not token:
            return _done(
                tool,
                False,
                "guardrail_confirm",
                {"decision_id": row["decision_id"]},
                decision,
                started,
                tenant_id,
                row["reason"],
            )
        if decision == GuardrailVerdict.allow.value:
            token = row.get("token") or token
    if not execute:
        return _done(tool, True, None, {"dry_run": True, "args_hash": args_hash(payload)}, decision or "allow", started, tenant_id)
    try:
        result = _route(tool, payload, token, adapters)
    except Exception as exc:
        return _done(tool, False, "upstream", None, decision, started, tenant_id, str(exc)[:160])
    return _done(tool, True, None, result, decision or "allow", started, tenant_id)


def _route(tool: str, args: dict[str, Any], token: str, adapters: dict[str, Adapter]) -> dict[str, Any]:
    if tool in {"opc_read", "opc.read"}:
        return adapters["opc_read"](tool, args, "")
    if tool in {"opc_write", "opc.write"}:
        return adapters["opc_write"](tool, args, token)
    if tool in {"place_block", "pose_block", "break_block", "fill_block", "execute_command", "get_player", "get_online_players"}:
        return adapters["minecraft"](tool, args, token)
    return adapters["local"](tool, args, token)


def _done(
    tool: str,
    ok: bool,
    error_code: str | None,
    result: Any,
    decision: str,
    started: float,
    tenant_id: str,
    detail: str = "",
) -> dict[str, Any]:
    latency_ms = (time.perf_counter() - started) * 1000
    audit = {
        "event": "audit.event",
        "tool": tool,
        "ok": ok,
        "error_code": error_code or "",
        "decision": decision,
        "tenant_id": tenant_id,
        "latency_ms": round(latency_ms, 3),
        "policy_version": POLICY_VERSION,
        "detail": detail,
    }
    AUDITS.append(audit)
    return {
        "ok": ok,
        "error_code": error_code,
        "result": result,
        "decision": decision,
        "latency_ms": audit["latency_ms"],
        "detail": detail,
        "policy_version": POLICY_VERSION,
        "tenant_id": tenant_id,
        "tool": tool,
    }


def result_hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def record_compare(legacy: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    sensitive = is_sensitive(str(legacy.get("tool") or new.get("tool") or ""))
    same_hash = legacy.get("args_hash") == new.get("args_hash")
    same_decision = (legacy.get("decision") or "") == (new.get("decision") or "")
    same_result = legacy.get("result_hash") == new.get("result_hash")
    matched = same_hash and same_decision and same_result and legacy.get("error_code") == new.get("error_code")
    explainable = bool(
        sensitive
        and new.get("decision") == GuardrailVerdict.confirm.value
        and legacy.get("ok")
        and not new.get("ok")
    )
    row = {
        "tool": new.get("tool") or legacy.get("tool"),
        "tenant_id": new.get("tenant_id") or legacy.get("tenant_id") or "",
        "policy_version": POLICY_VERSION,
        "args_hash": new.get("args_hash") or legacy.get("args_hash"),
        "legacy_decision": legacy.get("decision"),
        "new_decision": new.get("decision"),
        "legacy_error": legacy.get("error_code") or "",
        "new_error": new.get("error_code") or "",
        "latency_ms": new.get("latency_ms") or 0,
        "match": matched,
        "explainable": explainable,
        "sensitive": sensitive,
    }
    COMPARE.append(row)
    return row


def alert_rows() -> list[dict[str, Any]]:
    mismatches = [row for row in COMPARE if not row["match"]]
    rate = (len(mismatches) / len(COMPARE)) if COMPARE else 0.0
    alerts = []
    for row in mismatches:
        if row["sensitive"] or rate > 0.001:
            item = dict(row)
            item["rate"] = rate
            alerts.append(item)
    return alerts
