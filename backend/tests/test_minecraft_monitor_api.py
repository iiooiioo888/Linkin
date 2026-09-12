"""Minecraft 監控與 AI 可觀測性 API 測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.minecraft_observability import append_minecraft_event, reset_minecraft_events
from backend.linkin.narrative_registry import reset_narrative_registry


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
    yield tmp_path
    reset_store()
    reset_constitution_cache()
    reset_narrative_registry()
    reset_minecraft_events()


@pytest.fixture()
def client(linkin_env, monkeypatch):
    monkeypatch.setattr("backend.linkin.knowledge.evaluate_for_write", lambda *_a, **_k: None)
    app = FastAPI()
    register_linkin(app)
    with TestClient(app) as c:
        yield c


def test_monitor_summary_empty(client: TestClient):
    res = client.get("/linkin/minecraft/monitor/summary")
    assert res.status_code == 200
    body = res.json()
    assert "kpis" in body
    assert "bridge" in body
    assert body["kpis"]["map_plan_count"] == 0


def test_ai_events_append_and_list(client: TestClient):
    append_minecraft_event(
        domain="map",
        action="generate",
        status="ok",
        summary="測試地圖生成",
        dry_run=True,
    )
    res = client.get("/linkin/minecraft/ai/events?limit=10")
    assert res.status_code == 200
    body = res.json()
    assert body["count"] >= 1
    assert body["events"][-1]["summary"] == "測試地圖生成"
    assert body["events"][-1]["dry_run"] is True


def test_ai_snapshot_and_context(client: TestClient):
    append_minecraft_event(
        domain="bridge",
        action="probe",
        status="bridge_offline",
        summary="探測失敗",
        bridge_offline=True,
    )
    snap = client.get("/linkin/minecraft/ai/snapshot")
    assert snap.status_code == 200
    assert snap.json()["bridge"]["enabled"] is False

    ctx = client.get("/linkin/minecraft/ai/context?max_chars=2000&format=markdown")
    assert ctx.status_code == 200
    blob = ctx.json()
    assert blob["format"] == "markdown"
    assert "Minecraft" in blob["context"]
    assert blob["chars"] > 0


def test_map_plans_list(client: TestClient):
    res = client.get("/linkin/map/plans")
    assert res.status_code == 200
    assert res.json()["count"] == 0
