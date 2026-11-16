"""任務分析器審計日誌。

只保存已發生的事實，欄位固定為 tenant_id、actor_id、action、from_state、
to_state、rule_id、at。記錄只追加：沒有更新、刪除或清空。

這裡不是規則引擎，也不推動任何狀態機；from_state／to_state 只是變更前後的
文字快照。
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

_TOKEN_RE = re.compile(r"[A-Za-z0-9._@-]{1,96}")
_STATE_RE = re.compile(r"\S{1,200}")


def _token(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} 必須是字串")
    text = value.strip()
    if _TOKEN_RE.fullmatch(text) is None:
        raise ValueError(f"{field} 無效")
    return text


def _state(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} 必須是字串")
    text = value.strip()
    if _STATE_RE.fullmatch(text) is None:
        raise ValueError(f"{field} 無效")
    return text


def _aware_utc(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("at 必須是 datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("at 必須是有時區的 datetime")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """一筆不可變的審計記錄。"""

    tenant_id: str
    actor_id: str
    action: str
    from_state: str
    to_state: str
    rule_id: str
    at: datetime

    def __post_init__(self) -> None:
        tenant_id = _token(self.tenant_id, "tenant_id")
        actor_id = _token(self.actor_id, "actor_id")
        action = _token(self.action, "action")
        from_state = _state(self.from_state, "from_state")
        to_state = _state(self.to_state, "to_state")
        rule_id = _token(self.rule_id, "rule_id")
        at = _aware_utc(self.at)
        object.__setattr__(self, "tenant_id", tenant_id)
        object.__setattr__(self, "actor_id", actor_id)
        object.__setattr__(self, "action", action)
        object.__setattr__(self, "from_state", from_state)
        object.__setattr__(self, "to_state", to_state)
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "at", at)

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "actor_id": self.actor_id,
            "action": self.action,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "rule_id": self.rule_id,
            "at": self.at.isoformat(),
        }


class AuditLogError(RuntimeError):
    """試圖改寫或刪除審計記錄。"""


class AuditLog:
    """只追加的審計日誌。

    ``append``／``append_many`` 是唯一寫入路徑。``append_many`` 先驗證整批，
    任一筆不合法就整批不寫。``read`` 只回傳指定租戶的快照。
    """

    __slots__ = ("_events", "_lock")

    _events: tuple[AuditEvent, ...]
    _lock: threading.Lock

    def __init__(self) -> None:
        object.__setattr__(self, "_events", ())
        object.__setattr__(self, "_lock", threading.Lock())

    def __setattr__(self, name: str, value: object) -> None:
        raise AuditLogError("審計記錄只允許追加")

    def __delattr__(self, name: str) -> None:
        raise AuditLogError("審計記錄只允許追加")

    def append(self, event: AuditEvent) -> AuditEvent:
        self.append_many((event,))
        return event

    def append_many(self, events: Iterable[AuditEvent]) -> None:
        if isinstance(events, (str, bytes, AuditEvent)):
            raise TypeError("events 必須是審計事件的可迭代物件")
        pending = tuple(events)
        for event in pending:
            if type(event) is not AuditEvent:
                raise TypeError("審計事件必須是 AuditEvent")
        if not pending:
            return
        with self._lock:
            object.__setattr__(self, "_events", self._events + pending)

    def read(self, tenant_id: str) -> tuple[AuditEvent, ...]:
        tenant = _token(tenant_id, "tenant_id")
        with self._lock:
            events = self._events
        return tuple(event for event in events if event.tenant_id == tenant)
