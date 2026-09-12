"""Phase 4 區域 map_plan：schema、preview、generate fallback、apply confirm、dry-run。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.map_plan import (
    MAX_ESTIMATED_BLOCKS,
    MAX_PLOTS,
    MapPlanError,
    fallback_map_plan,
    gather_narrative_context,
    preview_map_plan,
    validate_map_plan,
)
from backend.linkin.narrative_registry import reset_narrative_registry


def _pass_eval(_query: str, _answer: str) -> EvaluationResult:
    result = EvaluationResult(source="test")
    for dim in ("accuracy", "completeness", "clarity", "relevance"):
        setattr(result, dim, DimensionResult(9.5, "ok"))
    result.overall = 9.5
    return result


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_LINKIN_NO_LLM", "1")
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    app = FastAPI()
    register_linkin(app)
    return TestClient(app)


def _sample_plan(**overrides) -> dict:
    base = fallback_map_plan(
        context=gather_narrative_context(
            workspace_drafts={
                "story_arc": {"title": "測試主線", "summary": "測試", "region": "织庭都"},
                "build_brief": {
                    "title": "測試廣場",
                    "region": "织庭都",
                    "location": "0,64,0",
                    "style": "织庭盟",
                    "prompt": "廣場",
                },
                "npc": {"name": "測試 NPC", "location": "织庭都"},
            },
            region="织庭都",
        ),
        seed="test-seed",
    )
    base.update(overrides)
    return base


def test_validate_map_plan_schema():
    plan = _sample_plan()
    validated = validate_map_plan(plan)
    assert validated["version"] == 1
    assert len(validated["plots"]) >= 2
    preview = preview_map_plan(validated)
    assert preview["plot_count"] == len(validated["plots"])
    assert preview["estimated_blocks"] <= MAX_ESTIMATED_BLOCKS
    assert preview["pois"]


def test_oversized_plot_count_rejected():
    plan = _sample_plan()
    plan["plots"] = [{"id": f"p{i}", "kind": "marker", "title": f"m{i}", "location": {"x": i, "y": 64, "z": 0}, "material": "STONE"} for i in range(MAX_PLOTS + 1)]
    with pytest.raises(MapPlanError) as exc:
        validate_map_plan(plan)
    assert exc.value.code == "plot_limit"


def test_oversized_blocks_rejected():
    plan = _sample_plan()
    plan["plots"] = [
        {
            "id": "big-terrain",
            "kind": "terrain",
            "title": "超大平台",
            "geometry": {
                "type": "fill",
                "x1": 0,
                "y1": 60,
                "z1": 0,
                "x2": 80,
                "y2": 60,
                "z2": 80,
                "material": "STONE",
            },
        }
    ]
    with pytest.raises(MapPlanError) as exc:
        validate_map_plan(plan)
    assert exc.value.code == "block_limit"


def test_map_generate_fallback(client: TestClient):
    ws = client.post("/linkin/narrative/workspaces", json={"task_id": "t-map", "snapshot_id": "snap-1"})
    assert ws.status_code == 200
    wid = ws.json()["workspace"]["workspace_id"]
    client.put(
        f"/linkin/narrative/workspaces/{wid}/drafts/story_arc",
        json={"value": {"title": "地圖測試", "summary": "摘要", "region": "织庭都"}},
    )
    client.put(
        f"/linkin/narrative/workspaces/{wid}/drafts/build_brief",
        json={
            "value": {
                "title": "序章廣場",
                "region": "织庭都",
                "location": "10,64,10",
                "style": "织庭盟",
                "prompt": "廣場",
            }
        },
    )
    resp = client.post("/linkin/map/generate", json={"workspace_id": wid, "seed": "phase4-seed"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "fallback"
    assert body["plan"]["id"]
    assert body["preview"]["plot_count"] >= 2
    assert body["preview"]["pois"]


def test_map_preview_no_writes(client: TestClient):
    plan = _sample_plan()
    resp = client.post("/linkin/map/preview", json={"plan": plan})
    assert resp.status_code == 200
    preview = resp.json()["preview"]
    assert preview["bounds"]
    assert preview["estimated_blocks"] > 0


def test_map_apply_requires_confirm(client: TestClient):
    plan = _sample_plan()
    denied = client.post("/linkin/map/apply", json={"plan": plan})
    assert denied.status_code == 409
    assert denied.json()["detail"]["code"] == "needs_confirmation"
    assert denied.json()["detail"]["preview"]["pois"]


def test_map_apply_dry_run(client: TestClient):
    plan = _sample_plan()
    resp = client.post("/linkin/map/apply", json={"plan": plan, "confirm": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body["minecraft"]["dry_run"] is True
    assert body["minecraft"]["ok"] is True
    assert body["status"] in {"complete", "partial"}
    assert body["plan"]["status"] in {"applied", "partial"}


def test_map_generate_via_module_gateway(client: TestClient, monkeypatch):
    from backend.modules import register_modules

    app = FastAPI()
    register_linkin(app)
    register_modules(app)
    gw = TestClient(app)
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", _pass_eval)
    resp = gw.post(
        "/modules/minecraft/api/map/generate",
        json={"region": "织庭都", "seed": "gw-seed"},
    )
    assert resp.status_code == 200
    assert resp.json()["preview"]["region"] == "织庭都"
