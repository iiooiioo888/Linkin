"""護欄與審批。OPC 寫入與危險 Minecraft 動作都在這裡做決定。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel, TraceContext


class GuardrailSubject(str, Enum):
    opc_write = "opc.write"
    minecraft_action = "minecraft.action"
    tool_invoke = "tool.invoke"


class GuardrailVerdict(str, Enum):
    allow = "allow"
    deny = "deny"
    confirm = "confirm"


class GuardrailCheckRequest(ContractModel):
    subject: GuardrailSubject
    action: str = Field(min_length=1, max_length=64)
    target: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)
    actor: str | None = Field(default=None, max_length=64)


class GuardrailDecision(TraceContext):
    decision_id: str = Field(min_length=1, max_length=64)
    verdict: GuardrailVerdict
    reason: str = Field(min_length=1, max_length=300)
    policy_version: str = Field(min_length=1, max_length=32)


class GuardrailApproveRequest(ContractModel):
    decision_id: str = Field(min_length=1, max_length=64)
    approved: bool
    approver: str = Field(min_length=1, max_length=64)
    note: str = Field(default="", max_length=300)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)
