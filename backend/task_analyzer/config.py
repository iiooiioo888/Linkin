"""任務分析器設定。

預設值：

- max_question_rounds = 3
- max_questions_per_round = 5
- question_timeout_hours = 24
- discovery_timeout_sec = 60
- budget_sensitivity_threshold = 0.2
- redline_unknown_policy = ask_user
- default_priority = P2
- report_schema_version = v0.1

租戶以 tenant_id 覆蓋上述欄位。每次實際變更寫一筆審計，rule_id 是欄位名。
report_schema_version 只是版本戳記，不註冊、不載入 Schema。

本模組不含規則引擎與狀態機。寫入設定前先過授權矩陣；跨租戶拒絕且不留審計。
"""

from __future__ import annotations

import math
import re
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType

from backend.task_analyzer.audit import AuditEvent, AuditLog
from backend.task_analyzer.authz import (
    Action,
    Actor,
    AuthzDecision,
    Resource,
    authorize,
    permission_message,
)

_SCHEMA_VERSION_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)$")

CONFIG_UPDATE_ACTION = "config.update"
CONFIG_FIELDS: tuple[str, ...] = (
    "max_question_rounds",
    "max_questions_per_round",
    "question_timeout_hours",
    "discovery_timeout_sec",
    "budget_sensitivity_threshold",
    "redline_unknown_policy",
    "default_priority",
    "report_schema_version",
)

_MIN_QUESTION_ROUNDS = 0
_MAX_QUESTION_ROUNDS = 10_000
_MIN_QUESTIONS_PER_ROUND = 0
_MAX_QUESTIONS_PER_ROUND = 10_000
_MIN_QUESTION_TIMEOUT_HOURS = 1
_MAX_QUESTION_TIMEOUT_HOURS = 366 * 24
_MIN_DISCOVERY_TIMEOUT_SEC = 1
_MAX_DISCOVERY_TIMEOUT_SEC = 24 * 60 * 60


class ConfigError(ValueError):
    """設定值不合法，或這次呼叫沒有可套用的變更內容。"""


class RedlineUnknownPolicy(str, Enum):
    ASK_USER = "ask_user"
    DENY = "deny"
    ALLOW = "allow"


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


