"""OPC 讀寫。寫入請求必須帶已放行的 guardrail 決策。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel


class OpcReadRequest(ContractModel):
    node_ids: list[str] = Field(min_length=1, max_length=64)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)


class OpcReading(ContractModel):
    node_id: str = Field(min_length=1, max_length=256)
    value: Any = None
    quality: str = "good"


class OpcReadResponse(ContractModel):
    readings: list[OpcReading]
    degraded: bool = False


class OpcWriteRequest(ContractModel):
    node_id: str = Field(min_length=1, max_length=256)
    value: Any
    guardrail_decision_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)


class OpcWriteAccepted(ContractModel):
    request_id: str = Field(min_length=1, max_length=64)
    status: Literal["accepted"] = "accepted"
