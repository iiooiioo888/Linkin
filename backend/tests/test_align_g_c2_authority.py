"""Align G-C2：DeliveryClaimAuthority vs O10MergeAuthority 分票契約測試。

對表 #148／#140；不合並產品碼波；不測餵線實作。
"""

from __future__ import annotations

from collections.abc import Generator

import pytest

from backend.core.align_g_c2_authority import (
    CONTRACT_ID,
    AuthorityKind,
    DeliveryBlockReason,
    DeliveryClaimInput,
    DeliveryUnitStatus,
    O10MergeDecisionKind,
    O10MergeInput,
    authorities_are_distinct,
    authority_shadow_log,
    conflation_rejected,
    evaluate_delivery_claim,
    evaluate_o10_merge,
    map_authorities_not_merge,
    reset_authority_shadow_log,
)


@pytest.fixture(autouse=True)
def _clear_shadow() -> Generator[None, None, None]:
    reset_authority_shadow_log()
    yield
    reset_authority_shadow_log()


# --- 兩權分離 ---


def test_g_c2_authorities_are_distinct() -> None:
    assert authorities_are_distinct()
    assert AuthorityKind.DELIVERY_CLAIM is not AuthorityKind.O10_MERGE
    assert AuthorityKind.DELIVERY_CLAIM.value != AuthorityKind.O10_MERGE.value


def test_g_c2_conflation_rejected_across_kinds() -> None:
    assert conflation_rejected(AuthorityKind.DELIVERY_CLAIM, AuthorityKind.O10_MERGE)
    assert not conflation_rejected(AuthorityKind.DELIVERY_CLAIM, AuthorityKind.DELIVERY_CLAIM)


def test_g_c2_map_not_merge_keeps_two_axes() -> None:
    delivery = evaluate_delivery_claim(
        DeliveryClaimInput(has_valid_diff=True, scan_passed=True, delivery_infra_ok=True)
    )
    o10 = evaluate_o10_merge(O10MergeInput(verification_passed=True))
    mapped = map_authorities_not_merge(delivery, o10)
    assert mapped["map_not_merge"] is True
    assert mapped["contract_id"] == CONTRACT_ID
    assert mapped["does_not_implement_feedline"] is True
    assert mapped["ready_to_merge_product"] is False
    assert mapped["delivery_claim"]["authority"] == AuthorityKind.DELIVERY_CLAIM.value
    assert mapped["o10_merge"]["authority"] == AuthorityKind.O10_MERGE.value
    assert mapped["delivery_claim"]["authority"] != mapped["o10_merge"]["authority"]


# --- 空 diff／scan 擋不得標 Delivery succeeded ---


def test_g_c2_empty_diff_cannot_claim_delivery_succeeded() -> None:
    decision = evaluate_delivery_claim(DeliveryClaimInput(has_valid_diff=False, scan_passed=True))
    assert decision.allowed_to_claim_delivery is False
    assert decision.unit_status != DeliveryUnitStatus.SUCCEEDED
    assert decision.unit_status == DeliveryUnitStatus.FAILED
    assert decision.block_reason == DeliveryBlockReason.EMPTY_DIFF
    assert decision.audit_event == "code_ops.diff.empty"
    assert "succeeded" not in decision.audit_event


def test_g_c2_scan_blocked_cannot_claim_delivery_succeeded() -> None:
    decision = evaluate_delivery_claim(DeliveryClaimInput(has_valid_diff=True, scan_passed=False))
    assert decision.allowed_to_claim_delivery is False
    assert decision.unit_status == DeliveryUnitStatus.BLOCKED
    assert decision.block_reason == DeliveryBlockReason.SCAN_BLOCKED
    assert decision.audit_event == "code_ops.scan.blocked"
    assert decision.unit_status != DeliveryUnitStatus.SUCCEEDED


def test_g_c2_sandbox_abort_and_draft_cancel_fail_closed() -> None:
    aborted = evaluate_delivery_claim(
        DeliveryClaimInput(has_valid_diff=True, scan_passed=True, sandbox_aborted=True)
    )
    assert aborted.unit_status == DeliveryUnitStatus.ABORTED
    assert aborted.allowed_to_claim_delivery is False

    cancelled = evaluate_delivery_claim(
        DeliveryClaimInput(has_valid_diff=True, scan_passed=True, draft_cancelled=True)
    )
    assert cancelled.unit_status == DeliveryUnitStatus.CANCELLED
    assert cancelled.allowed_to_claim_delivery is False


def test_g_c2_happy_path_allows_delivery_claim_only() -> None:
    decision = evaluate_delivery_claim(
        DeliveryClaimInput(has_valid_diff=True, scan_passed=True, delivery_infra_ok=True)
    )
    assert decision.allowed_to_claim_delivery is True
    assert decision.unit_status == DeliveryUnitStatus.SUCCEEDED
    assert decision.audit_event == "code_ops.delivery.succeeded"
    assert decision.authority == AuthorityKind.DELIVERY_CLAIM


# --- O10 獨立：Delivery succeeded ≠ 自動合入 ---


def test_g_c2_delivery_success_does_not_imply_o10_merge() -> None:
    delivery = evaluate_delivery_claim(
        DeliveryClaimInput(has_valid_diff=True, scan_passed=True, delivery_infra_ok=True)
    )
    assert delivery.allowed_to_claim_delivery is True

    o10 = evaluate_o10_merge(
        O10MergeInput(
            verification_passed=False,
            delivery_claimed_succeeded=True,
        )
    )
    assert o10.authority == AuthorityKind.O10_MERGE
    assert o10.delivery_success_implies_merge is False
    assert o10.decision == O10MergeDecisionKind.DENY_MERGE
    assert "despite_delivery_claim" in o10.reason


def test_g_c2_o10_allow_requires_verification() -> None:
    o10 = evaluate_o10_merge(O10MergeInput(verification_passed=True))
    assert o10.decision == O10MergeDecisionKind.ALLOW_MERGE
    assert o10.delivery_success_implies_merge is False


# --- shadow 記錄 ---


def test_g_c2_shadow_records_both_authorities() -> None:
    evaluate_delivery_claim(DeliveryClaimInput())
    evaluate_o10_merge(O10MergeInput())
    log = authority_shadow_log()
    assert len(log) == 2
    kinds = {row["authority"] for row in log}
    assert kinds == {
        AuthorityKind.DELIVERY_CLAIM.value,
        AuthorityKind.O10_MERGE.value,
    }
    assert all(row["mode"] == "shadow" for row in log)
    assert all(row["contract_id"] == CONTRACT_ID for row in log)
