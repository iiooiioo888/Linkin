"""任務分析器狀態機。

合法鏈：
RECEIVED → PARSING → DISCOVERING → GAP_IDENTIFIED → ASKING
→ CONSTRAINT_CHECKED → BUDGET_ESTIMATING → DECIDED
→ GO／CONDITIONAL_GO／NO_GO／HUMAN_REVIEW。

ASKING 可回到 GAP_IDENTIFIED 再開下一輪。FAILED 只由階段失敗碼進入。
TIMEOUT 由計時進入。非法轉移拋 LINKIN-TA-007，審計事件隨例外帶回，不寫資料庫。

不讀設定檔，也不裁決缺口、約束或預算內容。DISCOVERING 與
BUDGET_ESTIMATING 的逾時秒數由呼叫參數傳入。
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import NoReturn

from backend.task_analyzer.errors import (
    TA_001,
    TA_002,
    TA_003,
    TA_004,
    TA_005,
    TA_006,
    TA_007,
    TA_008,
    ErrorCodeReuseError,
    TaskAnalyzerError,
    get_spec,
)

PARSING_TIMEOUT_SECONDS = 30.0
ASKING_ROUND_TIMEOUT_SECONDS = 24.0 * 60.0 * 60.0

_RESERVED_FAIL_CODES = frozenset({TA_001, TA_007, TA_008})


class AnalyzerState(str, Enum):
    RECEIVED = "RECEIVED"
    PARSING = "PARSING"
    DISCOVERING = "DISCOVERING"
    GAP_IDENTIFIED = "GAP_IDENTIFIED"
    ASKING = "ASKING"
    CONSTRAINT_CHECKED = "CONSTRAINT_CHECKED"
    BUDGET_ESTIMATING = "BUDGET_ESTIMATING"
    DECIDED = "DECIDED"
    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


_S = AnalyzerState

_ALLOWED: dict[AnalyzerState, frozenset[AnalyzerState]] = {
    _S.RECEIVED: frozenset({_S.PARSING}),
    _S.PARSING: frozenset({_S.DISCOVERING}),
    _S.DISCOVERING: frozenset({_S.GAP_IDENTIFIED}),
    _S.GAP_IDENTIFIED: frozenset({_S.ASKING}),
    _S.ASKING: frozenset({_S.GAP_IDENTIFIED, _S.CONSTRAINT_CHECKED}),
    _S.CONSTRAINT_CHECKED: frozenset({_S.BUDGET_ESTIMATING}),
    _S.BUDGET_ESTIMATING: frozenset({_S.DECIDED}),
    _S.DECIDED: frozenset({_S.GO, _S.CONDITIONAL_GO, _S.NO_GO, _S.HUMAN_REVIEW}),
    _S.GO: frozenset(),
    _S.CONDITIONAL_GO: frozenset(),
    _S.NO_GO: frozenset(),
    _S.HUMAN_REVIEW: frozenset(),
    _S.FAILED: frozenset(),
    _S.TIMEOUT: frozenset(),
}

_TERMINAL = frozenset({
    _S.GO,
    _S.CONDITIONAL_GO,
    _S.NO_GO,
    _S.HUMAN_REVIEW,
    _S.FAILED,
    _S.TIMEOUT,
})

# 階段失敗碼的唯一觸發狀態。對錯狀態使用即為復用，不另開規則。
_FAILURE_CODE_BY_STATE: dict[AnalyzerState, str] = {
    _S.PARSING: TA_002,
    _S.DISCOVERING: TA_003,
    _S.GAP_IDENTIFIED: TA_004,
    _S.ASKING: TA_004,
    _S.CONSTRAINT_CHECKED: TA_005,
    _S.BUDGET_ESTIMATING: TA_006,
}


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """一筆審計事件。呼叫方自行保存；本模組不接資料庫。"""

    event_id: str
    task_id: str
    kind: str
    from_state: str
    to_state: str
    code: str
    occurred_at: datetime
    detail: str
    asking_round: int = 0


class IllegalTransitionError(TaskAnalyzerError):
    """非法轉移。``event`` 即本次寫下的審計事件。"""

    def __init__(self, event: AuditEvent) -> None:
        super().__init__(get_spec(TA_007), event)


def allowed_targets(state: AnalyzerState) -> frozenset[AnalyzerState]:
    """目前狀態可經 ``transition`` 到達的後繼。不含 FAILED 與 TIMEOUT。"""
    return _ALLOWED[AnalyzerState(state)]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(now: datetime, *, name: str = "now") -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(f"{name} 必須是帶時區的 datetime")
    return now


def _finite_seconds(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} 必須是秒數")
    number = float(value)
    if number < 0 or not math.isfinite(number):
        raise ValueError(f"{name} 必須是大於等於 0 的有限秒數")
    return number


def _format_seconds(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def _new_event(
    *,
    task_id: str,
    kind: str,
    from_state: str,
    to_state: str,
    code: str,
    occurred_at: datetime,
    detail: str,
    asking_round: int,
) -> AuditEvent:
    return AuditEvent(
        event_id=uuid.uuid4().hex,
        task_id=task_id,
        kind=kind,
        from_state=from_state,
        to_state=to_state,
        code=code,
        occurred_at=occurred_at,
        detail=detail,
        asking_round=asking_round,
    )


def _limit_for(
    state: AnalyzerState,
    discovering_timeout_s: float | None,
    budget_timeout_s: float | None,
) -> float | None:
    if state is _S.PARSING:
        return PARSING_TIMEOUT_SECONDS
    if state is _S.ASKING:
        return ASKING_ROUND_TIMEOUT_SECONDS
    if state is _S.DISCOVERING:
        return discovering_timeout_s
    if state is _S.BUDGET_ESTIMATING:
        return budget_timeout_s
    return None


class TaskAnalyzer:
    """單一任務的分析會話。逾時優先於後繼轉移與階段失敗。"""

    def __init__(self, task_id: str, *, now: datetime | None = None) -> None:
        opened_at = _require_aware(now) if now is not None else _utcnow()
        if not isinstance(task_id, str) or task_id.strip() == "":
            shown = task_id.strip() if isinstance(task_id, str) else ""
            spec = get_spec(TA_001)
            event = _new_event(
                task_id=shown,
                kind="rejected",
                from_state="",
                to_state="",
                code=spec.code,
                occurred_at=opened_at,
                detail=spec.trigger,
                asking_round=0,
            )
            raise TaskAnalyzerError(spec, event)
        self.task_id = task_id.strip()
        self.state = _S.RECEIVED
        self.entered_at = opened_at
        self.asking_round = 0
        self.asking_round_started_at: datetime | None = None
        self.events: list[AuditEvent] = []

    def transition(
        self,
        target: AnalyzerState | str,
        *,
        now: datetime | None = None,
        discovering_timeout_s: float | None = None,
        budget_timeout_s: float | None = None,
    ) -> AuditEvent:
        """合法轉移回傳審計事件。已逾時則進入 TIMEOUT 並回傳該事件。

        非法轉移拋 :class:`IllegalTransitionError`（LINKIN-TA-007）。
        事件寫在例外的 ``event``，並附加到 ``events``。
        """
        dest, label = _coerce_target(target)
        at, discovering, budget = self._timed_args(
            now,
            discovering_timeout_s=discovering_timeout_s,
            budget_timeout_s=budget_timeout_s,
        )
        expired = self._expire_at(at, discovering, budget)
        if expired is not None:
            return expired
        if dest is None or dest not in _ALLOWED[self.state]:
            self._reject(label, at, f"不允許從 {self.state.value} 轉到 {label}")
        if dest is _S.ASKING:
            self.asking_round += 1
            self.asking_round_started_at = at
        event = _new_event(
            task_id=self.task_id,
            kind="transition",
            from_state=self.state.value,
            to_state=dest.value,
            code="",
            occurred_at=at,
            detail=f"{self.state.value} → {dest.value}",
            asking_round=self.asking_round,
        )
        self.state = dest
        self.entered_at = at
        self.events.append(event)
        return event

    def fail(
        self,
        code: str,
        *,
        now: datetime | None = None,
        discovering_timeout_s: float | None = None,
        budget_timeout_s: float | None = None,
    ) -> AuditEvent:
        """以階段失敗碼進入 FAILED。001／007／008 不可拿來當失敗原因。"""
        at, discovering, budget = self._timed_args(
            now,
            discovering_timeout_s=discovering_timeout_s,
            budget_timeout_s=budget_timeout_s,
        )
        if code in _RESERVED_FAIL_CODES:
            raise ErrorCodeReuseError(code, "此碼已保留給識別、非法轉移或逾時")
        spec = get_spec(code)
        expired = self._expire_at(at, discovering, budget)
        if expired is not None:
            return expired
        if _FAILURE_CODE_BY_STATE.get(self.state) != code:
            self._reject(
                _S.FAILED.value,
                at,
                f"不允許以 {code} 從 {self.state.value} 進入 FAILED",
            )
        event = _new_event(
            task_id=self.task_id,
            kind="failure",
            from_state=self.state.value,
            to_state=_S.FAILED.value,
            code=spec.code,
            occurred_at=at,
            detail=spec.description,
            asking_round=self.asking_round,
        )
        self.state = _S.FAILED
        self.entered_at = at
        self.events.append(event)
        return event

    def check_timeout(
        self,
        now: datetime | None = None,
        *,
        discovering_timeout_s: float | None = None,
        budget_timeout_s: float | None = None,
    ) -> AuditEvent | None:
        """若目前階段已逾時，進入 TIMEOUT 並回傳審計事件；否則回傳 None。"""
        at, discovering, budget = self._timed_args(
            now,
            discovering_timeout_s=discovering_timeout_s,
            budget_timeout_s=budget_timeout_s,
        )
        return self._expire_at(at, discovering, budget)

    def _timed_args(
        self,
        now: datetime | None,
        *,
        discovering_timeout_s: float | None,
        budget_timeout_s: float | None,
    ) -> tuple[datetime, float | None, float | None]:
        at = _require_aware(now) if now is not None else _utcnow()
        discovering = _finite_seconds("discovering_timeout_s", discovering_timeout_s)
        budget = _finite_seconds("budget_timeout_s", budget_timeout_s)
        return at, discovering, budget

    def _expire_at(
        self,
        at: datetime,
        discovering_timeout_s: float | None,
        budget_timeout_s: float | None,
    ) -> AuditEvent | None:
        if self.state in _TERMINAL:
            return None
        limit = _limit_for(self.state, discovering_timeout_s, budget_timeout_s)
        if limit is None:
            return None
        anchor = self.entered_at
        if self.state is _S.ASKING and self.asking_round_started_at is not None:
            anchor = self.asking_round_started_at
        elapsed = (at - anchor).total_seconds()
        if elapsed < limit:
            return None
        shown = _format_seconds(limit)
        if self.state is _S.ASKING:
            hours = _format_seconds(ASKING_ROUND_TIMEOUT_SECONDS / 3600)
            detail = f"ASKING 第 {self.asking_round} 輪已滿 {shown} 秒（{hours} 小時）"
        else:
            detail = f"{self.state.value} 已滿時限 {shown} 秒"
        event = _new_event(
            task_id=self.task_id,
            kind="timeout",
            from_state=self.state.value,
            to_state=_S.TIMEOUT.value,
            code=TA_008,
            occurred_at=at,
            detail=detail,
            asking_round=self.asking_round,
        )
        self.state = _S.TIMEOUT
        self.entered_at = at
        self.events.append(event)
        return event

    def _reject(self, to_state: str, at: datetime, detail: str) -> NoReturn:
        event = _new_event(
            task_id=self.task_id,
            kind="illegal_transition",
            from_state=self.state.value,
            to_state=to_state,
            code=TA_007,
            occurred_at=at,
            detail=detail,
            asking_round=self.asking_round,
        )
        self.events.append(event)
        raise IllegalTransitionError(event)


def _coerce_target(target: AnalyzerState | str) -> tuple[AnalyzerState | None, str]:
    if isinstance(target, AnalyzerState):
        return target, target.value
    if not isinstance(target, str):
        raise TypeError("目標狀態必須是 AnalyzerState 或狀態名稱")
    try:
        parsed = AnalyzerState(target)
    except ValueError:
        return None, target
    return parsed, parsed.value


__all__ = [
    "ASKING_ROUND_TIMEOUT_SECONDS",
    "PARSING_TIMEOUT_SECONDS",
    "AnalyzerState",
    "AuditEvent",
    "IllegalTransitionError",
    "TaskAnalyzer",
    "allowed_targets",
]
