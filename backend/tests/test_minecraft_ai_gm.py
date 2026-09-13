"""Minecraft AI GM 單元與 API 測試。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store, upsert_entity
from backend.linkin.minecraft_ai_gm import (
    apply_gm_actions,
    decide_gm_actions,
    react_to_event,
    reset_gm_state,
    update_gm_config,
    validate_gm_actions,
)
from backend.linkin.minecraft_observability import (
    append_minecraft_event,
    list_minecraft_events,
    reset_minecraft_events,
)
from backend.linkin.minecraft_players import reset_player_state
from backend.linkin.narrative_registry import reset_narrative_registry


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_LINKIN_NO_LLM", "1")
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()
    reset_gm_state()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()
    reset_gm_state()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", lambda *_a, **_k: None)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _player_event(action: str = "chat", player: str = "Steve") -> dict:
    return append_minecraft_event(
        domain="player",
        action=action,
        status="ok",
        summary=f"{player} 說了話",
        entity_refs={"player_id": player.lower(), "player_name": player},
        details={"message": "hello"},
    )


def test_validate_gm_actions_filters_unsafe():
    raw = [
        {"type": "npc_say", "message": "hi"},
        {"type": "place_block", "block": "TNT"},
        {"type": "quest_progress", "quest_id": "q1", "status": "advance"},
        {"type": "destroy", "blocks": 1000},
    ]
    safe = validate_gm_actions(raw, max_actions=5)
    types = {a["type"] for a in safe}
    assert types == {"npc_say", "quest_progress"}
    assert len(safe) <= 3


def test_validate_gm_actions_max_limit():
    actions = [{"type": "hint", "message": f"h{i}"} for i in range(10)]
    safe = validate_gm_actions(actions, max_actions=2)
    assert len(safe) == 2


def test_apply_gm_actions_dry_run_quest(linkin_env):
    upsert_entity(
        "quests",
        {
            "id": "quest-test1",
            "title": "測試任務",
            "player_id": "steve",
            "description": "desc",
        },
    )
    results = apply_gm_actions(
        [{"type": "quest_progress", "quest_id": "quest-test1", "status": "advance", "note": "n"}],
        dry_run=True,
        auto_apply=False,
        trigger_event={
            "id": "mcevt-dry",
            "entity_refs": {"player_id": "steve", "player_name": "Steve"},
        },
    )
    assert results[0]["status"] == "dry_run"


def test_apply_gm_actions_npc_say_log_only(linkin_env, monkeypatch):
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {"enabled": False, "connected": False, "dry_run": True},
    )
    results = apply_gm_actions(
        [{"type": "npc_say", "npc_name": "村長", "message": "歡迎"}],
        dry_run=False,
        auto_apply=True,
    )
    assert results[0]["status"] == "log_only"
    assert results[0].get("bridge_offline") is True


def test_react_cooldown(linkin_env):
    update_gm_config({"enabled": True, "dry_run": True, "cooldown_seconds": 60})
    evt1 = _player_event("chat", "Steve")
    first = react_to_event(evt1, skip_cooldown=False, force=True)
    assert first["ok"] is True
    evt2 = _player_event("death", "Steve")
    second = react_to_event(evt2, skip_cooldown=False)
    assert second.get("error") == "cooldown"


def test_react_skips_move_action(linkin_env):
    update_gm_config({"enabled": True})
    evt = append_minecraft_event(
        domain="player",
        action="move",
        status="ok",
        summary="moved",
        entity_refs={"player_id": "steve", "player_name": "Steve"},
    )
    res = react_to_event(evt)
    assert res.get("error") == "action_not_reactive:move"


def test_react_with_mock_llm(linkin_env, monkeypatch):
    update_gm_config({"enabled": True, "dry_run": True, "cooldown_seconds": 0})

    def fake_llm(*_a, **_k):
        return json.dumps(
            {
                "rationale": "玩家打招呼，NPC 回應",
                "actions": [{"type": "npc_say", "npc_name": "村長", "message": "你好"}],
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr("backend.core.llm.call_llm", fake_llm)
    monkeypatch.setenv("EVOL_LINKIN_NO_LLM", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-not-real")

    evt = _player_event()
    res = react_to_event(evt, skip_cooldown=True, force=True)
    assert res["ok"] is True
    run = res["run"]
    assert run["actions"][0]["type"] == "npc_say"
    assert "村長" in str(run["apply_results"][0].get("message", ""))

    gm_events = [e for e in list_minecraft_events(limit=50)["events"] if e.get("domain") == "gm"]
    assert len(gm_events) >= 1


def test_gm_tick_api(client: TestClient, monkeypatch):
    update_gm_config({"enabled": True, "dry_run": True, "cooldown_seconds": 0})
    _player_event("death")
    _player_event("chat")

    monkeypatch.setattr(
        "backend.core.llm.call_llm",
        lambda *_a, **_k: json.dumps({"rationale": "noop", "actions": [{"type": "noop"}]}),
    )
    monkeypatch.setenv("EVOL_LINKIN_NO_LLM", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    res = client.post("/linkin/minecraft/gm/tick?limit=2")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["processed"] >= 1


def test_gm_config_api(client: TestClient):
    res = client.get("/linkin/minecraft/gm/config")
    assert res.status_code == 200
    assert "config" in res.json()

    put = client.put("/linkin/minecraft/gm/config", json={"enabled": True, "dry_run": True})
    assert put.status_code == 200
    assert put.json()["config"]["enabled"] is True


def test_gm_runs_list(client: TestClient, monkeypatch):
    update_gm_config({"enabled": True, "dry_run": True, "cooldown_seconds": 0})
    monkeypatch.setattr(
        "backend.core.llm.call_llm",
        lambda *_a, **_k: json.dumps({"rationale": "t", "actions": [{"type": "noop"}]}),
    )
    monkeypatch.setenv("EVOL_LINKIN_NO_LLM", "0")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    evt = _player_event()
    react_to_event(evt, skip_cooldown=True, force=True)

    res = client.get("/linkin/minecraft/gm/runs?limit=10")
    assert res.status_code == 200
    assert res.json()["count"] >= 1


def test_decide_without_llm(linkin_env):
    decision = decide_gm_actions({}, _player_event())
    assert decision["source"] == "unavailable"
    assert decision["actions"][0]["type"] == "noop"
