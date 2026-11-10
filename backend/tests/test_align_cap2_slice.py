"""Align Cap：Cap-2 垂直切片契約測試（超出 R1 邊界）。

對表 #148／#150；非真 aider／runsc／draft；不納 ModelGW CI。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.core.align_cap2_slice import (
    CONTRACT_ID,
    DOES_NOT_OPEN_REAL_DRAFT_PR,
    DOES_NOT_START_REAL_RUNSC,
    DOES_NOT_WIRE_REAL_AIDER,
    MODELGW_CI_REQUIRED,
    REQUIRES_R1_BOUNDARY_ALLOW,
    Cap2BlockReason,
    Cap2Provider,
    Cap2SliceInput,
    Cap2Verdict,
    cap2_shadow_log,
    contract_cap2_flags,
    evaluate_cap2_slice,
    reset_cap2_shadow_log,
)


@pytest.fixture(autouse=True)
def _clear_shadow() -> Generator[None, None, None]:
    reset_cap2_shadow_log()
    yield
    reset_cap2_shadow_log()


def _ok_input(**overrides: object) -> Cap2SliceInput:
    base: dict[str, object] = {
        "r1_boundary_allow": True,
        "r1_verdict": "allow",
        "preferred_provider": "aider",
        "aider_available": True,
        "fallback_enabled": True,
        "secret_scan_passed": True,
        "sandbox_aborted": False,
        "has_delivery_evidence": True,
        "draft_gate_requested": True,
    }
    base.update(overrides)
    return Cap2SliceInput(**base)  # type: ignore[arg-type]


# --- R1 未 allow → block；不得覆寫 ---


def test_cap2_r1_not_allow_blocks() -> None:
    decision = evaluate_cap2_slice(
        _ok_input(r1_boundary_allow=False, r1_verdict="block")
    )
    assert decision.verdict == Cap2Verdict.BLOCK
    assert decision.block_reason == Cap2BlockReason.R1_NOT_ALLOW
    assert decision.audit_event == "code_ops.cap2.r1_not_allow"
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


def test_cap2_r1_abort_fail_closed() -> None:
    decision = evaluate_cap2_slice(
        _ok_input(r1_boundary_allow=False, r1_verdict="abort")
    )
    assert decision.verdict == Cap2Verdict.ABORT
    assert decision.block_reason == Cap2BlockReason.R1_ABORT
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


def test_cap2_r1_bool_false_blocks_without_verdict() -> None:
    decision = evaluate_cap2_slice(
        Cap2SliceInput(
            r1_boundary_allow=False,
            r1_verdict="",
            secret_scan_passed=True,
            has_delivery_evidence=True,
            aider_available=True,
        )
    )
    assert decision.verdict == Cap2Verdict.BLOCK
    assert decision.block_reason == Cap2BlockReason.R1_NOT_ALLOW


# --- R1 allow＋切片條件 → allow ---


def test_cap2_r1_allow_slice_ok_allows() -> None:
    decision = evaluate_cap2_slice(_ok_input())
    assert decision.verdict == Cap2Verdict.ALLOW
    assert decision.block_reason == Cap2BlockReason.NONE
    assert decision.audit_event == "code_ops.cap2.slice_passed"
    assert decision.selected_provider == Cap2Provider.AIDER
    assert decision.fallback_used is False
    assert decision.draft_gate_allowed is True
    # 契約允許閘 ≠ 真開
    assert decision.opens_real_draft_pr is False
    assert decision.does_not_wire_real_aider is True
    assert decision.modelgw_ci_required is False


def test_cap2_allow_without_draft_request_gate_false() -> None:
    decision = evaluate_cap2_slice(_ok_input(draft_gate_requested=False))
    assert decision.verdict == Cap2Verdict.ALLOW
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


# --- abort／scan／空 evidence → 不開 draft ---


def test_cap2_sandbox_abort_no_draft() -> None:
    decision = evaluate_cap2_slice(_ok_input(sandbox_aborted=True))
    assert decision.verdict == Cap2Verdict.ABORT
    assert decision.block_reason == Cap2BlockReason.SANDBOX_ABORTED
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


def test_cap2_scan_blocked_no_draft() -> None:
    decision = evaluate_cap2_slice(_ok_input(secret_scan_passed=False))
    assert decision.verdict == Cap2Verdict.BLOCK
    assert decision.block_reason == Cap2BlockReason.SCAN_BLOCKED
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


def test_cap2_empty_evidence_no_draft() -> None:
    decision = evaluate_cap2_slice(_ok_input(has_delivery_evidence=False))
    assert decision.verdict == Cap2Verdict.BLOCK
    assert decision.block_reason == Cap2BlockReason.EMPTY_EVIDENCE
    assert decision.draft_gate_allowed is False
    assert decision.opens_real_draft_pr is False


# --- provider／fallback 契約 ---


def test_cap2_aider_fallback_to_opencode() -> None:
    decision = evaluate_cap2_slice(
        _ok_input(aider_available=False, fallback_enabled=True)
    )
    assert decision.verdict == Cap2Verdict.ALLOW
    assert decision.selected_provider == Cap2Provider.OPENCODE
    assert decision.fallback_used is True
    assert decision.opens_real_draft_pr is False


def test_cap2_provider_unavailable_blocks() -> None:
    decision = evaluate_cap2_slice(
        _ok_input(aider_available=False, fallback_enabled=False)
    )
    assert decision.verdict == Cap2Verdict.BLOCK
    assert decision.block_reason == Cap2BlockReason.PROVIDER_UNAVAILABLE
    assert decision.selected_provider == Cap2Provider.NONE
    assert decision.draft_gate_allowed is False


def test_cap2_preferred_opencode_no_fallback_flag() -> None:
    decision = evaluate_cap2_slice(_ok_input(preferred_provider="opencode"))
    assert decision.verdict == Cap2Verdict.ALLOW
    assert decision.selected_provider == Cap2Provider.OPENCODE
    assert decision.fallback_used is False


# --- QA24／旗標 ---


def test_cap2_qa24_modelgw_ci_required_false() -> None:
    assert MODELGW_CI_REQUIRED is False
    decision = evaluate_cap2_slice(_ok_input())
    assert decision.modelgw_ci_required is False
    assert decision.qa24_ownership == "Cap-2"
    flags = contract_cap2_flags()
    assert flags["modelgw_ci_required"] is False
    assert flags["qa24_ownership"] == "Cap-2"
    assert flags["ready_to_merge_product"] is False


def test_cap2_explicit_no_real_runtime_flags() -> None:
    assert REQUIRES_R1_BOUNDARY_ALLOW is True
    assert DOES_NOT_WIRE_REAL_AIDER is True
    assert DOES_NOT_OPEN_REAL_DRAFT_PR is True
    assert DOES_NOT_START_REAL_RUNSC is True
    flags = contract_cap2_flags()
    assert flags["contract_id"] == CONTRACT_ID
    assert flags["requires_r1_boundary_allow"] is True
    assert flags["does_not_wire_real_aider"] is True
    assert flags["does_not_open_real_draft_pr"] is True
    assert flags["does_not_start_real_runsc"] is True
    assert flags["does_not_wire_real_runtime"] is True
    assert flags["beyond_r1_boundary"] is True


# --- shadow ---


def test_cap2_shadow_records_evaluation() -> None:
    evaluate_cap2_slice(_ok_input(r1_verdict="block", r1_boundary_allow=False))
    evaluate_cap2_slice(_ok_input())
    log = cap2_shadow_log()
    assert len(log) == 2
    assert all(row["mode"] == "shadow" for row in log)
    assert all(row["contract_id"] == CONTRACT_ID for row in log)
    assert log[0]["payload"]["verdict"] == Cap2Verdict.BLOCK.value
    assert log[1]["payload"]["verdict"] == Cap2Verdict.ALLOW.value
