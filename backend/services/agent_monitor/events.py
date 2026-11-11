"""角色事件解析：payload／名稱／時間戳、角色歸屬、壓縮與寫入。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.services.task_manager import TaskRecord

from .common import PHASE_ROLE, ROLE_EVENT_HINTS, _role_id


def _event_payload(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        data = event.get("data")
        if isinstance(data, dict):
            merged = {**event, **data}
            merged.pop("data", None)
            return merged
        return dict(event)
    return {}


def _event_name(payload: dict[str, Any]) -> str:
    return str(payload.get("event") or "")


def _event_ts(payload: dict[str, Any], fallback: float | str | None = None) -> str | None:
    ts = payload.get("ts") or payload.get("timestamp") or fallback
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    text = str(ts)
    return text or None


def _roles_for_event(payload: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    assignee = _role_id(payload.get("assignee"))
    if assignee:
        roles.add(assignee)
    name = _event_name(payload)
    for role, events in ROLE_EVENT_HINTS.items():
        if name in events:
            roles.add(role)
    phase = str(payload.get("phase") or "")
    if name in {"phase", "phase_change"} and phase in PHASE_ROLE:
        roles.add(PHASE_ROLE[phase])
    return roles


def _compact_event(payload: dict[str, Any], task: TaskRecord | None = None) -> dict[str, Any]:
    return {
        "ts": _event_ts(payload, task.created_at if task else None),
        "event": _event_name(payload),
        "item_id": payload.get("item_id"),
        "title": payload.get("title") or payload.get("goal") or payload.get("phase") or "",
        "assignee": _role_id(payload.get("assignee")),
        "task_id": (task.task_id if task else None) or payload.get("run_id") or payload.get("task_id"),
        "cost_usd": float(payload.get("cost") or payload.get("cost_usd") or 0),
        "score": payload.get("score"),
        "degraded": bool(payload.get("degraded")),
        "duration_ms": payload.get("duration_ms") or payload.get("latency_ms"),
        "model": payload.get("model") or payload.get("model_name") or "",
        "tokens_in": payload.get("prompt_tokens") or payload.get("tokens_in") or 0,
        "tokens_out": payload.get("completion_tokens") or payload.get("tokens_out") or 0,
    }


def _append_event(bucket: dict[str, Any], payload: dict[str, Any], task: TaskRecord | None = None) -> None:
    compact = _compact_event(payload, task)
    key = (
        compact["ts"],
        compact["event"],
        compact["item_id"],
        compact["task_id"],
    )
    existing = {(e.get("ts"), e.get("event"), e.get("item_id"), e.get("task_id")) for e in bucket["events"]}
    if key in existing:
        return
    bucket["events"].append(compact)
    ts = compact["ts"]
    if ts and (not bucket["last_activity_at"] or str(ts) > str(bucket["last_activity_at"])):
        bucket["last_activity_at"] = ts
    cost = float(compact.get("cost_usd") or 0)
    if cost:
        bucket["cost_usd"] = round(float(bucket["cost_usd"]) + cost, 6)
