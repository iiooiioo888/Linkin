"""對話 SSE。simple 路徑的反思在這條回應裡同步結束。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel
from linkin_core.contracts.route import CompatibleStrategy, RouteDecision


class SseEventName(str, Enum):
    route = "route"
    token = "token"
    done = "done"
    error = "error"


class ChatStreamRequest(ContractModel):
    query: str = Field(min_length=1, max_length=8000)
    strategy: CompatibleStrategy = CompatibleStrategy.auto
    tenant_id: str = Field(pattern=TENANT_ID)
    session_id: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID)


class ChatSseEvent(ContractModel):
    event: SseEventName
    route: RouteDecision | None = None
    delta: str = ""
    detail: str = ""
