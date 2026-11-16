"""任務分析器狀態機與錯誤碼。"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from backend.task_analyzer.errors import (
    CATALOG,
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
    register_error_code,
)
from backend.task_analyzer.state_machine import (
    ASKING_ROUND_TIMEOUT_SECONDS,
    PARSING_TIMEOUT_SECONDS,
    AnalyzerState,
    IllegalTransitionError,
    TaskAnalyzer,
    allowed_targets,
)

T0 = datetime(2026, 11, 16, tzinfo=timezone.utc)
_S = AnalyzerState
_CHAIN = (
    _S.PARSING,
    _S.DISCOVERING,
    _S.GAP_IDENTIFIED,
    _S.ASKING,
    _S.CONSTRAINT_CHECKED,
    _S.BUDGET_ESTIMATING,
    _S.DECIDED,
)
_DECISIONS = (_S.GO, _S.CONDITIONAL_GO, _S.NO_GO, _S.HUMAN_REVIEW)
_TERMINALS = (*_DECISIONS, _S.FAILED, _S.TIMEOUT)


def _reach(state: AnalyzerState, task_id: str = "task-1") -> TaskAnalyzer:
    machine = TaskAnalyzer(task_id, now=T0)
    if state is _S.RECEIVED:
        return machine
    if state is _S.FAILED:
        machine.transition(_S.PARSING, now=T0)
        machine.fail(TA_002, now=T0)
        return machine
    if state is _S.TIMEOUT:
        machine.transition(_S.PARSING, now=T0)
        timed = machine.check_timeout(T0 + timedelta(seconds=30))
        assert timed is not None
        return machine
    for step in _CHAIN:
        machine.transition(step, now=T0)
        if step is state:
            return machine
    if state in _DECISIONS:
        machine.transition(state, now=T0)
        return machine
    raise AssertionError(state)


def test_catalog_is_exactly_001_through_008() -> None:
    assert tuple(CATALOG) == tuple(f"LINKIN-TA-{index:03d}" for index in range(1, 9))
    assert len({spec.code for spec in CATALOG.values()}) == 8


def test_each_code_has_chinese_description_trigger_and_recovery() -> None:
    for code, spec in CATALOG.items():
        assert spec.code == code
        assert spec.reusable is False
        assert get_spec(code) is spec
        for text in (spec.description, spec.trigger, spec.recovery):
            assert text.strip()
            assert any("\u4e00" <= char <= "\u9fff" for char in text)


def test_timeout_and_illegal_codes_keep_their_meaning() -> None:
    assert PARSING_TIMEOUT_SECONDS == 30
    assert ASKING_ROUND_TIMEOUT_SECONDS == 24 * 60 * 60
    assert "轉移" in get_spec(TA_007).trigger
    trigger = get_spec(TA_008).trigger
    assert "30" in trigger
    assert "24" in trigger
    assert "逾時" in get_spec(TA_008).description


def test_catalog_rejects_reuse_and_new_codes() -> None:
    original = get_spec(TA_007).description
    with pytest.raises(ErrorCodeReuseError) as reused:
        register_error_code(TA_007, "被改寫", "被改寫", "被改寫")
    assert reused.value.code == TA_007
    assert get_spec(TA_007).description == original
    with pytest.raises(ErrorCodeReuseError) as added:
        register_error_code("LINKIN-TA-009", "新碼", "觸發", "恢復")
    assert added.value.code == "LINKIN-TA-009"
    assert "LINKIN-TA-009" not in CATALOG


def test_catalog_and_specs_are_frozen() -> None:
    with pytest.raises(TypeError):
        CATALOG[TA_001] = get_spec(TA_002)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        get_spec(TA_007).description = "改寫"  # type: ignore[misc]


@pytest.mark.parametrize("task_id", ["", "   ", "\n\t", None, 12])
def test_invalid_task_id_raises_001_and_returns_event(task_id: object) -> None:
    with pytest.raises(TaskAnalyzerError) as caught:
        TaskAnalyzer(task_id, now=T0)  # type: ignore[arg-type]
    event = caught.value.event
    assert caught.value.code == TA_001
    assert event is not None
    assert event.code == TA_001  # type: ignore[attr-defined]
    assert event.kind == "rejected"  # type: ignore[attr-defined]
    assert event.occurred_at == T0  # type: ignore[attr-defined]
    assert get_spec(TA_001).description in str(caught.value)


def test_task_id_is_stripped() -> None:
    machine = TaskAnalyzer("  job-7  ", now=T0)
    assert machine.task_id == "job-7"
    assert machine.state is _S.RECEIVED
    assert machine.events == []


def test_allowed_targets_follow_the_chain() -> None:
    assert allowed_targets(_S.RECEIVED) == frozenset({_S.PARSING})
    assert allowed_targets(_S.PARSING) == frozenset({_S.DISCOVERING})
    assert allowed_targets(_S.DISCOVERING) == frozenset({_S.GAP_IDENTIFIED})
    assert allowed_targets(_S.GAP_IDENTIFIED) == frozenset({_S.ASKING})
    assert allowed_targets(_S.ASKING) == frozenset({_S.GAP_IDENTIFIED, _S.CONSTRAINT_CHECKED})
    assert allowed_targets(_S.CONSTRAINT_CHECKED) == frozenset({_S.BUDGET_ESTIMATING})
    assert allowed_targets(_S.BUDGET_ESTIMATING) == frozenset({_S.DECIDED})
    assert allowed_targets(_S.DECIDED) == frozenset(set(_DECISIONS))
    for state in _TERMINALS:
        assert allowed_targets(state) == frozenset()


def test_happy_path_reaches_go_and_returns_events() -> None:
    machine = TaskAnalyzer("alpha", now=T0)
    for step in (*_CHAIN, _S.GO):
        event = machine.transition(step, now=T0)
        assert event.to_state == step.value
        assert event.from_state != event.to_state
        assert event.code == ""
        assert event.kind == "transition"
        assert event.task_id == "alpha"
        assert event.occurred_at == T0
        assert len(event.event_id) == 32
    assert machine.state is _S.GO
    assert machine.asking_round == 1
    assert len({event.event_id for event in machine.events}) == len(machine.events)


@pytest.mark.parametrize("decision", _DECISIONS)
def test_decided_can_enter_each_outcome(decision: AnalyzerState) -> None:
    machine = _reach(_S.DECIDED)
    event = machine.transition(decision.value, now=T0)
    assert machine.state is decision
    assert event.to_state == decision.value
    assert event.kind == "transition"


def test_asking_can_cycle_back_to_gap() -> None:
    machine = _reach(_S.ASKING)
    assert machine.asking_round == 1
    back = machine.transition(_S.GAP_IDENTIFIED, now=T0)
    assert machine.state is _S.GAP_IDENTIFIED
    assert machine.asking_round == 1
    assert back.from_state == "ASKING"
    again = machine.transition(_S.ASKING, now=T0)
    assert machine.asking_round == 2
    assert again.asking_round == 2
    machine.transition(_S.CONSTRAINT_CHECKED, now=T0)
    assert machine.state is _S.CONSTRAINT_CHECKED


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        (_S.RECEIVED, _S.DISCOVERING),
        (_S.RECEIVED, _S.GO),
        (_S.PARSING, _S.GAP_IDENTIFIED),
        (_S.GAP_IDENTIFIED, _S.CONSTRAINT_CHECKED),
        (_S.ASKING, _S.DECIDED),
        (_S.BUDGET_ESTIMATING, _S.GO),
        (_S.DECIDED, _S.PARSING),
        (_S.GO, _S.NO_GO),
        (_S.PARSING, _S.PARSING),
    ],
)
def test_illegal_transition_raises_007_and_returns_event(
    src: AnalyzerState,
    dst: AnalyzerState,
) -> None:
    machine = _reach(src)
    before = len(machine.events)
    with pytest.raises(IllegalTransitionError) as caught:
        machine.transition(dst, now=T0)
    event = caught.value.event
    assert machine.state is src
    assert caught.value.code == TA_007
    assert event is machine.events[-1]
    assert event.code == TA_007  # type: ignore[attr-defined]
    assert event.kind == "illegal_transition"  # type: ignore[attr-defined]
    assert event.from_state == src.value  # type: ignore[attr-defined]
    assert event.to_state == dst.value  # type: ignore[attr-defined]
    assert event.task_id == machine.task_id  # type: ignore[attr-defined]
    assert len(machine.events) == before + 1


def test_unknown_state_name_is_illegal_transition() -> None:
    machine = _reach(_S.RECEIVED)
    with pytest.raises(IllegalTransitionError) as caught:
        machine.transition("NOT_A_STATE", now=T0)
    assert machine.state is _S.RECEIVED
    assert caught.value.code == TA_007
    assert caught.value.event.to_state == "NOT_A_STATE"  # type: ignore[attr-defined]


def test_target_must_be_state_or_name() -> None:
    machine = _reach(_S.RECEIVED)
    with pytest.raises(TypeError):
        machine.transition(1, now=T0)  # type: ignore[arg-type]
    assert machine.state is _S.RECEIVED
    assert machine.events == []


@pytest.mark.parametrize("target", [_S.FAILED, _S.TIMEOUT])
def test_failed_and_timeout_are_not_direct_edges(target: AnalyzerState) -> None:
    machine = _reach(_S.PARSING)
    with pytest.raises(IllegalTransitionError) as caught:
        machine.transition(target, now=T0)
    assert machine.state is _S.PARSING
    assert caught.value.event.to_state == target.value  # type: ignore[attr-defined]


@pytest.mark.parametrize("state", _TERMINALS)
def test_terminal_rejects_further_transition(state: AnalyzerState) -> None:
    machine = _reach(state)
    later = T0 + timedelta(days=1)
    with pytest.raises(IllegalTransitionError):
        machine.transition(_S.PARSING, now=later)
    assert machine.state is state


def test_parsing_times_out_at_30_seconds() -> None:
    machine = _reach(_S.PARSING)
    assert machine.check_timeout(T0 + timedelta(seconds=29.999)) is None
    assert machine.state is _S.PARSING
    event = machine.check_timeout(T0 + timedelta(seconds=30))
    assert event is not None
    assert event.code == TA_008
    assert event.kind == "timeout"
    assert event.from_state == "PARSING"
    assert event.to_state == "TIMEOUT"
    assert "30" in event.detail
    assert machine.state is _S.TIMEOUT


def test_parsing_timeout_ignores_other_limits_and_is_idempotent() -> None:
    machine = _reach(_S.PARSING)
    assert machine.check_timeout(
        T0 + timedelta(seconds=29),
        discovering_timeout_s=0,
        budget_timeout_s=0,
    ) is None
    event = machine.check_timeout(
        T0 + timedelta(seconds=30),
        discovering_timeout_s=0,
        budget_timeout_s=0,
    )
    assert event is not None and machine.state is _S.TIMEOUT
    assert machine.check_timeout(T0 + timedelta(days=3), discovering_timeout_s=0) is None
    assert len([item for item in machine.events if item.kind == "timeout"]) == 1


def test_leaving_parsing_after_30_seconds_times_out_instead() -> None:
    machine = _reach(_S.PARSING)
    event = machine.transition(_S.DISCOVERING, now=T0 + timedelta(seconds=30))
    assert event.code == TA_008
    assert machine.state is _S.TIMEOUT


def test_asking_round_times_out_at_24_hours() -> None:
    machine = _reach(_S.ASKING)
    almost = T0 + timedelta(hours=24) - timedelta(microseconds=1)
    assert machine.check_timeout(almost) is None
    event = machine.check_timeout(T0 + timedelta(hours=24))
    assert event is not None
    assert event.code == TA_008
    assert event.asking_round == 1
    assert "24" in event.detail
    assert machine.state is _S.TIMEOUT


def test_asking_transition_after_24_hours_times_out() -> None:
    machine = _reach(_S.ASKING)
    event = machine.transition(_S.CONSTRAINT_CHECKED, now=T0 + timedelta(hours=24))
    assert event.to_state == "TIMEOUT"
    assert machine.state is _S.TIMEOUT


def test_asking_timeout_resets_each_round() -> None:
    machine = _reach(_S.ASKING)
    machine.transition(_S.GAP_IDENTIFIED, now=T0 + timedelta(hours=20))
    machine.transition(_S.ASKING, now=T0 + timedelta(hours=20))
    assert machine.asking_round == 2
    assert machine.check_timeout(T0 + timedelta(hours=43)) is None
    event = machine.check_timeout(T0 + timedelta(hours=44))
    assert event is not None
    assert event.asking_round == 2
    assert machine.state is _S.TIMEOUT


def test_discovering_timeout_uses_configured_seconds() -> None:
    machine = _reach(_S.DISCOVERING)
    assert machine.check_timeout(T0 + timedelta(days=30)) is None
    assert machine.check_timeout(T0 + timedelta(seconds=9), discovering_timeout_s=10) is None
    event = machine.transition(
        _S.GAP_IDENTIFIED,
        now=T0 + timedelta(seconds=10),
        discovering_timeout_s=10,
    )
    assert event.code == TA_008
    assert event.from_state == "DISCOVERING"
    assert machine.state is _S.TIMEOUT


def test_discovering_within_limit_continues() -> None:
    machine = _reach(_S.DISCOVERING)
    event = machine.transition(
        _S.GAP_IDENTIFIED,
        now=T0 + timedelta(seconds=10),
        discovering_timeout_s=11,
    )
    assert machine.state is _S.GAP_IDENTIFIED
    assert event.kind == "transition"


def test_zero_discovering_timeout_fires_immediately() -> None:
    machine = _reach(_S.DISCOVERING)
    event = machine.check_timeout(T0, discovering_timeout_s=0)
    assert event is not None
    assert machine.state is _S.TIMEOUT


def test_budget_timeout_uses_configured_seconds() -> None:
    machine = _reach(_S.BUDGET_ESTIMATING)
    assert machine.check_timeout(
        T0 + timedelta(seconds=3),
        discovering_timeout_s=0,
        budget_timeout_s=5,
    ) is None
    event = machine.check_timeout(
        T0 + timedelta(seconds=5),
        discovering_timeout_s=999,
        budget_timeout_s=5,
    )
    assert event is not None
    assert event.from_state == "BUDGET_ESTIMATING"
    assert event.code == TA_008
    assert machine.state is _S.TIMEOUT


@pytest.mark.parametrize(
    "state",
    [
        _S.RECEIVED,
        _S.GAP_IDENTIFIED,
        _S.CONSTRAINT_CHECKED,
        _S.DECIDED,
        *_TERMINALS,
    ],
)
def test_state_without_limit_does_not_timeout(state: AnalyzerState) -> None:
    machine = _reach(state)
    assert machine.check_timeout(
        T0 + timedelta(days=365),
        discovering_timeout_s=1,
        budget_timeout_s=1,
    ) is None
    assert machine.state is state


def test_clock_rewind_does_not_timeout() -> None:
    machine = _reach(_S.PARSING)
    assert machine.check_timeout(T0 - timedelta(seconds=5)) is None
    assert machine.state is _S.PARSING


def test_naive_now_is_rejected() -> None:
    machine = _reach(_S.RECEIVED)
    with pytest.raises(ValueError):
        machine.transition(_S.PARSING, now=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        TaskAnalyzer("task", now=datetime(2026, 1, 1))
    assert machine.state is _S.RECEIVED


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (-0.1, ValueError),
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (True, TypeError),
        ("10", TypeError),
    ],
)
def test_timeout_seconds_must_be_finite(value: object, expected: type[Exception]) -> None:
    machine = _reach(_S.RECEIVED)
    with pytest.raises(expected):
        machine.transition(_S.PARSING, now=T0, budget_timeout_s=value)  # type: ignore[arg-type]
    assert machine.state is _S.RECEIVED
    assert machine.events == []


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (_S.PARSING, TA_002),
        (_S.DISCOVERING, TA_003),
        (_S.GAP_IDENTIFIED, TA_004),
        (_S.ASKING, TA_004),
        (_S.CONSTRAINT_CHECKED, TA_005),
        (_S.BUDGET_ESTIMATING, TA_006),
    ],
)
def test_fail_uses_the_phase_code(state: AnalyzerState, code: str) -> None:
    machine = _reach(state)
    event = machine.fail(code, now=T0)
    assert machine.state is _S.FAILED
    assert event is machine.events[-1]
    assert event.kind == "failure"
    assert event.code == code
    assert event.from_state == state.value
    assert event.to_state == "FAILED"
    assert event.detail == get_spec(code).description


def test_fail_after_parsing_timeout_records_timeout() -> None:
    machine = _reach(_S.PARSING)
    event = machine.fail(TA_002, now=T0 + timedelta(seconds=30))
    assert event.code == TA_008
    assert machine.state is _S.TIMEOUT


@pytest.mark.parametrize("code", [TA_001, TA_007, TA_008])
def test_reserved_codes_cannot_be_reused_as_failure(code: str) -> None:
    machine = _reach(_S.PARSING)
    before = list(machine.events)
    with pytest.raises(ErrorCodeReuseError) as caught:
        machine.fail(code, now=T0 + timedelta(seconds=30))
    assert caught.value.code == code
    assert machine.state is _S.PARSING
    assert machine.events == before


def test_fail_from_wrong_phase_is_illegal() -> None:
    machine = _reach(_S.PARSING)
    with pytest.raises(IllegalTransitionError) as caught:
        machine.fail(TA_006, now=T0)
    assert machine.state is _S.PARSING
    assert caught.value.code == TA_007
    assert caught.value.event.to_state == "FAILED"  # type: ignore[attr-defined]
    assert "LINKIN-TA-006" in caught.value.event.detail  # type: ignore[attr-defined]


def test_fail_unknown_code_does_not_move() -> None:
    machine = _reach(_S.PARSING)
    before = len(machine.events)
    with pytest.raises(KeyError):
        machine.fail("LINKIN-TA-009", now=T0)
    assert machine.state is _S.PARSING
    assert len(machine.events) == before


def test_fail_from_terminal_is_illegal() -> None:
    machine = _reach(_S.GO)
    with pytest.raises(IllegalTransitionError) as caught:
        machine.fail(TA_002, now=T0)
    assert machine.state is _S.GO
    assert caught.value.code == TA_007


def test_event_ids_are_not_reused() -> None:
    machine = _reach(_S.ASKING)
    machine.transition(_S.GAP_IDENTIFIED, now=T0)
    with pytest.raises(IllegalTransitionError):
        machine.transition(_S.GO, now=T0)
    ids = [event.event_id for event in machine.events]
    assert len(ids) == len(set(ids))
    assert all(len(event_id) == 32 for event_id in ids)
