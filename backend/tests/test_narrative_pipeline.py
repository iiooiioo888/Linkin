"""Phase 5：敘事 RPG 一鍵管線測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.evaluation import DimensionResult, EvaluationResult
from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.tests.test_narrative_workspace_api import (
    BUILD_BRIEF_DRAFT,
    ITEM_DRAFT,
    NPC_DRAFT,
    QUEST_DRAFT,
)

VALID_GENERATE_PAYLOAD = {
    "story_arc": {
        "title": "靈丝残章",
        "summary": "旅人在織庭都追尋失落的織夢記憶。",
        "region": "织庭都",
        "chapters": ["序章"],
        "tags": ["主線"],
    },
    "quest": QUEST_DRAFT,
    "npc": NPC_DRAFT,
    "item": ITEM_DRAFT,
    "build_brief": BUILD_BRIEF_DRAFT,
}


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
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_MCP_AUDIT_PATH", str(tmp_path / "mcp_audit.jsonl"))
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

    def _fake_generate(**_kwargs):
        return {"drafts": VALID_GENERATE_PAYLOAD, "source": "llm", "keys": sorted(VALID_GENERATE_PAYLOAD)}

    monkeypatch.setattr("backend.linkin.narrative_pipeline.generate_narrative_drafts", _fake_generate)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _step_status(body: dict, step_id: str) -> str:
    for row in body["steps"]:
        if row["id"] == step_id:
            return row["status"]
    raise KeyError(step_id)


def test_pipeline_no_confirm_stops_before_world_writes(client: TestClient):
    resp = client.post(
        "/linkin/narrative/pipelines/run",
        json={
            "brief": "織庭都靈丝契約",
            "task_id": "task-pipe-1",
            "snapshot_id": "snap-pipe-1",
            "region": "织庭都",
            "confirm_world": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["needs_confirm"] is True
    assert body["confirm_world"] is False
    assert _step_status(body, "generate") == "ok"
    assert _step_status(body, "commit") == "ok"
    assert _step_status(body, "map_generate") == "ok"
    assert _step_status(body, "build_preview") == "ok"
    assert _step_status(body, "world_preview") == "ok"
    assert _step_status(body, "map_preview") == "ok"
    assert _step_status(body, "build_apply") == "skipped"
    assert _step_status(body, "world_apply") == "skipped"
    assert _step_status(body, "map_apply") == "skipped"
    assert body["plan"]["confirm_world_required"] is True


def test_pipeline_offline_dry_run_full_path(client: TestClient):
    phase1 = client.post(
        "/linkin/narrative/pipelines/run",
        json={
            "brief": "織庭都靈丝契約",
            "task_id": "task-pipe-2",
            "snapshot_id": "snap-pipe-2",
            "confirm_world": False,
        },
    ).json()
    ws_id = phase1["workspace_id"]

    phase2 = client.post(
        "/linkin/narrative/pipelines/run",
        json={
            "workspace_id": ws_id,
            "confirm_world": True,
            "regenerate": False,
        },
    )
    assert phase2.status_code == 200, phase2.text
    body = phase2.json()
    assert body["confirm_world"] is True
    assert _step_status(body, "generate") == "skipped"
    assert _step_status(body, "commit") == "skipped"
    assert _step_status(body, "build_apply") in {"ok", "partial"}
    assert _step_status(body, "world_apply") in {"ok", "partial"}
    assert _step_status(body, "map_apply") in {"ok", "partial"}
    assert body["bridge"]["enabled"] is False


def test_pipeline_partial_step_failure_reporting(client: TestClient, monkeypatch):
    def _fail_map(**_kwargs):
        from backend.linkin.map_plan import MapPlanError

        raise MapPlanError("測試地圖生成失敗", code="invalid_plan")

    monkeypatch.setattr("backend.linkin.narrative_pipeline.generate_map_plan", _fail_map)

    resp = client.post(
        "/linkin/narrative/pipelines/run",
        json={
            "brief": "織庭都測試",
            "task_id": "task-pipe-3",
            "snapshot_id": "snap-pipe-3",
            "confirm_world": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "error"
    assert _step_status(body, "map_generate") == "error"
    assert _step_status(body, "generate") == "ok"
    assert _step_status(body, "commit") == "ok"
    assert _step_status(body, "map_preview") == "skipped"


def test_pipeline_starter_pack_offline(client: TestClient, monkeypatch):
    from backend.linkin.narrative_generate import NarrativeGenerateError

    def _llm_unavailable(**_kwargs):
        raise NarrativeGenerateError("LLM 未配置", code="llm_unavailable")

    monkeypatch.setattr("backend.linkin.narrative_pipeline.generate_narrative_drafts", _llm_unavailable)
    resp = client.post(
        "/linkin/narrative/pipelines/run",
        json={
            "brief": "織庭都靈丝",
            "task_id": "task-pipe-4",
            "snapshot_id": "snap-pipe-4",
            "confirm_world": False,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert _step_status(body, "generate") == "partial"
    assert _step_status(body, "commit") in {"ok", "partial"}


def test_pipeline_steps_endpoint(client: TestClient):
    resp = client.get("/linkin/narrative/pipelines/steps")
    assert resp.status_code == 200
    steps = resp.json()["steps"]
    assert any(s["id"] == "generate" for s in steps)
    assert any(s["id"] == "map_apply" for s in steps)
