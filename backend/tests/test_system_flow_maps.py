"""系統流程 Archify IR 目錄與編譯。"""

from __future__ import annotations

import pytest

from backend.company.archify_compile import compile_ir, resolve_strategy_ir
from backend.company.system_flow_maps import (
    credit_pools_lifecycle_ir,
    deploy_topology_ir,
    langgraph_pipeline_ir,
    list_system_flow_ids,
    opc_six_stage_ir,
    raho_spine_ir,
    resolve_system_flow_ir,
    shared_pool_mining_ir,
    system_flow_catalog,
)


@pytest.mark.parametrize(
    ("builder", "diagram_type", "title_substr"),
    [
        (deploy_topology_ir, "architecture", "部署"),
        (langgraph_pipeline_ir, "workflow", "LangGraph"),
        (raho_spine_ir, "workflow", "RAHO"),
        (shared_pool_mining_ir, "lifecycle", "共享池"),
        (credit_pools_lifecycle_ir, "lifecycle", "積分池"),
        (opc_six_stage_ir, "workflow", "OPC"),
    ],
)
def test_each_catalog_ir_compiles(builder, diagram_type, title_substr):
    ir = builder()
    assert title_substr in ir["meta"]["title"]
    doc = compile_ir(ir)
    assert doc["diagram_type"] == diagram_type
    assert doc["meta"]["title"]


def test_resolve_system_flow_ir_and_aliases():
    deploy = resolve_system_flow_ir("system-deploy")
    assert deploy["meta"]["view"] == "system-deploy"
    assert any(n["id"] == "token_plan" for n in deploy["nodes"])

    evoloop = resolve_system_flow_ir("evoloop")
    assert any(n["id"] == "graph" for n in evoloop["nodes"])

    same = resolve_system_flow_ir("system")
    assert same["meta"]["title"] == evoloop["meta"]["title"]

    with pytest.raises(ValueError, match="未知系統流程"):
        resolve_system_flow_ir("not-a-flow")


def test_resolve_strategy_ir_system_views():
    langgraph = resolve_strategy_ir("langgraph")
    assert langgraph["meta"]["type"] == "workflow"
    assert any(n["id"] == "route" for n in langgraph["nodes"])

    pools = resolve_strategy_ir("credit-pools")
    assert "積分池" in pools["meta"]["title"]

    shared = resolve_strategy_ir("shared-pool")
    assert any(n["id"] == "reward" for n in shared["nodes"])


def test_system_flow_catalog():
    catalog = system_flow_catalog()
    assert catalog["ok"] is True
    ids = {row["id"] for row in catalog["flows"]}
    assert ids >= {
        "system-deploy",
        "langgraph",
        "raho",
        "shared-pool",
        "credit-pools",
        "opc",
        "evoloop",
    }
    assert catalog["default_view"] == "langgraph"
    for row in catalog["flows"]:
        assert row["title"]
        assert row["blurb"]
        assert row["diagram_type"]


def test_list_system_flow_ids():
    ids = list_system_flow_ids()
    assert "langgraph" in ids
    assert len(ids) >= 7
