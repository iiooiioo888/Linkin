"""公司任務受理。計畫生成可異步，受理本身只回 task_id。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel
from linkin_core.contracts.route import ExecutionPathName, ExecutionStrategyRequest


class TaskStatus(str, Enum):
    accepted = "accepted"
    planning = "planning"
    running = "running"
    awaiting_confirmation = "awaiting_confirmation"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class TaskCreateRequest(ExecutionStrategyRequest):
    query: str = Field(min_length=1, max_length=8000)
    tenant_id: str = Field(pattern=TENANT_ID)
    session_id: str | None = Field(default=None, max_length=64)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID)


class TaskAccepted(ContractModel):
    task_id: str = Field(min_length=1, max_length=64)
    status: TaskStatus = TaskStatus.accepted


class TaskView(ContractModel):
    task_id: str = Field(min_length=1, max_length=64)
    status: TaskStatus
    tenant_id: str = Field(pattern=TENANT_ID)
    path: ExecutionPathName | None = None
    detail: str = ""
