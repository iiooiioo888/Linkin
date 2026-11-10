"""工具呼叫的唯一入口。席位不得直連 OPC 或 Minecraft。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import Field

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel


class ToolErrorCode(str, Enum):
    invalid_schema = "invalid_schema"
    unknown_tool = "unknown_tool"
    timeout = "timeout"
    rate_limited = "rate_limited"
    guardrail_denied = "guardrail_denied"
    guardrail_confirm = "guardrail_confirm"
    upstream = "upstream"


class ToolInvokeRequest(ContractModel):
    args: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)
    seat_id: str | None = Field(default=None, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)
    timeout_ms: int = Field(default=30_000, ge=1, le=120_000)


class ToolInvokeResponse(ContractModel):
    ok: bool
    error_code: ToolErrorCode | None = None
    result: Any = None
    audit_event_id: str | None = None
