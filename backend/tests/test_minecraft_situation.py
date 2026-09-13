"""Minecraft 四維情境快照測試。"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store, upsert_entity
from backend.linkin.minecraft_ai_gm import build_gm_context, reset_gm_state
from backend.linkin.minecraft_observability import (
    append_minecraft_event,
    build_ai_context,
    build_ai_snapshot,
    reset_minecraft_events,
)
from backend.linkin.minecraft_players import reset_player_state
from backend.linkin.minecraft_situation import (
    build_situation_snapshot,
    compact_situation_for_context,
)
from backend.linkin.narrative_registry import reset_narrative_registry
from backend.linkin.quest_runtime import reset_quest_progress


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


def test_snapshot_shape_empty(linkin_env):
    snap = build_situation_snapshot()
    assert "generated_at" in snap
    for dim in ("market", "economy", "land", "players"):
        block = snap[dim]
        assert block["status"] in {"ok", "partial", "unknown"}
        assert isinstance(block["signals"], list)
        assert isinstance(block["summary"], str)
        assert 0 <= block["confidence"] <= 1
    assert isinstance(snap["hints"], list)
    assert 1 <= len(snap["hints"]) <= 8


def test_unknown_when_no_data(linkin_env):
    snap = build_situation_snapshot()
    assert snap["market"]["status"] == "unknown"
    assert snap["economy"]["status"] in {"unknown", "partial"}
    assert snap["land"]["status"] == "unknown"
    assert snap["players"]["status"] in {"unknown", "partial"}
    price_signals = [s for s in snap["economy"]["signals"] if s.get("name") == "price_index"]
    assert price_signals and price_signals[0].get("value") == "unknown"


def test_land_partial_with_map_plan(linkin_env):
    upsert_entity(
        "map_plans",
        {
            "id": "plan-1",
            "title": "測試地圖",
            "region": "spawn",
            "plots": [{"id": "p1", "type": "poi", "title": "中心"}],
        },
    )
    snap = build_situation_snapshot()
    assert snap["land"]["status"] in {"partial", "ok"}
    assert snap["land"]["summary"]


def test_players_stuck_quest_hint(linkin_env):
    upsert_entity(
        "quests",
        {
            "id": "quest-stuck",
            "title": "卡住任務",
            "player_id": "steve",
            "objectives": [{"id": "obj-a", "title": "第一步"}],
        },
    )
    stale_ts = time.time() - 7200
    from backend.linkin.quest_runtime import _save_all

    _save_all(
        [
            {
                "id": "qprog-stuck",
                "player_id": "steve",
                "quest_id": "quest-stuck",
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
    stuck = next(s for s in snap["players"]["signals"] if s.get("name") == "stuck_quest_count")
    assert stuck.get("value", 0) >= 1
    assert any("卡住" in h for h in snap["hints"])


def test_gm_context_includes_situation(linkin_env):
    evt = append_minecraft_event(
        domain="player",
        action="chat",
        status="ok",
        summary="hello",
        entity_refs={"player_id": "steve", "player_name": "Steve"},
    )
    ctx = build_gm_context(evt)
    assert "situation" in ctx
    assert "market" in ctx["situation"]
    assert "hints" in ctx["situation"]


def test_ai_snapshot_and_context_include_situation(linkin_env):
    snap = build_ai_snapshot()
    assert "situation" in snap
    assert snap["situation"].get("market")

    ctx = build_ai_context(max_chars=4000, fmt="markdown")
    assert "四維情境" in ctx["context"]
    assert ctx["snapshot"].get("situation")


def test_compact_situation(linkin_env):
    full = build_situation_snapshot()
    compact = compact_situation_for_context(full)
    assert compact["market"]["status"] == full["market"]["status"]
    assert len(compact["market"]["signals"]) <= 6


def test_dimension_endpoint(client: TestClient):
    res = client.get("/linkin/minecraft/situation/land")
    assert res.status_code == 200
    body = res.json()
    assert body["dimension"] == "land"
    assert body["status"] in {"ok", "partial", "unknown"}

    bad = client.get("/linkin/minecraft/situation/invalid")
    assert bad.status_code == 404


def test_situation_api(client: TestClient):
    res = client.get("/linkin/minecraft/situation")
    assert res.status_code == 200
    body = res.json()
    assert all(dim in body for dim in ("market", "economy", "land", "players", "hints"))
