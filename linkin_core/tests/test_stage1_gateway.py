"""階段 1：工具與護欄入口、簽章、雙跑與繞過拒絕。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from guardrail_service import approve_decision, check_decision
from guardrail_service import reset_state as reset_guard
from minecraft_gateway import app as minecraft_app
from tool_gateway import reset_state as reset_tools
from tool_gateway import should_sample

from linkin_core.contracts.signatures import issue_token, verify_token
from linkin_core.contracts.topology import ALLOW, SYNC_CHAINS
from opc_service.write_port import app as opc_write_app


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("LINKIN_GUARDRAIL_HMAC_KEY", "stage1-test-key")
    monkeypatch.setenv("TOOL_GATEWAY_RATE_LIMIT", "0")
    reset_guard()
    reset_tools()
    yield
    reset_guard()
    reset_tools()


def test_sampling_defaults():
    assert should_sample("place_block", rng=lambda: 0.99) is True
    assert should_sample("echo", rng=lambda: 0.5) is False
    assert should_sample("echo", rng=lambda: 0.05) is True


def test_opc_write_needs_approval_then_signature_opens_port():
    row = check_decision(
        tool="opc_write",
        args={"node_id": "ns=2;s=Temperature", "value": 40.0},
        tenant_id="acme",
        trace_id="trace-1",
        caller="tool-gateway",
    )
    assert row["verdict"] == "confirm"
    client = TestClient(opc_write_app)
    denied = client.post(
        "/api/v1/opc/write-request",
        json={"node_id": "ns=2;s=Temperature", "value": 40, "tenant_id": "acme", "trace_id": "trace-1"},
    )
    assert denied.json()["ok"] is False
    approved = approve_decision(
        decision_id=row["decision_id"],
        approved=True,
        approver="ops",
        tenant_id="acme",
        trace_id="trace-2",
        caller="api-gateway",
    )
    claims = verify_token(approved["token"])
    assert claims["verdict"] == "allow"
    # 審批簽的是原參數雜湊；寫入埠要同一組參數。
    opened = client.post(
        "/api/v1/opc/write-request",
        json={
            "node_id": "ns=2;s=Temperature",
            "value": 40.0,
            "tenant_id": "acme",
            "trace_id": "trace-2",
            "guardrail_token": approved["token"],
        },
    )
    assert opened.json()["ok"] is True


def test_hot_opc_write_is_denied():
    row = check_decision(
        tool="opc_write",
        args={"node_id": "Temperature", "value": 400},
        tenant_id="acme",
        trace_id="trace-hot",
        caller="tool-gateway",
    )
    assert row["verdict"] == "deny"


def test_minecraft_sensitive_without_token_is_rejected():
    client = TestClient(minecraft_app)
    resp = client.post(
        "/api/v1/minecraft/action",
        json={
            "action": "execute_command",
            "args": {"command": "ban Steve"},
            "tenant_id": "acme",
            "trace_id": "trace-mc",
        },
    )
    assert resp.json()["ok"] is False
    banned = check_decision(
        tool="execute_command",
        args={"command": "ban Steve"},
        tenant_id="acme",
        trace_id="trace-mc",
        caller="tool-gateway",
    )
    assert banned["verdict"] == "deny"


def test_check_rejects_other_callers():
    with pytest.raises(PermissionError):
        check_decision(
            tool="opc_write",
            args={"node_id": "Valve", "value": 1},
            tenant_id="acme",
            trace_id="trace-x",
            caller="seat-executor",
        )


def test_tampered_token_is_rejected():
    token = issue_token(
        {
            "decision_id": "gd_test",
            "verdict": "allow",
            "policy_version": "2026-10-26",
            "tenant_id": "acme",
            "trace_id": "trace-1",
            "tool": "opc_write",
            "args_hash": "abc",
            "exp": 9_999_999_999,
            "schema_version": "1.0.0",
        }
    )
    broken = token[:-1] + ("0" if token[-1] != "0" else "1")
    with pytest.raises(ValueError):
        verify_token(broken)


def test_stage1_edges_match_the_locked_chains():
    assert ("context-service", "tool-gateway", 8080) in ALLOW
    assert ("context-service", "opc-service", 8080) not in ALLOW
    assert ("tool-gateway", "opc-service", 8080) in ALLOW
    assert ("guardrail-service", "opc-service", 8081) in ALLOW
    assert ("seat-executor", "opc-service", 8081) not in ALLOW
    assert len(SYNC_CHAINS["opc_read"]) <= 3
    assert len(SYNC_CHAINS["opc_write"]) <= 3
    assert len(SYNC_CHAINS["minecraft_sensitive"]) <= 3
