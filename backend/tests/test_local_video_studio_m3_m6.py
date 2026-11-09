"""M3–M6：workflows、draft/refine、review、compose+compliance、storage/resources。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backend.local_video_studio.agent.poller import run_once
from backend.local_video_studio.comfy_client import ComfyClient
from backend.local_video_studio.compliance import require_stamped, stamp
from backend.local_video_studio.config import load_config
from backend.local_video_studio.db import init_db, reset_db_state, session_scope
from backend.local_video_studio.ffmpeg_compose import compose_shots
from backend.local_video_studio.mock_comfyui import create_mock_comfy_app
from backend.local_video_studio.models import Asset
from backend.local_video_studio.storage import LocalPathStorage, StorageError
from backend.local_video_studio.workflow_inject import inject_params
from backend.main import app

_WF = Path(__file__).resolve().parents[1] / "local_video_studio" / "workflows"


class _TestClientAsHttpx:
    def __init__(self, app):
        self._client = TestClient(app)

    def post(self, url, **kwargs):
        return self._client.post(url, **kwargs)

    def get(self, url, **kwargs):
        return self._client.get(url, **kwargs)

    def close(self) -> None:
        self._client.close()


def _boot(monkeypatch, tmp_path, name: str):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_USE_MOCK_COMFY", "true")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / name}.sqlite3")
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path / "media"))
    monkeypatch.setenv("LVS_AGENT_ID", "test-agent")
    reset_db_state()
    init_db()
    return TestClient(app)


def test_m3_workflow_templates_and_mappings_exist():
    for name in ("keyframe_flux_ipadapter", "ltx_draft", "wan5b_refine"):
        wf = json.loads((_WF / f"{name}.json").read_text(encoding="utf-8"))
        mapping = json.loads((_WF / "mappings" / f"{name}.mapping.json").read_text(encoding="utf-8"))
        assert mapping["template"] == name
        out = inject_params(wf, {"prompt": "x", "seed": 1}, mapping)
        assert out["6"]["inputs"]["text"] == "x"


def test_m3_config_mock_vs_real_comfy(monkeypatch):
    monkeypatch.delenv("LVS_USE_MOCK_COMFY", raising=False)
    monkeypatch.delenv("LVS_COMFYUI_URL", raising=False)
    monkeypatch.delenv("COMFYUI_URL", raising=False)
    assert load_config().use_mock_comfy is True

    monkeypatch.setenv("COMFYUI_URL", "http://127.0.0.1:8188")
    assert load_config().use_mock_comfy is False

    monkeypatch.setenv("LVS_USE_MOCK_COMFY", "true")
    assert load_config().use_mock_comfy is True


def test_m3_draft_job_mock_comfy(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m3-draft")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "m3"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "draft"},
    ).json()["id"]
    out_rel = f"projects/{project_id}/drafts/{shot_id}.mp4"
    job_id = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "draft",
            "workflow_template": "ltx_draft",
            "params": {
                "prompt": "rain alley",
                "seed": 2,
                "width": 1280,
                "height": 704,
                "frames": 121,
                "input_image_relative_path": f"projects/{project_id}/keyframes/ref.png",
                "output_relative_path": out_rel,
            },
        },
    ).json()["id"]

    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy")
    comfy = ComfyClient("http://mock", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            result = run_once(
                session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media"
            )
    finally:
        comfy.close()

    assert result is not None
    assert result["id"] == job_id
    assert result["status"] == "succeeded"
    assert result["asset"]["type"] == "draft"
    assert (tmp_path / "media" / out_rel).is_file()
    shot = client.get(f"/local-video-studio/api/v1/projects/{project_id}/shots").json()[0]
    assert shot["status"] == "draft_ready"


def test_m4_refine_review_approve(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m4-review")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "m4"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "refine"},
    ).json()["id"]
    out_rel = f"projects/{project_id}/refines/{shot_id}.mp4"
    client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "refine",
            "workflow_template": "wan5b_refine",
            "params": {
                "prompt": "refine",
                "seed": 3,
                "output_relative_path": out_rel,
                "input_image_relative_path": f"projects/{project_id}/keyframes/ref.png",
            },
        },
    )
    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy")
    comfy = ComfyClient("http://mock", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            run_once(session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media")
    finally:
        comfy.close()

    assets = client.get(f"/local-video-studio/api/v1/projects/{project_id}/assets").json()
    assert assets[0]["type"] == "refine"
    asset_id = assets[0]["id"]

    queue = client.get(f"/local-video-studio/api/v1/projects/{project_id}/review-queue")
    assert queue.status_code == 200
    assert any(item["asset_id"] == asset_id for item in queue.json())

    review = client.post(
        f"/local-video-studio/api/v1/assets/{asset_id}/review",
        json={"decision": "approve", "reason": "ok"},
    )
    assert review.status_code == 200
    assert review.json()["decision"] == "approve"

    shot = client.get(f"/local-video-studio/api/v1/projects/{project_id}/shots").json()[0]
    assert shot["status"] == "approved"
    assert shot["selected_clip_asset_id"] == asset_id


def test_m5_compose_requires_compliance(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m5-compose")
    store = LocalPathStorage(tmp_path / "media")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "m5"}
    ).json()["id"]
    store.ensure_project_dirs(project_id)

    shot_ids = []
    for i in range(1, 4):
        shot = client.post(
            f"/local-video-studio/api/v1/projects/{project_id}/shots",
            json={"scene_no": 1, "shot_no": i, "description": f"s{i}"},
        ).json()
        shot_ids.append(shot["id"])
        rel = f"projects/{project_id}/refines/{shot['id']}.mp4"
        store.write_bytes(rel, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 32)
        # 直接 complete 路徑：寫入 asset + approve
        with session_scope() as session:
            asset = Asset(
                project_id=project_id,
                shot_id=shot["id"],
                type="refine",
                relative_path=rel,
                mime="video/mp4",
                bytes=40,
                sha256="a" * 64,
            )
            session.add(asset)
            session.flush()
            asset_id = asset.id
        client.post(
            f"/local-video-studio/api/v1/assets/{asset_id}/review",
            json={"decision": "approve"},
        )

    composed = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/compose",
        json={"shot_ids": shot_ids, "output_name": "final_v1.mp4", "add_watermark": True},
    )
    assert composed.status_code == 200, composed.text
    body = composed.json()
    assert body["compliance_id"]
    assert body["relative_path"].endswith("final_v1.mp4")
    assert (tmp_path / "media" / body["relative_path"]).is_file()

    stamp_get = client.get(f"/local-video-studio/api/v1/assets/{body['asset']['id']}/compliance")
    assert stamp_get.status_code == 200
    assert stamp_get.json()["explicit_mark"] is True
    assert stamp_get.json()["metadata_json"]["ai_generated"] is True


def test_m5_ffmpeg_compose_unit(tmp_path, monkeypatch):
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path))
    store = LocalPathStorage(tmp_path)
    pid = "proj-ff"
    store.ensure_project_dirs(pid)
    clips = []
    for i in range(2):
        rel = f"projects/{pid}/refines/c{i}.mp4"
        store.write_bytes(rel, b"fake" + bytes([i]))
        clips.append(rel)
    result = compose_shots(
        project_id=pid,
        clip_relative_paths=clips,
        output_name="out.mp4",
        storage=store,
    )
    assert result["relative_path"].endswith("out.mp4")
    assert Path(tmp_path / result["relative_path"]).is_file()
    meta = json.loads(
        (tmp_path / f"projects/{pid}/output/out.metadata.json").read_text(encoding="utf-8")
    )
    assert meta["ai_generated"] == "true"
    assert meta["explicit_text"]


def test_m5_compliance_stamp_unit(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'comp.sqlite3'}")
    reset_db_state()
    init_db()
    with session_scope() as session:
        from backend.local_video_studio.models import Project

        project = Project(name="c")
        session.add(project)
        session.flush()
        asset = Asset(
            project_id=project.id,
            type="final",
            relative_path=f"projects/{project.id}/output/x.mp4",
            bytes=1,
        )
        session.add(asset)
        session.flush()
        rec = stamp(session, asset=asset)
        assert rec.explicit_mark is True
        assert require_stamped(session, asset.id).id == rec.id


def test_m6_storage_and_resources(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m6-res")
    store = LocalPathStorage(tmp_path / "media")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "m6"}
    ).json()["id"]
    root = store.ensure_project_dirs(project_id)
    for name in ("script", "keyframes", "drafts", "refines", "output"):
        assert (root / name).is_dir()

    try:
        store.resolve("../escape")
        assert False, "expected StorageError"
    except StorageError:
        pass

    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "r"},
    ).json()["id"]
    client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "params": {
                "prompt": "p",
                "output_relative_path": f"projects/{project_id}/keyframes/{shot_id}.png",
                "input_image_relative_path": f"projects/{project_id}/script/ref.png",
            },
        },
    )
    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy")
    comfy = ComfyClient("http://mock", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            run_once(session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media")
    finally:
        comfy.close()

    summary = client.get(f"/local-video-studio/api/v1/projects/{project_id}/resources")
    assert summary.status_code == 200
    body = summary.json()
    assert body["job_count"] >= 1
    assert body["asset_count"] >= 1
    assert body["storage_bytes"] >= 0
    assert body["gpu_minutes"] >= 0


def test_m7_cloud_stubs_blocked(monkeypatch):
    monkeypatch.setenv("CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    from backend.local_video_studio.cloud_adapters.cloud_gpu import CloudGPUAdapter
    from backend.local_video_studio.cloud_adapters.vidu import ViduAdapter
    from backend.local_video_studio.cloud_adapters.base import CloudAdapterError

    try:
        ViduAdapter().submit({"data_class": "cloud_allowed"})
        assert False
    except CloudAdapterError:
        pass
    try:
        CloudGPUAdapter().submit({"data_class": "local_only"})
        assert False
    except CloudAdapterError:
        pass


def test_health_milestone_m6(monkeypatch):
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    resp = TestClient(app).get("/local-video-studio/health")
    assert resp.status_code == 200
    assert resp.json()["milestone"] == "M6"
    assert resp.json()["cloud_enabled"] is False
