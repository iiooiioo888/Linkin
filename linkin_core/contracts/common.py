"""跨服務共用欄位。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from linkin_core.contracts.version import SCHEMA_VERSION

TENANT_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
TRACE_ID = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TraceContext(ContractModel):
    schema_version: str = SCHEMA_VERSION
    trace_id: str = Field(pattern=TRACE_ID)
    tenant_id: str = Field(pattern=TENANT_ID)


class ErrorBody(ContractModel):
    error_code: str = Field(min_length=1, max_length=64)
    detail: str = Field(min_length=1, max_length=500)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID)
