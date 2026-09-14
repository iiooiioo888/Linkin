"""Minecraft 情境規則引擎測試。"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store, upsert_entity
from backend.linkin.minecraft_ai_gm import (
    apply_gm_actions,
    build_gm_context,
    reset_gm_state,
    validate_gm_actions,
)
from backend.linkin.minecraft_situation import build_situation_snapshot
from backend.linkin.minecraft_situation_rules import (
    evaluate_situation_rules,
    get_region_focus,
    list_rule_runs,
    recommendation_to_action,
    reset_rules_state,
    run_situation_rules,
    set_region_focus,
)
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.quest_runtime import _save_all, reset_quest_progress


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_GM_RULES_ENABLED", "true")
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_gm_state()
    reset_rules_state()
    reset_quest_progress()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_gm_state()
    reset_rules_state()
    reset_quest_progress()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", lambda *_a, **_k: None)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def test_evaluate_rules_no_players(linkin_env):
    snap = build_situation_snapshot()
    result = evaluate_situation_rules(snap)
    recs = result["recommendations"]
    assert isinstance(recs, list)
    assert any(r["action_type"] == "noop" for r in recs)
    assert any("經濟" in r.get("message", "") or "物價" in r.get("message", "") for r in recs)


def test_stuck_quest_produces_player_assist(linkin_env):
    upsert_entity(
        "quests",
        {
            "id": "quest-stuck-rule",
            "title": "卡住",
            "player_id": "steve",
            "objectives": [{"id": "o1", "title": "步驟"}],
        },
    )
    stale_ts = time.time() - 7200
    _save_all(
        [
            {
                "id": "qprog-rule",
                "player_id": "steve",
                "quest_id": "quest-stuck-rule",
                "status": "active",
                "objectives": {},
                "started_at": stale_ts,
                "updated_at": stale_ts,
                "completed_at": None,
                "last_event_id": None,
                "notes": [],
            }
        ]
    )
    snap = build_situation_snapshot()
    recs = evaluate_situation_rules(snap)["recommendations"]
    assert any(r["action_type"] == "player_assist" for r in recs)
    assert snap.get("rule_recommendations")


def test_run_situation_rules_persists_log(linkin_env):
    result = run_situation_rules(dry_run=True)
    assert result["ok"] is True
    runs = list_rule_runs(5)
    assert len(runs) >= 1
    assert runs[0]["id"] == result["run_id"]


def test_validate_new_gm_action_types(linkin_env):
    raw = [
        {"type": "player_assist", "message": "需要幫助", "assist_type": "quest_unstick"},
        {"type": "region_focus", "focus_mode": "away_from_spawn", "center": {"x": 0, "z": 0}},
    ]
    safe = validate_gm_actions(raw, max_actions=5)
    types = {a["type"] for a in safe}
    assert types == {"player_assist", "region_focus"}


def test_apply_region_focus_log_only(linkin_env):
    results = apply_gm_actions(
        [
            {
                "type": "region_focus",
                "focus_mode": "at_hotspot",
                "center": {"x": 100, "z": 200},
                "message": "焦點區",
            }
        ],
        dry_run=True,
        auto_apply=False,
    )
    assert results[0]["status"] == "log_only"
    focus = get_region_focus()
    assert focus.get("focus_mode") == "at_hotspot"


def test_apply_player_assist_dry_run(linkin_env, monkeypatch):
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {"enabled": False, "connected": False, "dry_run": True},
    )
    results = apply_gm_actions(
        [{"type": "player_assist", "message": "試試與 NPC 對話", "assist_type": "quest_unstick"}],
        dry_run=True,
        auto_apply=False,
    )
    assert results[0]["status"] == "log_only"
    assert results[0]["assist_type"] == "quest_unstick"


def test_gm_context_includes_rule_recommendations(linkin_env):
    ctx = build_gm_context(None)
    assert "rule_recommendations" in ctx
    assert isinstance(ctx["rule_recommendations"], list)


def test_situation_api_includes_rules(client: TestClient):
    res = client.get("/linkin/minecraft/situation")
    assert res.status_code == 200
    body = res.json()
    assert "rule_recommendations" in body

    rules = client.get("/linkin/minecraft/situation/rules")
    assert rules.status_code == 200
    assert "snapshot" in rules.json()


def test_recommendation_to_action(linkin_env):
    rec = {
        "id": "test",
        "action_type": "hint",
        "message": "測試提示",
        "payload": {"hint": "內容"},
    }
    action = recommendation_to_action(rec)
    assert action["type"] == "hint"
    assert action["message"] == "內容"


def test_set_region_focus_roundtrip(linkin_env):
    marker = {"focus_mode": "test", "center": {"x": 1, "z": 2}}
    set_region_focus(marker)
    loaded = get_region_focus()
    assert loaded["focus_mode"] == "test"
