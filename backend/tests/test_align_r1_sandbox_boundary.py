"""Align R1：runsc／沙箱硬邊界＝Cap-2 邊界契約測試。

對表 #148／#140；非全量 Cap-2；不測真容器／aider／draft 自動開。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.core.align_r1_sandbox_boundary import (
    CAP2_BOUNDARY_ONLY,
    CONTRACT_ID,
    DOES_NOT_IMPLEMENT_FULL_CAP2,
    SandboxBlockReason,
    SandboxBoundaryInput,
    SandboxVerdict,
    contract_boundary_flags,
    evaluate_sandbox_boundary,
    reset_sandbox_shadow_log,
    sandbox_shadow_log,
)


@pytest.fixture(autouse=True)
def _clear_shadow() -> Generator[None, None, None]:
    reset_sandbox_shadow_log()
    yield
    reset_sandbox_shadow_log()


def _ok_input(**overrides: object) -> SandboxBoundaryInput:
    base: dict[str, object] = {
        "runtime": "runsc",
        "network": "none",
        "token_in_sandbox": False,
        "secret_in_sandbox": False,
        "secret_scan_passed": True,
        "sandbox_aborted": False,
    }
    base.update(overrides)
    return SandboxBoundaryInput(**base)  # type: ignore[arg-type]


# --- 硬邊界擋 ---


def test_r1_network_not_none_blocks() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(network="bridge"))
    assert decision.verdict == SandboxVerdict.BLOCK
    assert decision.block_reason == SandboxBlockReason.NETWORK_NOT_NONE
    assert decision.audit_event == "code_ops.sandbox.network_blocked"
    assert decision.opens_draft_pr is False


def test_r1_token_into_sandbox_blocks() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(token_in_sandbox=True))
    assert decision.verdict == SandboxVerdict.BLOCK
    assert decision.block_reason == SandboxBlockReason.TOKEN_INTO_SANDBOX
    assert decision.audit_event == "code_ops.sandbox.token_blocked"
    assert decision.opens_draft_pr is False


def test_r1_secret_into_sandbox_blocks() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(secret_in_sandbox=True))
    assert decision.verdict == SandboxVerdict.BLOCK
    assert decision.block_reason == SandboxBlockReason.SECRET_INTO_SANDBOX
    assert decision.opens_draft_pr is False


def test_r1_secret_scan_fail_blocks() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(secret_scan_passed=False))
    assert decision.verdict == SandboxVerdict.BLOCK
    assert decision.block_reason == SandboxBlockReason.SCAN_BLOCKED
    assert decision.audit_event == "code_ops.sandbox.scan.blocked"
    assert decision.opens_draft_pr is False


def test_r1_runtime_not_runsc_blocks() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(runtime="runc"))
    assert decision.verdict == SandboxVerdict.BLOCK
    assert decision.block_reason == SandboxBlockReason.RUNTIME_NOT_RUNSC
    assert decision.audit_event == "code_ops.sandbox.runtime_blocked"


# --- abort → aborted；不開 draft ---


def test_r1_sandbox_abort_fail_closed_no_draft() -> None:
    decision = evaluate_sandbox_boundary(_ok_input(sandbox_aborted=True))
    assert decision.verdict == SandboxVerdict.ABORT
    assert decision.block_reason == SandboxBlockReason.SANDBOX_ABORTED
    assert decision.audit_event == "code_ops.sandbox.aborted"
    assert decision.opens_draft_pr is False


# --- 全過才 allow ---


def test_r1_all_pass_allows() -> None:
    decision = evaluate_sandbox_boundary(_ok_input())
    assert decision.verdict == SandboxVerdict.ALLOW
    assert decision.block_reason == SandboxBlockReason.NONE
    assert decision.audit_event == "code_ops.sandbox.boundary_passed"
    assert decision.cap2_boundary_only is True
    assert decision.does_not_implement_full_cap2 is True
    # allow 亦不自動開 draft（本契約邊界 only）
    assert decision.opens_draft_pr is False


# --- shadow 有記錄 ---


def test_r1_shadow_records_evaluation() -> None:
    evaluate_sandbox_boundary(_ok_input(network="host"))
    evaluate_sandbox_boundary(_ok_input())
    log = sandbox_shadow_log()
    assert len(log) == 2
    assert all(row["mode"] == "shadow" for row in log)
    assert all(row["contract_id"] == CONTRACT_ID for row in log)
    assert log[0]["payload"]["verdict"] == SandboxVerdict.BLOCK.value
    assert log[1]["payload"]["verdict"] == SandboxVerdict.ALLOW.value


# --- 全量 Cap-2 未實作旗標 ---


def test_r1_full_cap2_not_implemented_flags() -> None:
    assert CAP2_BOUNDARY_ONLY is True
    assert DOES_NOT_IMPLEMENT_FULL_CAP2 is True
    flags = contract_boundary_flags()
    assert flags["contract_id"] == CONTRACT_ID
    assert flags["cap2_boundary_only"] is True
    assert flags["does_not_implement_full_cap2"] is True
    assert flags["does_not_implement_aider"] is True
    assert flags["does_not_start_real_runsc_container"] is True
    assert flags["does_not_auto_open_draft_pr"] is True
    assert flags["does_not_include_qa24_in_modelgw_ci"] is True
    assert flags["ready_to_merge_product"] is False
    assert flags["required_runtime"] == "runsc"
    assert flags["required_network"] == "none"
