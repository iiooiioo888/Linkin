"""任務進度運行時單元與 API 測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store, upsert_entity
from backend.linkin.minecraft_ai_gm import apply_gm_actions, reset_gm_state
from backend.linkin.minecraft_observability import reset_minecraft_events
from backend.linkin.minecraft_players import reset_player_state
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.quest_runtime import (
    QUEST_STATUS_ACTIVE,
    QUEST_STATUS_COMPLETED,
    apply_quest_progress,
    evaluate_heuristics,
    list_quest_progress,
    reset_quest_progress,
)


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()
    reset_gm_state()
    reset_quest_progress()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()
    reset_gm_state()
    reset_quest_progress()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", lambda *_a, **_k: None)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _sample_quest(quest_id: str = "quest-rt1") -> dict:
    return {
        "id": quest_id,
        "title": "測試任務",
        "player_id": "steve",
        "quest_type": "支线",
        "difficulty": "普通",
        "region": "织庭都",
        "description": "測試描述",
        "objectives": [
            {"id": "obj-a", "title": "步驟 A"},
            {"id": "obj-b", "title": "步驟 B"},
        ],
    }


def test_apply_advance_objective(linkin_env):
    upsert_entity("quests", _sample_quest())
    r1 = apply_quest_progress(
        player_id="Steve",
        quest_id="quest-rt1",
        objective_id="obj-a",
        status="advance",
        note="完成 A",
    )
    assert r1["ok"] is True
    assert r1["status"] == "applied"
    assert r1["quest_status"] == QUEST_STATUS_ACTIVE

    rows = list_quest_progress(player_id="steve", quest_id="quest-rt1")
    assert len(rows) == 1
    assert rows[0]["objectives_done"] == 1
    assert rows[0]["objectives_total"] == 2


def test_apply_complete_all_objectives(linkin_env):
    upsert_entity("quests", _sample_quest())
    apply_quest_progress(player_id="steve", quest_id="quest-rt1", objective_id="obj-a", status="advance")
    r2 = apply_quest_progress(player_id="steve", quest_id="quest-rt1", objective_id="obj-b", status="advance")
    assert r2["ok"] is True
    assert r2["quest_status"] == QUEST_STATUS_COMPLETED

    rows = list_quest_progress(player_id="steve", status=QUEST_STATUS_COMPLETED)
    assert len(rows) == 1


def test_apply_invalid_quest_id(linkin_env):
    result = apply_quest_progress(player_id="steve", quest_id="missing-quest", objective_id="obj-a")
    assert result["ok"] is False
    assert result["reason"] == "quest_not_found"


def test_apply_invalid_objective_id(linkin_env):
    upsert_entity("quests", _sample_quest())
    result = apply_quest_progress(
        player_id="steve",
        quest_id="quest-rt1",
        objective_id="obj-invalid",
        status="advance",
    )
    assert result["ok"] is False
    assert result["reason"] == "invalid_objective_id"
    assert "obj-a" in result.get("valid_objectives", [])


def test_apply_dry_run(linkin_env):
    upsert_entity("quests", _sample_quest())
    result = apply_quest_progress(
        player_id="steve",
        quest_id="quest-rt1",
        objective_id="obj-a",
        dry_run=True,
    )
    assert result["ok"] is True
    assert result["status"] == "dry_run"
    assert list_quest_progress() == []


def test_gm_apply_quest_progress_integration(linkin_env):
    upsert_entity("quests", _sample_quest())
    results = apply_gm_actions(
        [
            {
                "type": "quest_progress",
                "quest_id": "quest-rt1",
                "objective": "obj-a",
                "status": "advance",
                "note": "gm note",
            }
        ],
        dry_run=False,
        auto_apply=True,
        trigger_event={
            "id": "mcevt-test1",
            "entity_refs": {"player_id": "steve", "player_name": "Steve"},
        },
    )
    assert results[0]["ok"] is True
    assert results[0]["status"] == "applied"
    rows = list_quest_progress(player_id="steve")
    assert len(rows) == 1
    assert rows[0]["last_event_id"] == "mcevt-test1"


def test_heuristics_chat_keyword(linkin_env):
    upsert_entity("quests", _sample_quest())
    apply_quest_progress(player_id="steve", quest_id="quest-rt1", objective_id="obj-a", status="advance")
    event = {
        "action": "chat",
        "entity_refs": {"player_id": "steve"},
        "details": {"message": "我在做測試任務"},
    }
    hints = evaluate_heuristics(event)
    assert any(h.get("signal") == "chat_keyword" for h in hints)


def test_api_apply_and_list(client: TestClient, linkin_env):
    upsert_entity("quests", _sample_quest())

    apply_res = client.post(
        "/linkin/minecraft/quests/progress/apply",
        json={
            "player_id": "steve",
            "quest_id": "quest-rt1",
            "objective_id": "obj-a",
            "status": "advance",
            "note": "via api",
        },
    )
    assert apply_res.status_code == 200
    body = apply_res.json()
    assert body["ok"] is True

    list_res = client.get("/linkin/minecraft/quests/progress?player_id=steve")
    assert list_res.status_code == 200
    assert list_res.json()["count"] == 1

    summary_res = client.get("/linkin/minecraft/quests/progress/summary")
    assert summary_res.status_code == 200
    assert summary_res.json()["active"] >= 1


def test_api_invalid_quest(client: TestClient):
    res = client.post(
        "/linkin/minecraft/quests/progress/apply",
        json={"player_id": "steve", "quest_id": "nope", "objective_id": "obj-a"},
    )
    assert res.status_code == 200
    assert res.json()["ok"] is False
    assert res.json()["reason"] == "quest_not_found"


def test_ai_context_includes_quest_progress(client: TestClient, linkin_env):
    upsert_entity("quests", _sample_quest())
    apply_quest_progress(player_id="steve", quest_id="quest-rt1", objective_id="obj-a", status="advance")

    res = client.get("/linkin/minecraft/ai/context?max_chars=12000")
    assert res.status_code == 200
    ctx = res.json()["context"]
    assert "任務進度" in ctx
    assert "測試任務" in ctx
