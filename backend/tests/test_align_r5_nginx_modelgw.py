"""Align R5：nginx /modelgw 暴露與雙電路共享邊界契約測試。

對表 #148 §5／align-spec §10.1 R5／G-X1；非真改 nginx／compose。
"""

from __future__ import annotations

import pytest

from backend.core.align_r5_nginx_modelgw import (
    CONTRACT_ID,
    DOES_NOT_MODIFY_NGINX,
    DOES_NOT_WIRE_DUAL_CIRCUIT,
    GX1_INFRA_SEPARATE_TICKET,
    ORTHOGONAL_TO_ALIGN,
    SHADOW_ONLY,
    WIRE_CHANGE,
    R5BlockReason,
    R5ModelgwIngressInput,
    R5Verdict,
    contract_r5_flags,
    evaluate_r5_modelgw_ingress,
    r5_shadow_log,
    reset_r5_shadow_log,
)


@pytest.fixture(autouse=True)
def _clear_shadow() -> None:
    reset_r5_shadow_log()
    yield
    reset_r5_shadow_log()


# --- docs／契約觀測 → allow（永不改 nginx） ---


def test_r5_docs_observe_allows() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="docs_observe", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.ALLOW
    assert decision.block_reason == R5BlockReason.NONE
    assert decision.audit_event == "modelgw.r5.ingress.docs_observe_ok"
    assert decision.nginx_modified is False
    assert decision.dual_circuit_wired is False
    assert decision.intent_normalized == "docs_observe"


def test_r5_contract_eval_allows() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="contract_eval", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.ALLOW
    assert decision.nginx_modified is False
    assert decision.dual_circuit_wired is False
    assert decision.intent_normalized == "contract_eval"


# --- 暴露 /modelgw → orthogonal_deferred；shadow would_expose ---


def test_r5_expose_modelgw_orthogonal_deferred() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(
            intent="expose_modelgw_location",
            infra_auth_flag=True,
            would_expose_path="/modelgw",
        )
    )
    assert decision.verdict == R5Verdict.ORTHOGONAL_DEFERRED
    assert decision.block_reason == R5BlockReason.EXPOSE_MODELGW
    assert decision.audit_event == "modelgw.r5.ingress.orthogonal_deferred"
    assert decision.nginx_modified is False
    log = r5_shadow_log()
    assert len(log) == 1
    assert log[0]["payload"]["would_expose"] == "/modelgw"
    assert log[0]["payload"]["nginx_modified"] is False


def test_r5_nginx_location_open_deferred() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="nginx_location_open", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.ORTHOGONAL_DEFERRED
    assert decision.block_reason == R5BlockReason.EXPOSE_MODELGW
    assert decision.nginx_modified is False
    log = r5_shadow_log()
    assert log[0]["payload"]["would_expose"] == "/modelgw"


# --- 雙電路共享 → would_share_dual_circuit ---


def test_r5_share_dual_circuit_blocked() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(
            intent="share_dual_circuit",
            infra_auth_flag=True,
            would_share_circuits=("unit_bus", "modelgw"),
        )
    )
    assert decision.verdict == R5Verdict.WOULD_SHARE_DUAL_CIRCUIT
    assert decision.block_reason == R5BlockReason.DUAL_CIRCUIT
    assert decision.audit_event == "modelgw.r5.ingress.would_share_dual_circuit"
    assert decision.dual_circuit_wired is False
    assert decision.nginx_modified is False
    log = r5_shadow_log()
    assert log[0]["payload"]["would_share_dual_circuit"] == ["unit_bus", "modelgw"]
    assert log[0]["payload"]["dual_circuit_wired"] is False


def test_r5_dual_circuit_merge_blocked() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="dual_circuit_merge", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.WOULD_SHARE_DUAL_CIRCUIT
    assert decision.block_reason == R5BlockReason.DUAL_CIRCUIT
    assert decision.dual_circuit_wired is False
    log = r5_shadow_log()
    assert log[0]["payload"]["would_share_dual_circuit"] is True


# --- 缺 infra 授權 fail-closed ---


def test_r5_missing_infra_auth_blocks_even_docs() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="docs_observe", infra_auth_flag=False)
    )
    assert decision.verdict == R5Verdict.BLOCK
    assert decision.block_reason == R5BlockReason.MISSING_INFRA_AUTH
    assert decision.audit_event == "modelgw.r5.ingress.missing_infra_auth"
    assert decision.nginx_modified is False


def test_r5_missing_infra_auth_blocks_expose() -> None:
    """缺授權優先於暴露意圖（fail-closed）。"""
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="expose_modelgw_location", infra_auth_flag=False)
    )
    assert decision.verdict == R5Verdict.BLOCK
    assert decision.block_reason == R5BlockReason.MISSING_INFRA_AUTH
    assert decision.nginx_modified is False


# --- 未知／缺意圖 ---


def test_r5_unknown_intent_blocks() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="rewrite_nginx_conf", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.BLOCK
    assert decision.block_reason == R5BlockReason.UNKNOWN_INTENT
    assert decision.nginx_modified is False


def test_r5_missing_intent_with_auth_blocks() -> None:
    decision = evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="", infra_auth_flag=True)
    )
    assert decision.verdict == R5Verdict.BLOCK
    assert decision.block_reason == R5BlockReason.UNKNOWN_INTENT
    assert decision.intent_normalized == "missing"


# --- 旗標 ---


def test_r5_contract_flags() -> None:
    assert DOES_NOT_MODIFY_NGINX is True
    assert DOES_NOT_WIRE_DUAL_CIRCUIT is True
    assert SHADOW_ONLY is True
    assert GX1_INFRA_SEPARATE_TICKET is True
    assert ORTHOGONAL_TO_ALIGN is True
    assert WIRE_CHANGE == "none"
    flags = contract_r5_flags()
    assert flags["contract_id"] == CONTRACT_ID
    assert flags["does_not_modify_nginx"] is True
    assert flags["does_not_wire_dual_circuit"] is True
    assert flags["shadow_only"] is True
    assert flags["gx1_infra_separate_ticket"] is True
    assert flags["ready_to_merge_product"] is False
    assert flags["wire_change"] == "none"
    assert flags["orthogonal_to_align"] is True
    assert flags["does_not_claim_nginx_changed"] is True
    assert "docs_observe" in flags["allowed_intents"]
    assert "contract_eval" in flags["allowed_intents"]
    assert "expose_modelgw_location" in flags["blocked_expose_intents"]
    assert "share_dual_circuit" in flags["blocked_dual_intents"]


# --- shadow ---


def test_r5_shadow_records_evaluation() -> None:
    evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="expose_modelgw_location", infra_auth_flag=True)
    )
    evaluate_r5_modelgw_ingress(
        R5ModelgwIngressInput(intent="docs_observe", infra_auth_flag=True)
    )
    log = r5_shadow_log()
    assert len(log) == 2
    assert all(row["mode"] == "shadow" for row in log)
    assert all(row["contract_id"] == CONTRACT_ID for row in log)
    assert log[0]["payload"]["verdict"] == R5Verdict.ORTHOGONAL_DEFERRED.value
    assert log[1]["payload"]["verdict"] == R5Verdict.ALLOW.value
    assert all(row["payload"]["nginx_modified"] is False for row in log)
    assert all(row["payload"]["dual_circuit_wired"] is False for row in log)
