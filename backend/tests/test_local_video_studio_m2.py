"""M2：Jobs API + mock ComfyUI + render-agent poller → Asset。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.local_video_studio.agent.poller import run_once
from backend.local_video_studio.comfy_client import ComfyClient
from backend.local_video_studio.db import init_db, reset_db_state, session_scope
from backend.local_video_studio.mock_comfyui import create_mock_comfy_app
from backend.local_video_studio.workflow_inject import WorkflowMappingError, inject_params
from backend.main import app


class _TestClientAsHttpx:
    """把 Starlette TestClient 適配成 ComfyClient 可用的同步 HTTP 介面。"""

    def __init__(self, app):
        self._client = TestClient(app)

    def post(self, url, **kwargs):
        return self._client.post(url, **kwargs)

    def get(self, url, **kwargs):
        return self._client.get(url, **kwargs)

    def close(self) -> None:
        self._client.close()


def test_workflow_inject_writes_params():
    workflow = {
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
        "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
    }
    mapping = {
        "mappings": [
            {"param": "prompt", "node_id": "6", "input": "text"},
            {"param": "seed", "node_id": "3", "input": "seed"},
        ]
    }
    out = inject_params(workflow, {"prompt": "neon alley", "seed": 7}, mapping)
    assert out["6"]["inputs"]["text"] == "neon alley"
    assert out["3"]["inputs"]["seed"] == 7


def test_workflow_inject_missing_node_raises():
    try:
        inject_params(
            {"6": {"inputs": {"text": "x"}}},
            {"prompt": "y"},
            {"mappings": [{"param": "prompt", "node_id": "99", "input": "text"}]},
        )
        assert False, "expected WorkflowMappingError"
    except WorkflowMappingError:
        pass


def test_m2_keyframe_job_agent_mock_comfy_asset(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'lvs-m2.sqlite3'}")
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path / "media"))
    monkeypatch.setenv("LVS_AGENT_ID", "test-agent")
    reset_db_state()
    init_db()

    client = TestClient(app)
    project = client.post(
        "/local-video-studio/api/v1/projects",
        json={"name": "m2-demo"},
    ).json()
    project_id = project["id"]
    shot = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "keyframe subject"},
    ).json()
    shot_id = shot["id"]

    out_rel = f"projects/{project_id}/keyframes/{shot_id}.png"
    job = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "params": {
                "prompt": "wide rainy alley",
                "negative_prompt": "blur",
                "seed": 1,
                "width": 1024,
                "height": 1024,
                "input_image_relative_path": f"projects/{project_id}/script/ref.png",
                "output_relative_path": out_rel,
            },
        },
    )
    assert job.status_code == 200
    job_body = job.json()
    assert job_body["status"] == "queued"
    job_id = job_body["id"]

    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy-out")
    comfy = ComfyClient("http://mock-comfy", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            result = run_once(
                session,
                comfy=comfy,
                agent_id="test-agent",
                storage_base=Path(tmp_path / "media"),
            )
    finally:
        comfy.close()

    assert result is not None
    assert result["id"] == job_id
    assert result["status"] == "succeeded"
    assert result["assigned_agent"] == "test-agent"
    assert result["asset"] is not None
    assert result["asset"]["relative_path"] == out_rel
    assert result["asset"]["sha256"]
    assert (tmp_path / "media" / out_rel).is_file()

    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "succeeded"

    assets = client.get(f"/local-video-studio/api/v1/projects/{project_id}/assets")
    assert assets.status_code == 200
    assert len(assets.json()) >= 1
    assert assets.json()[0]["type"] == "keyframe"

    shot_after = client.get(f"/local-video-studio/api/v1/projects/{project_id}/shots").json()[0]
    assert shot_after["status"] == "keyframe_ready"
    assert shot_after["selected_keyframe_asset_id"]


def test_m2_job_cancel_and_retry(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'lvs-m2b.sqlite3'}")
    reset_db_state()
    init_db()
    client = TestClient(app)
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "retry"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "x"},
    ).json()["id"]
    job_id = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "params": {},
        },
    ).json()["id"]

    cancelled = client.post(f"/local-video-studio/api/v1/jobs/{job_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    retried = client.post(f"/local-video-studio/api/v1/jobs/{job_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "queued"
    assert retried.json()["assigned_agent"] is None
