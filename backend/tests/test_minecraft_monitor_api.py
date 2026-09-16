"""Minecraft 監控與 AI 可觀測性 API 測試。"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.linkin.api import register_linkin
from backend.linkin.constitution import reset_cache as reset_constitution_cache
from backend.linkin.knowledge import reset_store
from backend.linkin.minecraft_ai_gm import reset_gm_state, update_gm_config
from backend.linkin.minecraft_observability import (
    aggregate_ai_monitor_kpis,
    append_minecraft_event,
    count_minecraft_events_since,
    reset_minecraft_events,
    resolve_ai_gm_status,
)
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
    assert "bridge_setup" in body
    assert "plugins" in body
    assert "pipeline_timeline" in body
    assert isinstance(body["pipeline_timeline"], list)
    assert body["kpis"]["map_plan_count"] == 0
    assert body["bridge_setup"]["token_set"] is False
    ai = body["kpis"].get("ai") or {}
    assert ai.get("gm_status") == "offline"
    assert ai.get("events_24h") == 0


def test_aggregate_ai_monitor_kpis_events_and_gm(linkin_env, monkeypatch):
    reset_gm_state()
    now = 1_700_000_000.0
    monkeypatch.setattr("backend.linkin.minecraft_observability.time.time", lambda: now)
    append_minecraft_event(domain="map", action="generate", status="ok", summary="事件 A")
    append_minecraft_event(domain="player", action="join", status="ok", summary="事件 B")
    assert count_minecraft_events_since(now - 86400) == 2

    update_gm_config({"enabled": True, "dry_run": True, "auto_apply": False, "cooldown_seconds": 45})
    assert resolve_ai_gm_status({"enabled": True, "dry_run": True, "auto_apply": False}) == "dry-run"
    assert resolve_ai_gm_status({"enabled": True, "dry_run": False, "auto_apply": True}) == "active"
    assert resolve_ai_gm_status({"enabled": False}) == "offline"

    kpis = aggregate_ai_monitor_kpis(now=now)
    assert kpis["events_24h"] == 2
    assert kpis["gm_status"] == "dry-run"
    assert kpis["gm_cooldown_seconds"] == 45.0


def test_monitor_summary_includes_ai_kpis(client: TestClient):
    append_minecraft_event(domain="gm", action="react", status="dry_run", summary="GM 測試", dry_run=True)
    res = client.get("/linkin/minecraft/monitor/summary")
    body = res.json()
    ai = body["kpis"]["ai"]
    assert ai["events_24h"] >= 1
    assert "gm_status" in ai


def test_monitor_summary_pipeline_timeline(client: TestClient):
    append_minecraft_event(
        domain="pipeline",
        action="run",
        status="ok",
        summary="測試管線",
        details={"steps": [{"id": "begin_workspace", "status": "ok"}]},
    )
    append_minecraft_event(domain="map", action="generate", status="ok", summary="地圖生成")
    res = client.get("/linkin/minecraft/monitor/summary")
    body = res.json()
    assert len(body["pipeline_timeline"]) >= 2
    assert body["last_pipeline"]["domain"] == "pipeline"


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


def test_recent_errors_drops_superseded_bridge_offline_probe(client: TestClient):
    """成功探測後，舊的 bridge_offline probe 不應再出現在 recent_errors。"""
    append_minecraft_event(
        domain="bridge",
        action="probe",
        status="bridge_offline",
        summary="MineMCP 遠端探測：未連線（MCP HTTP 失敗：404）",
        bridge_offline=True,
        details={"error": "404"},
    )
    append_minecraft_event(
        domain="bridge",
        action="probe",
        status="ok",
        summary="MineMCP 遠端探測：已連線",
        bridge_offline=False,
    )
    res = client.get("/linkin/minecraft/monitor/summary")
    assert res.status_code == 200
    errors = res.json().get("recent_errors") or []
    assert not any(
        e.get("bridge_offline") and str(e.get("action")) == "probe" for e in errors
    )
    assert not any("404" in str(e.get("summary") or "") for e in errors)


def test_recent_errors_excludes_dry_run_probe(client: TestClient):
    append_minecraft_event(
        domain="bridge",
        action="probe",
        status="dry_run",
        summary="MineMCP 探測 connected=False dry_run=True",
        dry_run=True,
        details={"connected": False, "dry_run": True},
    )
    res = client.get("/linkin/minecraft/monitor/summary")
    assert res.status_code == 200
    errors = res.json().get("recent_errors") or []
    assert not any(e.get("dry_run") for e in errors)
    assert not any("dry_run=True" in str(e.get("summary") or "") for e in errors)


def test_map_plans_list(client: TestClient):
    res = client.get("/linkin/map/plans")
    assert res.status_code == 200
    assert res.json()["count"] == 0
