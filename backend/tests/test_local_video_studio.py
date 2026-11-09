"""Local Video Studio M0：health 探針與模組目錄。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.modules import register_builtin_modules
from backend.modules.registry import get_module, reset_registry


def test_local_video_studio_health_ok(monkeypatch):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("CLOUD_ENABLED", "false")
    client = TestClient(app)
    resp = client.get("/local-video-studio/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["module"] == "local-video-studio"
    assert body["milestone"] == "M0"
    assert body["cloud_enabled"] is False


def test_local_video_studio_health_v1_alias(monkeypatch):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    client = TestClient(app)
    resp = client.get("/local-video-studio/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_local_video_studio_module_catalog_health(monkeypatch):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    reset_registry()
    register_builtin_modules()
    spec = get_module("local-video-studio")
    assert spec is not None
    assert spec.id == "local-video-studio"
    snap = spec.health_snapshot()
    assert snap["ok"] is True

    client = TestClient(app)
    via_modules = client.get("/modules/local-video-studio/health")
    assert via_modules.status_code == 200
    assert via_modules.json()["ok"] is True
