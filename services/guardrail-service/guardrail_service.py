"""護欄服務。OPC 寫入與危險 Minecraft 動作在這裡做決定，並簽發 HMAC。"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from linkin_core.contracts.guardrail import GuardrailVerdict
from linkin_core.contracts.minecraft import MUTATING_MINECRAFT_ACTIONS
from linkin_core.contracts.signatures import (
    POLICY_VERSION,
    SCHEMA_VERSION,
    args_hash,
    is_sensitive,
    issue_token,
    signing_key,
)

CALLER_CHECK = "tool-gateway"
CALLER_APPROVE = "api-gateway"
_DESTRUCTIVE_RE = re.compile(r"\b(ban|kick|op|deop|stop|restart|whitelist)\b", re.IGNORECASE)
_TEMP_CEILING = 150.0

def evaluate(tool: str, args: dict[str, Any]) -> tuple[str, str]:
    """回傳 (verdict, reason)。confirm 即需要人工審批。"""
    if tool in {"opc_write", "opc.write"}:
        tag = str(args.get("node_id") or args.get("tag_name") or "")
        value = args.get("value")
        if isinstance(value, (int, float)) and "temp" in tag.lower() and not 0 <= float(value) <= _TEMP_CEILING:
            return GuardrailVerdict.deny.value, "超出溫度邊界"
        return GuardrailVerdict.confirm.value, "OPC 寫入需要人工審批"
    if tool == "execute_command":
        command = str(args.get("command") or "")
        if _DESTRUCTIVE_RE.search(command):
            return GuardrailVerdict.deny.value, "靈境鐵律拒絕危險指令"
        return GuardrailVerdict.confirm.value, "指令需要人工審批"
    if tool in MUTATING_MINECRAFT_ACTIONS:
        return GuardrailVerdict.confirm.value, "危險 Minecraft 動作需要人工審批"
    return GuardrailVerdict.allow.value, "非敏感工具"


class DecisionStore:
    """審批狀態。未設定資料庫時留在記憶體；正式環境寫 Postgres。"""

    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}

    def save(self, row: dict[str, Any]) -> dict[str, Any]:
        self.rows[row["decision_id"]] = row
        return row

    def get(self, decision_id: str) -> dict[str, Any] | None:
        return self.rows.get(decision_id)


STORE = DecisionStore()
EVENTS: list[dict[str, Any]] = []


def reset_state() -> None:
    STORE.rows.clear()
    EVENTS.clear()


def _event(name: str, row: dict[str, Any]) -> None:
    EVENTS.append(
        {
            "event": name,
            "schema_version": SCHEMA_VERSION,
            "trace_id": row["trace_id"],
            "tenant_id": row["tenant_id"],
            "decision_id": row["decision_id"],
            "verdict": row["verdict"],
            "policy_version": POLICY_VERSION,
        }
    )


def check_decision(
    *,
    tool: str,
    args: dict[str, Any],
    tenant_id: str,
    trace_id: str,
    caller: str,
) -> dict[str, Any]:
    if caller != CALLER_CHECK:
        raise PermissionError("只有 tool-gateway 可以呼叫 check")
    verdict, reason = evaluate(tool, args)
    if is_sensitive(tool):
        try:
            signing_key()
        except RuntimeError:
            verdict, reason = GuardrailVerdict.deny.value, "簽章金鑰未設定"
    decision_id = "gd_" + uuid.uuid4().hex[:12]
    token = ""
    if verdict == GuardrailVerdict.allow.value and is_sensitive(tool):
        token = issue_token(_claims(decision_id, tool, args, tenant_id, trace_id))
    row = {
        "decision_id": decision_id,
        "tool": tool,
        "args_hash": args_hash(args),
        "verdict": verdict,
        "reason": reason,
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "policy_version": POLICY_VERSION,
        "token": token,
    }
    STORE.save(row)
    _event("guardrail.decision", row)
    return row


def approve_decision(
    *,
    decision_id: str,
    approved: bool,
    approver: str,
    tenant_id: str,
    trace_id: str,
    caller: str,
) -> dict[str, Any]:
    if caller != CALLER_APPROVE:
        raise PermissionError("審批入口只接受 api-gateway")
    row = STORE.get(decision_id)
    if row is None or row["tenant_id"] != tenant_id:
        raise KeyError("找不到決策")
    # 已審批過：回傳新簽章決策，勿把 confirm id 當執行憑證
    superseded = row.get("superseded_by")
    if superseded:
        newer = STORE.get(superseded)
        if newer is not None:
            return newer
    if row["verdict"] == GuardrailVerdict.allow.value and row.get("token"):
        return row
    if not approved:
        row["verdict"] = GuardrailVerdict.deny.value
        row["reason"] = "人工拒絕"
        row["token"] = ""
        row["trace_id"] = trace_id
        STORE.save(row)
        _event("guardrail.decision", row)
        return row

    # 審批通過：發新 decision_id 再簽章，不可複用 check 的 confirm
    old_id = decision_id
    new_id = "gd_" + uuid.uuid4().hex[:12]
    new_row = {
        "decision_id": new_id,
        "prior_decision_id": old_id,
        "tool": row["tool"],
        "args_hash": row["args_hash"],
        "verdict": GuardrailVerdict.allow.value,
        "reason": f"{approver} 已放行",
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "policy_version": POLICY_VERSION,
        "token": "",
    }
    new_row["token"] = issue_token(
        _claims(new_id, row["tool"], {"args_hash": row["args_hash"]}, tenant_id, trace_id, hashed=True)
    )
    marked = dict(row)
    marked["superseded_by"] = new_id
    marked["token"] = ""
    STORE.save(marked)
    STORE.save(new_row)
    _event("guardrail.decision", new_row)
    return new_row


def _claims(
    decision_id: str,
    tool: str,
    args: dict[str, Any],
    tenant_id: str,
    trace_id: str,
    *,
    hashed: bool = False,
) -> dict[str, Any]:
    from linkin_core.contracts.signatures import key_id, new_nonce

    return {
        "decision_id": decision_id,
        "verdict": GuardrailVerdict.allow.value,
        "policy_version": POLICY_VERSION,
        "tenant_id": tenant_id,
        "trace_id": trace_id,
        "tool": tool,
        "args_hash": args["args_hash"] if hashed else args_hash(args),
        "exp": int(time.time()) + 600,
        "schema_version": SCHEMA_VERSION,
        "kid": key_id(),
        "nonce": new_nonce(),
    }
