"""階段 0 契約：路徑相容、護欄必填、同步深度、依賴方向。"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

import pytest
from pydantic import ValidationError

from linkin_core.boundaries import forbidden_imports
from linkin_core.contracts.asyncapi_doc import build_asyncapi, event_names
from linkin_core.contracts.events import EventName
from linkin_core.contracts.export import artifacts
from linkin_core.contracts.minecraft import MinecraftActionRequest
from linkin_core.contracts.opc import OpcWriteRequest
from linkin_core.contracts.openapi_doc import build_openapi
from linkin_core.contracts.route import (
    RULE_CHAIN,
    CompatibleStrategy,
    ExecutionPathName,
    RoutePreviewRequest,
    RuleHit,
    normalize_execution_path,
)
from linkin_core.contracts.slo import MAX_SYNC_HOPS
from linkin_core.contracts.topology import (
    DEFAULT_SERVICES,
    SYNC_CHAINS,
    assert_sync_budget,
    seat_executor_targets,
)


def test_rule_chain_order():
    assert [item.value for item in RULE_CHAIN] == [
        "industrial",
        "linkin_complex",
        "mine_multi_step",
        "mine_single_step",
        "cost_speed",
        "company_keyword",
        "length",
        "fallback_simple",
    ]


def test_legacy_opc_path_is_company():
    assert normalize_execution_path("opc") is ExecutionPathName.company
    assert normalize_execution_path("minecraft_ops") is ExecutionPathName.minecraft_ops


def test_manual_route_requires_path():
    with pytest.raises(ValidationError):
        RoutePreviewRequest(query="看溫度", strategy=CompatibleStrategy.manual, tenant_id="acme")
    row = RoutePreviewRequest(
        query="看溫度",
        strategy=CompatibleStrategy.simple,
        tenant_id="acme",
    )
    assert row.strategy is CompatibleStrategy.simple


def test_opc_write_requires_guardrail_decision():
    with pytest.raises(ValidationError):
        OpcWriteRequest(node_id="ns=2;s=Valve", value=1, tenant_id="acme", trace_id="trace-1")


def test_dangerous_minecraft_action_requires_guardrail():
    with pytest.raises(ValidationError):
        MinecraftActionRequest(
            server_id="srv",
            session_id="sess",
            action="execute_command",
            tenant_id="acme",
            trace_id="trace-1",
        )
    ok = MinecraftActionRequest(
        server_id="srv",
        session_id="sess",
        action="get_player",
        tenant_id="acme",
        trace_id="trace-1",
    )
    assert ok.guardrail_decision_id is None


def test_sync_chains_stay_within_budget():
    assert_sync_budget()
    assert all(len(chain) <= MAX_SYNC_HOPS for chain in SYNC_CHAINS.values())
    assert seat_executor_targets() == {"tool-gateway", "nats"}
    assert "opc-service" not in seat_executor_targets()
    assert len(DEFAULT_SERVICES) == 12


def test_openapi_and_asyncapi_cover_the_locked_surface():
    spec = build_openapi()
    paths = spec["paths"]
    for path in (
        "/api/v1/route-preview",
        "/api/v1/chat/stream",
        "/api/v1/tasks",
        "/api/v1/tasks/{task_id}",
        "/api/v1/tools/{tool}/invoke",
        "/api/v1/guardrail/check",
        "/api/v1/guardrail/approve",
        "/api/v1/opc/read",
        "/api/v1/opc/write-request",
        "/api/v1/minecraft/action",
        "/chat",
        "/tasks",
    ):
        assert path in paths
    assert "get" in paths["/api/v1/opc/read"]
    assert paths["/api/v1/tools/{tool}/invoke"]["post"]["x-linkin-visibility"] == "internal"
    assert paths["/chat"]["post"]["deprecated"] is True
    events = build_asyncapi()["channels"]
    for name in event_names():
        assert name in events
    assert set(event_names()) == {item.value for item in EventName}


def test_checked_in_artifacts_match_builder():
    for path, text in artifacts().items():
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8") == text


def test_k8s_skeleton_keeps_write_path_on_guardrail():
    root = ROOT / "deploy" / "k8s" / "linkin"
    policy = (root / "networkpolicies.yaml").read_text(encoding="utf-8")
    workloads = (root / "workloads.yaml").read_text(encoding="utf-8")
    assert "port: 8081" in policy
    assert "allow-in-opc-service" in policy
    assert "allow-out-seat-executor" in policy
    for name in DEFAULT_SERVICES:
        assert f"name: {name}" in workloads
    assert "/healthz" in workloads
    assert "/readyz" in workloads
    ingress = (root / "ingress.yaml").read_text(encoding="utf-8")
    assert "nginx-internal" in ingress
    assert "linkin.internal" in ingress


def test_contracts_do_not_import_runtime():
    assert forbidden_imports() == []


def test_runtime_doc_order_matches_rule_chain():
    text = (ROOT / "backend/core/execution_path.py").read_text(encoding="utf-8")
    positions = [
        text.index("工業關鍵詞"),
        text.index("靈境複雜任務"),
        text.index("Minecraft 重型"),
        text.index("Minecraft 單步"),
        text.index("cost_speed"),
        text.index("關鍵詞／長度規則"),
    ]
    assert positions == sorted(positions)
    assert RuleHit.company_keyword in RULE_CHAIN
    assert RuleHit.length in RULE_CHAIN


def test_openapi_json_is_sorted():
    payload = json.loads((ROOT / "linkin_core/contracts/openapi.json").read_text(encoding="utf-8"))
    assert payload["openapi"] == "3.1.0"
    assert payload["paths"]["/api/v1/route-preview"]["post"]["requestBody"]
