"""Minecraft 玩家現場 API 與同步測試。"""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.minecraft_observability import reset_minecraft_events
from backend.linkin.minecraft_players import (
    _parse_online_players_payload,
    build_players_ai_block,
    list_player_events,
    list_players_snapshot,
    normalize_player_record,
    reset_player_state,
    sync_players_from_bridge,
)
from backend.linkin.narrative_registry import reset_narrative_registry


@pytest.fixture()
def linkin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    monkeypatch.setenv("EVOL_LINKIN_CONSTITUTION_PATH", str(tmp_path / "linkin_constitution.json"))
    monkeypatch.setenv("EVOL_LINKIN_CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EVOL_LINKIN_FORCE_JSON", "1")
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "true")
    monkeypatch.setenv("EVOL_MC_MCP_TOKEN", "test-token")
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()
    reset_player_state()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", lambda *_a, **_k: None)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def _mock_bridge(monkeypatch, *, online: list[str], player_detail: dict):
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {
            "enabled": True,
            "connected": True,
            "dry_run": False,
            "live": True,
            "token_configured": True,
            "world": "world",
        },
    )

    def fake_online(*_a, **_k):
        return {"ok": True, "text": json.dumps(online)}

    def fake_player(name, *_a, **_k):
        detail = dict(player_detail)
        detail.setdefault("name", name)
        return {"ok": True, "text": json.dumps(detail)}

    monkeypatch.setattr("backend.tools.minecraft_mcp.get_online_players", fake_online)
    monkeypatch.setattr("backend.tools.minecraft_mcp.get_player", fake_player)


def test_normalize_player_record_inventory():
    raw = {
        "name": "Steve",
        "uuid": "uuid-steve",
        "health": 18.5,
        "food": 16,
        "gamemode": "survival",
        "location": {"x": 10.2, "y": 64, "z": -5.7, "world": "world"},
        "inventory": [
            {"slot": 0, "type": "DIAMOND_SWORD", "amount": 1},
            {"slot": 1, "type": "OAK_PLANKS", "amount": 32},
        ],
        "armor": [{"type": "IRON_HELMET", "amount": 1}],
        "heldItem": {"type": "DIAMOND_SWORD", "amount": 1},
    }
    rec = normalize_player_record(raw)
    assert rec["name"] == "Steve"
    assert rec["position"]["x"] == pytest.approx(10.2)
    assert rec["inventory_summary"]
    assert rec["inventory_fingerprint"]


def test_sync_players_emits_join_and_move(linkin_env, monkeypatch):
    detail = {
        "name": "Alex",
        "uuid": "uuid-alex",
        "health": 20,
        "location": {"x": 1, "y": 64, "z": 2, "world": "world"},
        "inventory": [{"slot": 0, "type": "STONE", "amount": 1}],
    }
    _mock_bridge(monkeypatch, online=["Alex"], player_detail=detail)
    meta = sync_players_from_bridge(force=True)
    assert meta["synced"] is True
    assert meta["online_count"] == 1

    actions = [e["action"] for e in list_player_events(limit=50)["events"]]
    assert "join" in actions

    detail["location"] = {"x": 5, "y": 64, "z": 2, "world": "world"}
    monkeypatch.setattr(
        "backend.tools.minecraft_mcp.get_player",
        lambda name, *_a, **_k: {"ok": True, "text": json.dumps({**detail, "name": name})},
    )
    sync_players_from_bridge(force=True)
    actions2 = [e["action"] for e in list_player_events(limit=50)["events"]]
    assert "move" in actions2


def test_players_api_list_and_detail(client: TestClient, monkeypatch):
    detail = {
        "name": "Steve",
        "uuid": "uuid-steve",
        "health": 20,
        "food": 18,
        "gamemode": "creative",
        "location": {"x": 100, "y": 70, "z": -20, "world": "world_nether"},
        "inventory": [{"slot": 0, "type": "NETHERITE_PICKAXE", "amount": 1}],
    }
    _mock_bridge(monkeypatch, online=["Steve"], player_detail=detail)

    listed = client.get("/linkin/minecraft/players?sync=true")
    assert listed.status_code == 200
    body = listed.json()
    assert body["online_count"] == 1
    assert body["players"][0]["name"] == "Steve"
    assert body["players"][0]["position"]["x"] == 100

    pid = body["players"][0]["id"]
    detail_res = client.get(f"/linkin/minecraft/players/{pid}?sync=true")
    assert detail_res.status_code == 200
    detail_body = detail_res.json()
    assert detail_body["ok"] is True
    assert detail_body["player"]["slots"][0]["name"] == "NETHERITE_PICKAXE"


