"""Align R3：AuthGate→tenant 自動注入殘差契約測試。

對表 #148 §4／align-spec §10.1 R3／P5 Q7；非真 AuthGate；不改 admit 熱路徑。
"""

from __future__ import annotations

import pytest

from backend.core.align_r3_authgate_tenant import (
    CONTRACT_ID,
    DOES_NOT_MUTATE_ADMIT_HOTPATH,
    DOES_NOT_WIRE_REAL_AUTHGATE,
    SHADOW_ONLY,
    WIRE_CHANGE,
    R3BlockReason,
    R3TenantInjectInput,
    R3Verdict,
    contract_r3_flags,
    evaluate_r3_tenant_inject,
    r3_shadow_log,
    reset_r3_shadow_log,
)


@pytest.fixture(autouse=True)
def _clear_shadow() -> None:
    reset_r3_shadow_log()
    yield
    reset_r3_shadow_log()


# --- explicit／http_body → allow（含 ""） ---


def test_r3_explicit_tenant_allows() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="explicit", tenant_id="acme")
    )
    assert decision.verdict == R3Verdict.ALLOW
    assert decision.block_reason == R3BlockReason.NONE
    assert decision.audit_event == "modelgw.r3.tenant_inject.explicit_ok"
    assert decision.effective_tenant_id == "acme"
    assert decision.tenant_injected is False
    assert decision.source_normalized == "explicit"


def test_r3_http_body_empty_string_allows() -> None:
    """現行口徑：tenant="" 可 allow（C 類／現網相容）。"""
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="http_body", tenant_id="")
    )
    assert decision.verdict == R3Verdict.ALLOW
    assert decision.effective_tenant_id == ""
    assert decision.tenant_injected is False
    assert decision.source_normalized == "http_body"


def test_r3_http_body_none_tenant_treats_as_empty() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="http_body", tenant_id=None)
    )
    assert decision.verdict == R3Verdict.ALLOW
    assert decision.effective_tenant_id == ""
    assert decision.tenant_injected is False


# --- AuthGate／header／cookie → would_inject_blocked；未注入 ---


def test_r3_authgate_session_would_inject_blocked() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(
            source="authgate_session",
            would_inject_tenant="acme",
            tenant_id=None,
        )
    )
    assert decision.verdict == R3Verdict.WOULD_INJECT_BLOCKED
    assert decision.block_reason == R3BlockReason.AUTHGATE_SESSION
    assert decision.audit_event == "modelgw.r3.tenant_inject.would_inject_blocked"
    assert decision.tenant_injected is False
    assert decision.effective_tenant_id is None
    log = r3_shadow_log()
    assert len(log) == 1
    assert log[0]["payload"]["would_inject_tenant"] == "acme"
    assert log[0]["payload"]["tenant_injected"] is False


def test_r3_header_guess_blocked() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="header_guess", would_inject_tenant="x")
    )
    assert decision.verdict == R3Verdict.WOULD_INJECT_BLOCKED
    assert decision.block_reason == R3BlockReason.HEADER_GUESS
    assert decision.tenant_injected is False


def test_r3_cookie_blocked() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="cookie", would_inject_tenant="y")
    )
    assert decision.verdict == R3Verdict.WOULD_INJECT_BLOCKED
    assert decision.block_reason == R3BlockReason.COOKIE
    assert decision.tenant_injected is False


# --- 缺來源 fail-closed ---


def test_r3_missing_source_tenant_required_blocks() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="", tenant_required=True)
    )
    assert decision.verdict == R3Verdict.BLOCK
    assert decision.block_reason == R3BlockReason.MISSING_SOURCE
    assert decision.audit_event == "modelgw.r3.tenant_inject.missing_source"
    assert decision.tenant_injected is False
    assert decision.effective_tenant_id is None


def test_r3_missing_source_not_required_allows_empty_path() -> None:
    """不要求 tenant 時：不猜 AuthGate；有效 ""（現網相容）。"""
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="", tenant_required=False)
    )
    assert decision.verdict == R3Verdict.ALLOW
    assert decision.effective_tenant_id == ""
    assert decision.tenant_injected is False
    assert decision.source_normalized == "missing"


# --- 異 tenant 交叉 ---


def test_r3_cross_tenant_attempt_blocks() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(
            source="explicit",
            tenant_id="acme",
            cross_tenant_id="other",
        )
    )
    assert decision.verdict == R3Verdict.BLOCK
    assert decision.block_reason == R3BlockReason.CROSS_TENANT
    assert decision.audit_event == "modelgw.r3.tenant_inject.cross_tenant_blocked"
    assert decision.tenant_injected is False
    assert decision.effective_tenant_id is None


def test_r3_same_cross_tenant_id_does_not_block() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(
            source="explicit",
            tenant_id="acme",
            cross_tenant_id="acme",
        )
    )
    assert decision.verdict == R3Verdict.ALLOW
    assert decision.effective_tenant_id == "acme"


# --- 未知來源 ---


def test_r3_unknown_source_blocks() -> None:
    decision = evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="jwt_claim_guess", tenant_id="z")
    )
    assert decision.verdict == R3Verdict.BLOCK
    assert decision.block_reason == R3BlockReason.UNKNOWN_SOURCE
    assert decision.tenant_injected is False


# --- 旗標 ---


def test_r3_contract_flags() -> None:
    assert DOES_NOT_WIRE_REAL_AUTHGATE is True
    assert DOES_NOT_MUTATE_ADMIT_HOTPATH is True
    assert SHADOW_ONLY is True
    assert WIRE_CHANGE == "none"
    flags = contract_r3_flags()
    assert flags["contract_id"] == CONTRACT_ID
    assert flags["does_not_wire_real_authgate"] is True
    assert flags["does_not_mutate_admit_hotpath"] is True
    assert flags["shadow_only"] is True
    assert flags["ready_to_merge_product"] is False
    assert flags["wire_change"] == "none"
    assert flags["does_not_claim_injected"] is True
    assert "explicit" in flags["allowed_sources"]
    assert "http_body" in flags["allowed_sources"]
    assert "authgate_session" in flags["blocked_inject_sources"]


# --- shadow ---


def test_r3_shadow_records_evaluation() -> None:
    evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="authgate_session", would_inject_tenant="a")
    )
    evaluate_r3_tenant_inject(
        R3TenantInjectInput(source="explicit", tenant_id="acme")
    )
    log = r3_shadow_log()
    assert len(log) == 2
    assert all(row["mode"] == "shadow" for row in log)
    assert all(row["contract_id"] == CONTRACT_ID for row in log)
    assert log[0]["payload"]["verdict"] == R3Verdict.WOULD_INJECT_BLOCKED.value
    assert log[1]["payload"]["verdict"] == R3Verdict.ALLOW.value
    assert all(row["payload"]["tenant_injected"] is False for row in log)