def _as_int(value: object, name: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{name} 必須是整數")
    if value < low or value > high:
        raise ConfigError(f"{name} 必須介於 {low} 與 {high}")
    return value


def _as_rounds(value: object) -> int:
    return _as_int(value, "max_question_rounds", _MIN_QUESTION_ROUNDS, _MAX_QUESTION_ROUNDS)


def _as_questions(value: object) -> int:
    return _as_int(
        value,
        "max_questions_per_round",
        _MIN_QUESTIONS_PER_ROUND,
        _MAX_QUESTIONS_PER_ROUND,
    )


def _as_hours(value: object) -> int:
    return _as_int(
        value,
        "question_timeout_hours",
        _MIN_QUESTION_TIMEOUT_HOURS,
        _MAX_QUESTION_TIMEOUT_HOURS,
    )


def _as_discovery(value: object) -> int:
    return _as_int(
        value,
        "discovery_timeout_sec",
        _MIN_DISCOVERY_TIMEOUT_SEC,
        _MAX_DISCOVERY_TIMEOUT_SEC,
    )


def _as_threshold(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("budget_sensitivity_threshold 必須是 0 到 1 的數值")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise ConfigError("budget_sensitivity_threshold 必須介於 0 與 1")
    if number == 0.0:
        return 0.0
    return float(format(number, ".12g"))


def _as_policy(value: object) -> RedlineUnknownPolicy:
    if isinstance(value, RedlineUnknownPolicy):
        return value
    if isinstance(value, str):
        try:
            return RedlineUnknownPolicy(value.strip())
        except ValueError:
            pass
    raise ConfigError("redline_unknown_policy 必須是 ask_user、deny 或 allow")


def _as_priority(value: object) -> Priority:
    if isinstance(value, Priority):
        return value
    if isinstance(value, str):
        try:
            return Priority(value.strip())
        except ValueError:
            pass
    raise ConfigError("default_priority 必須是 P0、P1、P2 或 P3")


def _as_schema_version(value: object) -> str:
    if not isinstance(value, str) or _SCHEMA_VERSION_RE.fullmatch(value.strip()) is None:
        raise ConfigError("report_schema_version 必須是 v主版.次版，例如 v0.1")
    return value.strip()


def _canonical(value: object) -> str:
    if isinstance(value, (RedlineUnknownPolicy, Priority)):
        return str(value.value)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigError("無法正規化設定值")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ConfigError("無法正規化設定值")
        return format(value, ".12g")
    return str(value)


def _coerce(field: str, value: object) -> int | float | str | RedlineUnknownPolicy | Priority:
    if field == "max_question_rounds":
        return _as_rounds(value)
    if field == "max_questions_per_round":
        return _as_questions(value)
    if field == "question_timeout_hours":
        return _as_hours(value)
    if field == "discovery_timeout_sec":
        return _as_discovery(value)
    if field == "budget_sensitivity_threshold":
        return _as_threshold(value)
    if field == "redline_unknown_policy":
        return _as_policy(value)
    if field == "default_priority":
        return _as_priority(value)
    if field == "report_schema_version":
        return _as_schema_version(value)
    raise ConfigError(f"未知設定鍵：{field!r}")


@dataclass(frozen=True, slots=True)
class TaskAnalyzerConfig:
    """一份已驗證的有效設定。欄位缺省即為產品預設。"""

    max_question_rounds: int = 3
    max_questions_per_round: int = 5
    question_timeout_hours: int = 24
    discovery_timeout_sec: int = 60
    budget_sensitivity_threshold: float = 0.2
    redline_unknown_policy: RedlineUnknownPolicy = RedlineUnknownPolicy.ASK_USER
    default_priority: Priority = Priority.P2
    report_schema_version: str = "v0.1"

    def __post_init__(self) -> None:
        rounds = _as_rounds(self.max_question_rounds)
        questions = _as_questions(self.max_questions_per_round)
        hours = _as_hours(self.question_timeout_hours)
        discovery = _as_discovery(self.discovery_timeout_sec)
        threshold = _as_threshold(self.budget_sensitivity_threshold)
        policy = _as_policy(self.redline_unknown_policy)
        priority = _as_priority(self.default_priority)
        schema_version = _as_schema_version(self.report_schema_version)
        object.__setattr__(self, "max_question_rounds", rounds)
        object.__setattr__(self, "max_questions_per_round", questions)
        object.__setattr__(self, "question_timeout_hours", hours)
        object.__setattr__(self, "discovery_timeout_sec", discovery)
        object.__setattr__(self, "budget_sensitivity_threshold", threshold)
        object.__setattr__(self, "redline_unknown_policy", policy)
        object.__setattr__(self, "default_priority", priority)
        object.__setattr__(self, "report_schema_version", schema_version)

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "max_question_rounds": self.max_question_rounds,
            "max_questions_per_round": self.max_questions_per_round,
            "question_timeout_hours": self.question_timeout_hours,
            "discovery_timeout_sec": self.discovery_timeout_sec,
            "budget_sensitivity_threshold": self.budget_sensitivity_threshold,
            "redline_unknown_policy": self.redline_unknown_policy.value,
            "default_priority": self.default_priority.value,
            "report_schema_version": self.report_schema_version,
        }


def default_config() -> TaskAnalyzerConfig:
    return TaskAnalyzerConfig()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize(changes: Mapping[str, object]) -> dict[str, object]:
    unknown = [repr(key) for key in changes if not isinstance(key, str) or key not in CONFIG_FIELDS]
    if unknown:
        raise ConfigError("未知設定鍵：" + "、".join(unknown))
    return {field: _coerce(field, changes[field]) for field in CONFIG_FIELDS if field in changes}


def _public_override(value: object) -> int | float | str:
    if isinstance(value, (RedlineUnknownPolicy, Priority)):
        return str(value.value)
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigError("覆寫值損壞")
    return value


class ConfigStore:
    """依 tenant_id 保存覆寫。只有授權通過的變更會寫入並產生審計。"""

    __slots__ = ("_audit", "_clock", "_lock", "_overrides")

    _audit: AuditLog
    _clock: Callable[[], datetime]
    _lock: threading.Lock
    _overrides: Mapping[str, Mapping[str, object]]

    def __init__(
        self,
        audit: AuditLog | None = None,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if audit is not None and not isinstance(audit, AuditLog):
            raise TypeError("audit 必須是 AuditLog")
        object.__setattr__(self, "_audit", audit if audit is not None else AuditLog())
        object.__setattr__(self, "_clock", clock if clock is not None else _utc_now)
        object.__setattr__(self, "_lock", threading.Lock())
        object.__setattr__(self, "_overrides", MappingProxyType({}))

    def __setattr__(self, name: str, value: object) -> None:
        raise ConfigError("設定只能經由 update 或 reset 變更")

    def __delattr__(self, name: str) -> None:
        raise ConfigError("設定只能經由 update 或 reset 變更")

    def get(self, actor: Actor, *, tenant_id: str | None = None) -> TaskAnalyzerConfig:
        target = self._target(actor, tenant_id)
        _enforce(
            authorize(actor, tenant_id=target, resource=Resource.CONFIG, action=Action.READ)
        )
        with self._lock:
            return self._materialize(target)

    def overrides(
        self,
        actor: Actor,
        *,
        tenant_id: str | None = None,
    ) -> dict[str, int | float | str]:
        target = self._target(actor, tenant_id)
        _enforce(
            authorize(actor, tenant_id=target, resource=Resource.CONFIG, action=Action.READ)
        )
        with self._lock:
            stored = dict(self._overrides.get(target, {}))
        return {
            field: _public_override(stored[field])
            for field in CONFIG_FIELDS
            if field in stored
        }

    def update(
        self,
        actor: Actor,
        changes: Mapping[str, object],
        *,
        tenant_id: str | None = None,
    ) -> TaskAnalyzerConfig:
        if isinstance(changes, (str, bytes)) or not isinstance(changes, Mapping):
            raise TypeError("changes 必須是對應表")
        target = self._target(actor, tenant_id)
        _enforce(
            authorize(actor, tenant_id=target, resource=Resource.CONFIG, action=Action.UPDATE)
        )
        if len(changes) == 0:
            raise ConfigError("變更不可為空")
        normalized = _normalize(changes)
        with self._lock:
            return self._apply(actor, target, normalized)

    def reset(
        self,
        actor: Actor,
        keys: Iterable[str],
        *,
        tenant_id: str | None = None,
    ) -> TaskAnalyzerConfig:
        if isinstance(keys, (str, bytes)) or not isinstance(keys, Iterable):
            raise TypeError("keys 必須是欄位名稱的可迭代物件")
        target = self._target(actor, tenant_id)
        _enforce(
            authorize(actor, tenant_id=target, resource=Resource.CONFIG, action=Action.UPDATE)
        )
        fields = tuple(keys)
        if not fields:
            raise ConfigError("重設鍵不可為空")
        defaults = default_config()
        changes: dict[str, object] = {}
        for field in fields:
            if field not in CONFIG_FIELDS:
                raise ConfigError(f"未知設定鍵：{field!r}")
            changes[field] = getattr(defaults, field)
        return self.update(actor, changes, tenant_id=tenant_id)

    def read_audit(
        self,
        actor: Actor,
        *,
        tenant_id: str | None = None,
    ) -> tuple[AuditEvent, ...]:
        target = self._target(actor, tenant_id)
        _enforce(
            authorize(actor, tenant_id=target, resource=Resource.AUDIT, action=Action.READ)
        )
        with self._lock:
            return self._audit.read(target)

    def _target(self, actor: Actor, tenant_id: str | None) -> str:
        if not isinstance(actor, Actor):
            raise TypeError("actor 必須是 Actor")
        if tenant_id is None:
            return actor.tenant_id
        if not isinstance(tenant_id, str):
            raise TypeError("tenant_id 必須是字串")
        return tenant_id.strip()

    def _materialize(self, tenant_id: str) -> TaskAnalyzerConfig:
        base = default_config()
        overlay = self._overrides.get(tenant_id, {})
        if not overlay:
            return base
        return TaskAnalyzerConfig(
            max_question_rounds=_as_rounds(
                overlay.get("max_question_rounds", base.max_question_rounds)
            ),
            max_questions_per_round=_as_questions(
                overlay.get("max_questions_per_round", base.max_questions_per_round)
            ),
            question_timeout_hours=_as_hours(
                overlay.get("question_timeout_hours", base.question_timeout_hours)
            ),
            discovery_timeout_sec=_as_discovery(
                overlay.get("discovery_timeout_sec", base.discovery_timeout_sec)
            ),
            budget_sensitivity_threshold=_as_threshold(
                overlay.get("budget_sensitivity_threshold", base.budget_sensitivity_threshold)
            ),
            redline_unknown_policy=_as_policy(
                overlay.get("redline_unknown_policy", base.redline_unknown_policy)
            ),
            default_priority=_as_priority(overlay.get("default_priority", base.default_priority)),
            report_schema_version=_as_schema_version(
                overlay.get("report_schema_version", base.report_schema_version)
            ),
        )

    def _apply(
        self,
        actor: Actor,
        tenant_id: str,
        normalized: Mapping[str, object],
    ) -> TaskAnalyzerConfig:
        current = self._materialize(tenant_id)
        defaults = default_config()
        overlay = dict(self._overrides.get(tenant_id, {}))
        stamp = self._clock()
        events: list[AuditEvent] = []
        for field in CONFIG_FIELDS:
            if field not in normalized:
                continue
            new_value = normalized[field]
            old_value = getattr(current, field)
            if _canonical(old_value) == _canonical(new_value):
                continue
            if _canonical(new_value) == _canonical(getattr(defaults, field)):
                overlay.pop(field, None)
            else:
                overlay[field] = new_value
            events.append(
                AuditEvent(
                    tenant_id=tenant_id,
                    actor_id=actor.actor_id,
                    action=CONFIG_UPDATE_ACTION,
                    from_state=_canonical(old_value),
                    to_state=_canonical(new_value),
                    rule_id=field,
                    at=stamp,
                )
            )
        if not events:
            return current
        self._audit.append_many(events)
        self._commit(tenant_id, overlay)
        return self._materialize(tenant_id)

    def _commit(self, tenant_id: str, overlay: Mapping[str, object]) -> None:
        merged = {tenant: dict(values) for tenant, values in self._overrides.items()}
        if overlay:
            merged[tenant_id] = dict(overlay)
        else:
            merged.pop(tenant_id, None)
        sealed = MappingProxyType(
            {tenant: MappingProxyType(values) for tenant, values in merged.items()}
        )
        object.__setattr__(self, "_overrides", sealed)


def _enforce(decision: AuthzDecision) -> None:
    if not decision.allowed:
        raise PermissionError(permission_message(decision))
