"""Native 2D layout preview normalization."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.knowledge import reset_store, upsert_entity
from backend.linkin.layout_preview import (
    build_layout_preview,
    normalize_build_brief_features,
    normalize_plot_features,
    normalize_world_intent_features,
)
from backend.linkin.map_plan import fallback_map_plan, gather_narrative_context
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.constitution import reset_cache as reset_constitution_cache


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
def client(linkin_env):
    app = FastAPI()
    register_linkin(app)
    return TestClient(app)


def _sample_plan() -> dict:
    return fallback_map_plan(
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
        seed="layout-test-seed",
    )


def test_normalize_plot_features_from_map_plan():
    plan = _sample_plan()
    features = normalize_plot_features(plan)
    kinds = {f["kind"] for f in features}
    assert "poi" in kinds
    assert "path" in kinds
    assert "terrain" in kinds
    points = [f for f in features if f["type"] == "point"]
    assert points
    for feat in features:
        assert feat["source"] == "map_plan"
        assert feat["label"] in {"planned", "applied", "partial"}


def test_normalize_build_brief_synthetic_footprint():
    briefs = [
        {
            "id": "bb-1",
            "title": "無座標廣場",
            "region": "织庭都",
            "location": "织庭都",
            "block_count": 400,
            "status": "pending_builder",
        }
    ]
    features = normalize_build_brief_features(briefs, seed="seed-1", hub=(0, 64, 0))
    assert len(features) == 1
    rect = features[0]["rect"]
    assert rect["x2"] > rect["x1"]
    assert features[0]["meta"]["footprint_estimate"] is True
    assert features[0]["meta"]["layout_mode"] == "synthetic"


def test_normalize_build_brief_absolute_location():
    briefs = [{"id": "bb-2", "title": "有座標", "location": "10,64,20", "block_count": 100}]
    features = normalize_build_brief_features(briefs, seed="seed-2")
    rect = features[0]["rect"]
    assert rect["x1"] <= 10 <= rect["x2"]
    assert rect["z1"] <= 20 <= rect["z2"]
    assert features[0]["meta"]["layout_mode"] == "absolute"


def test_normalize_world_intent_npc_synthetic():
    npcs = [{"id": "npc-1", "name": "青禾", "location": "织庭都", "world_status": "pending_world"}]
    features = normalize_world_intent_features(npcs, seed="npc-seed", hub=(0, 64, 0))
    assert features[0]["type"] == "point"
    assert features[0]["kind"] == "npc_intent"
    assert features[0]["meta"]["layout_mode"] == "synthetic"


def test_build_layout_preview_composes_entities(linkin_env):
    plan = _sample_plan()
    upsert_entity("map_plans", {**plan, "status": "planned"})
    upsert_entity(
        "build_briefs",
        {
            "id": "bb-extra",
            "title": "側翼塔",
            "region": plan["region"],
            "location": "20,64,30",
            "block_count": 200,
            "status": "pending_builder",
        },
    )
    preview = build_layout_preview()
    assert preview["ok"] is True
    assert preview["has_map_plan"] is True
    assert preview["counts"]["total"] > 0
    assert preview["bounds"]["x2"] > preview["bounds"]["x1"]
    assert preview["layout_summary"]["feature_count"] == preview["counts"]["total"]


def test_build_layout_preview_empty(linkin_env):
    preview = build_layout_preview()
    assert preview["empty"] is True
    assert preview["features"] == []


def test_layout_preview_api(client, linkin_env):
    plan = _sample_plan()
    upsert_entity("map_plans", {**plan, "status": "planned"})
    res = client.get("/linkin/minecraft/layout-preview")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["has_map_plan"] is True
    assert len(body["features"]) > 0
