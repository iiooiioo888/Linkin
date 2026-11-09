"""Local Video Studio：M0 health + M1 projects/scripts/shots CRUD。"""

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
    assert body["milestone"] == "M1"
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
    assert spec.default_page == "projects"
    snap = spec.health_snapshot()
    assert snap["ok"] is True

    client = TestClient(app)
    via_modules = client.get("/modules/local-video-studio/health")
    assert via_modules.status_code == 200
    assert via_modules.json()["ok"] is True


def test_m1_project_crud_and_import_three_shots(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'lvs.sqlite3'}")
    from backend.local_video_studio.db import init_db, reset_db_state

    reset_db_state()
    init_db()

    client = TestClient(app)

    created = client.post(
        "/local-video-studio/api/v1/projects",
        json={"name": "demo", "description": "m1"},
    )
    assert created.status_code == 200
    project = created.json()
    assert project["name"] == "demo"
    assert project["status"] == "draft"
    assert project["shot_count"] == 0
    project_id = project["id"]

    listed = client.get("/local-video-studio/api/v1/projects")
    assert listed.status_code == 200
    assert any(item["id"] == project_id for item in listed.json())

    patched = client.patch(
        f"/local-video-studio/api/v1/projects/{project_id}",
        json={"status": "scripting"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "scripting"

    script = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/scripts",
        json={
            "content_json": {
                "project_title": "demo",
                "shots": [
                    {
                        "scene_no": 1,
                        "shot_no": 1,
                        "description": "wide shot, rainy alley, neon light",
                        "dialogue": "",
                        "duration_sec": 5,
                    },
                    {
                        "scene_no": 1,
                        "shot_no": 2,
                        "description": "close-up, character looks up",
                        "dialogue": "開始了",
                        "duration_sec": 4,
                    },
                    {
                        "scene_no": 2,
                        "shot_no": 1,
                        "description": "drone over rooftops at dusk",
                        "dialogue": "",
                        "duration_sec": 6,
                    },
                ],
            }
        },
    )
    assert script.status_code == 200
    script_body = script.json()
    assert script_body["imported_shots"] == 3
    assert script_body["version"] == 1

    shots = client.get(f"/local-video-studio/api/v1/projects/{project_id}/shots")
    assert shots.status_code == 200
    shot_rows = shots.json()
    assert len(shot_rows) == 3
    assert shot_rows[0]["scene_no"] == 1 and shot_rows[0]["shot_no"] == 1
    assert shot_rows[1]["description"] == "close-up, character looks up"

    detail = client.get(f"/local-video-studio/api/v1/projects/{project_id}")
    assert detail.status_code == 200
    assert detail.json()["shot_count"] == 3

    one = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={
            "scene_no": 3,
            "shot_no": 1,
            "description": "manual shot",
            "duration_sec": 3.5,
        },
    )
    assert one.status_code == 200
    shot_id = one.json()["id"]

    updated = client.patch(
        f"/local-video-studio/api/v1/shots/{shot_id}",
        json={"status": "keyframe_ready", "description": "manual shot refined"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "keyframe_ready"
    assert updated.json()["description"] == "manual shot refined"

    final_shots = client.get(f"/local-video-studio/api/v1/projects/{project_id}/shots")
    assert len(final_shots.json()) == 4


def test_m1_api_key_gate(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_API_KEY", "secret-key")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'lvs-key.sqlite3'}")
    from backend.local_video_studio.db import init_db, reset_db_state

    reset_db_state()
    init_db()
    client = TestClient(app)

    denied = client.get("/local-video-studio/api/v1/projects")
    assert denied.status_code == 401

    ok = client.get(
        "/local-video-studio/api/v1/projects",
        headers={"X-API-Key": "secret-key"},
    )
    assert ok.status_code == 200
    assert ok.json() == []