def test_ingest_validation(client: TestClient):
    missing = client.post("/linkin/minecraft/players/ingest", json={"player": "Steve"})
    assert missing.status_code == 200
    assert missing.json()["ok"] is False
    assert missing.json()["error"] == "missing_action"

    chat = client.post(
        "/linkin/minecraft/players/ingest",
        json={"action": "chat", "player": "Steve"},
    )
    assert chat.json()["error"] == "chat_requires_message"

    block = client.post(
        "/linkin/minecraft/players/ingest",
        json={"action": "block_break", "player": "Steve", "summary": "broke"},
    )
    assert block.json()["error"] == "block_action_requires_block"


def test_players_events_and_ingest(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {"enabled": False, "connected": False, "dry_run": True},
    )

    ingest = client.post(
        "/linkin/minecraft/players/ingest",
        json={
            "action": "chat",
            "player": "Steve",
            "message": "hello world",
            "summary": "Steve: hello world",
        },
    )
    assert ingest.status_code == 200
    assert ingest.json()["ok"] is True

    events = client.get("/linkin/minecraft/players/events?action=chat")
    assert events.status_code == 200
    ev_body = events.json()
    assert ev_body["count"] >= 1
    assert ev_body["events"][0]["domain"] == "player"
    assert ev_body["events"][0]["action"] == "chat"
    assert ev_body["events"][0]["details"]["source"] == "ingest"


def test_ai_snapshot_includes_players(client: TestClient, monkeypatch):
    detail = {
        "name": "Alex",
        "location": {"x": 0, "y": 64, "z": 0},
        "inventory": [{"slot": 0, "type": "BREAD", "amount": 5}],
    }
    _mock_bridge(monkeypatch, online=["Alex"], player_detail=detail)
    client.get("/linkin/minecraft/players?sync=true")

    snap = client.get("/linkin/minecraft/ai/snapshot")
    assert snap.status_code == 200
    players = snap.json().get("players") or {}
    assert players.get("online_count") == 1
    player_list = players.get("players") or []
    assert player_list[0]["name"] == "Alex"

    ctx = client.get("/linkin/minecraft/ai/context?max_chars=4000")
    assert "玩家現場" in ctx.json()["context"]


def test_players_api_offline_honest(client: TestClient, monkeypatch):
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {"enabled": False, "connected": False, "dry_run": True},
    )
    res = client.get("/linkin/minecraft/players?sync=true")
    body = res.json()
    assert body["bridge_offline"] is True
    assert body["online_count"] == 0
    assert body["players"] == []


def test_players_snapshot_includes_join_address(client: TestClient, monkeypatch):
    monkeypatch.setenv("EVOL_MC_MCP_ENABLED", "false")
    monkeypatch.setenv("EVOL_MC_JOIN_ADDRESS", "47.79.23.223:25565")
    monkeypatch.setattr(
        "backend.linkin.minecraft.monitor_status",
        lambda: {"enabled": False, "connected": False, "dry_run": True},
    )
    res = client.get("/linkin/minecraft/players?sync=false")
    body = res.json()
    assert body["online_count"] == 0
    assert body["players"] == []
    assert body["join_address"] == "47.79.23.223:25565"


def test_english_empty_online_text_not_a_player():
    """MineMCP 常回英文空狀態句；不得當成玩家名（否則 KPI=1、列表顯示該句）。"""
    assert _parse_online_players_payload("No players are currently online.") == []
    assert _parse_online_players_payload({"raw_text": "No players are currently online."}) == []
    assert _parse_online_players_payload({"raw_text": "There are no players online."}) == []
    assert _parse_online_players_payload(["Steve", "No players are currently online."]) == ["Steve"]
    assert _parse_online_players_payload(["Alex"]) == ["Alex"]


def test_english_empty_sync_clears_stale_and_matches_kpi(client: TestClient, monkeypatch):
    # 先用真實玩家污染 cache
    detail = {"name": "Steve", "location": {"x": 1, "y": 64, "z": 1}}
    _mock_bridge(monkeypatch, online=["Steve"], player_detail=detail)
    sync_players_from_bridge(force=True)
    assert list_players_snapshot(sync=False)["online_count"] == 1

    # MineMCP 改回英文空狀態句
    monkeypatch.setattr(
        "backend.tools.minecraft_mcp.get_online_players",
        lambda *_a, **_k: {"ok": True, "text": "No players are currently online."},
    )
    sync_players_from_bridge(force=True)
    snap = list_players_snapshot(sync=False)
    assert snap["online_count"] == 0
    assert snap["players"] == []

    # Monitor Hub 路徑（build_players_ai_block）須與面板一致
    block = build_players_ai_block(sync=True)
    assert block["online_count"] == 0
    assert block["players"] == []
