"""異步事件。每則都帶 schema_version、trace_id、tenant_id。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from linkin_core.contracts.common import ContractModel, TraceContext
from linkin_core.contracts.guardrail import GuardrailVerdict


class EventName(str, Enum):
    seat_task_created = "seat.task.created"
    seat_task_completed = "seat.task.completed"
    reflection_requested = "reflection.requested"
    guardrail_decision = "guardrail.decision"
    audit_event = "audit.event"
    opc_write_requested = "opc.write.requested"


class SeatTaskCreatedEvent(TraceContext):
    event: EventName = EventName.seat_task_created
    occurred_at: str = Field(min_length=20, max_length=40)
    task_id: str
    seat_id: str
    work_item_id: str
    idempotency_key: str = Field(min_length=8, max_length=128)


class SeatTaskCompletedEvent(TraceContext):
    event: EventName = EventName.seat_task_completed
    occurred_at: str = Field(min_length=20, max_length=40)
    task_id: str
    seat_id: str
    work_item_id: str
    ok: bool
    detail: str = ""


class ReflectionRequestedEvent(TraceContext):
    event: EventName = EventName.reflection_requested
    occurred_at: str = Field(min_length=20, max_length=40)
    task_id: str
    sync: bool = False


class GuardrailDecisionEvent(TraceContext):
    event: EventName = EventName.guardrail_decision
    occurred_at: str = Field(min_length=20, max_length=40)
    decision_id: str
    verdict: GuardrailVerdict
    policy_version: str


class AuditEvent(TraceContext):
    event: EventName = EventName.audit_event
    occurred_at: str = Field(min_length=20, max_length=40)
    action: str
    object_key: str = ""


class OpcWriteRequestedEvent(TraceContext):
    event: EventName = EventName.opc_write_requested
    occurred_at: str = Field(min_length=20, max_length=40)
    request_id: str
    node_id: str
    guardrail_decision_id: str


EVENT_MODELS: dict[EventName, type[ContractModel]] = {
    EventName.seat_task_created: SeatTaskCreatedEvent,
    EventName.seat_task_completed: SeatTaskCompletedEvent,
    EventName.reflection_requested: ReflectionRequestedEvent,
    EventName.guardrail_decision: GuardrailDecisionEvent,
    EventName.audit_event: AuditEvent,
    EventName.opc_write_requested: OpcWriteRequestedEvent,
}
