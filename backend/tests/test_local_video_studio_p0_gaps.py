"""P0-03／P0-11／P0-12／P0-13 缺口驗收。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend.local_video_studio.agent.poller import run_once
from backend.local_video_studio.comfy_client import ComfyClient
from backend.local_video_studio.db import init_db, reset_db_state, session_scope
from backend.local_video_studio.mock_comfyui import create_mock_comfy_app
from backend.local_video_studio.model_registry import ModelValidationError, validate_required_models
from backend.local_video_studio.schemas import ModelRegister
from backend.main import app


class _TestClientAsHttpx:
    def __init__(self, app_):
        self._client = TestClient(app_)

    def post(self, url, **kwargs):
        return self._client.post(url, **kwargs)

    def get(self, url, **kwargs):
        return self._client.get(url, **kwargs)

    def close(self) -> None:
        self._client.close()


def _boot(monkeypatch, tmp_path, db_name: str) -> TestClient:
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / db_name}")
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path / "media"))
    monkeypatch.setenv("LVS_AGENT_ID", "test-agent")
    monkeypatch.setenv("LVS_USE_MOCK_COMFY", "true")
    monkeypatch.delenv("LVS_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)
    reset_db_state()
    init_db()
    return TestClient(app)


_MIN_WF = {
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "old"}},
    "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
}
_MIN_MAP = {
    "mappings": [
        {"param": "prompt", "node_id": "6", "input": "text"},
        {"param": "seed", "node_id": "3", "input": "seed"},
    ]
}
_BAD_MAP = {
    "mappings": [
        {"param": "prompt", "node_id": "99", "input": "text"},
    ]
}


# ---- P0-03 ----


def test_p0_03_import_workflow_versions_and_reject_bad_mapping(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "p0-03.sqlite3")
    r1 = client.post(
        "/local-video-studio/api/v1/workflows",
        json={
            "name": "demo_wf",
            "workflow_json": _MIN_WF,
            "mapping_json": _MIN_MAP,
            "required_models": ["flux_dev"],
            "notes": "v1",
        },
    )
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["name"] == "demo_wf"
    assert body1["version"] == 1
    assert body1["required_models"] == ["flux_dev"]

    r2 = client.post(
        "/local-video-studio/api/v1/workflows",
        json={
            "name": "demo_wf",
            "workflow_json": _MIN_WF,
            "mapping_json": _MIN_MAP,
            "notes": "v2",
        },
    )
    assert r2.status_code == 200
    assert r2.json()["version"] == 2

    listed = client.get("/local-video-studio/api/v1/workflows?name=demo_wf")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    latest = client.get("/local-video-studio/api/v1/workflows/demo_wf")
    assert latest.json()["version"] == 2

    bad = client.post(
        "/local-video-studio/api/v1/workflows",
        json={
            "name": "bad_wf",
            "workflow_json": _MIN_WF,
            "mapping_json": _BAD_MAP,
        },
    )
    assert bad.status_code == 422
    assert "node" in bad.json()["detail"].lower() or "99" in bad.json()["detail"]


def test_p0_03_job_fails_when_imported_mapping_node_missing(monkeypatch, tmp_path):
    """Acceptance：mapping 缺 node 時 job 失敗並給明確錯誤。"""
    client = _boot(monkeypatch, tmp_path, "p0-03-job.sqlite3")
    # 先匯入合法模板，再手動把 DB mapping 換成缺 node（模擬損壞／錯版）
    client.post(
        "/local-video-studio/api/v1/workflows",
        json={
            "name": "broken_inject",
            "workflow_json": _MIN_WF,
            "mapping_json": _MIN_MAP,
        },
    )
    from sqlalchemy import select

    from backend.local_video_studio.models import WorkflowTemplate

    with session_scope() as session:
        row = session.scalars(
            select(WorkflowTemplate)
            .where(WorkflowTemplate.name == "broken_inject")
            .order_by(WorkflowTemplate.version.desc())
        ).first()
        assert row is not None
        row.mapping_json = _BAD_MAP
        session.flush()

    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "p03"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "x"},
    ).json()["id"]
    job = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "broken_inject",
            "params": {"prompt": "hi", "seed": 1},
        },
    )
    assert job.status_code == 200
    job_id = job.json()["id"]

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
    assert result["status"] == "failed"
    assert "99" in (result.get("error") or "") or "node" in (result.get("error") or "").lower()

    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}").json()
    assert detail["status"] == "failed"
    assert detail["error"]


# ---- P0-11 ----


def test_p0_11_model_registry_and_missing_model_fails_job(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "p0-11.sqlite3")
    models_dir = tmp_path / "media" / "models"
    models_dir.mkdir(parents=True)
    real = models_dir / "flux.safetensors"
    real.write_bytes(b"fake-weights")

    reg = client.post(
        "/local-video-studio/api/v1/models",
        json={
            "name": "flux_dev",
            "path": str(real),
            "sha256": "abc",
            "vae_name": "ae.safetensors",
            "notes": "test",
        },
    )
    assert reg.status_code == 200
    assert reg.json()["name"] == "flux_dev"

    listed = client.get("/local-video-studio/api/v1/models")
    assert any(m["name"] == "flux_dev" for m in listed.json())

    # 單位：缺檔
    with session_scope() as session:
        from backend.local_video_studio import model_registry as mr

        mr.register_model(
            session,
            ModelRegister(name="ghost_ckpt", path=str(models_dir / "missing.safetensors")),
        )
        try:
            validate_required_models(session, ["ghost_ckpt"], models_root=models_dir)
            assert False, "expected ModelValidationError"
        except ModelValidationError as exc:
            assert "ghost_ckpt" in str(exc)

    # VAE 混用
    with session_scope() as session:
        from backend.local_video_studio import model_registry as mr

        mr.register_model(
            session,
            ModelRegister(
                name="wan_5b_refine",
                path=str(real),
                vae_name="wan_2.1_vae",
            ),
        )
        try:
            validate_required_models(session, ["wan_5b_refine"], models_root=models_dir)
            assert False, "expected VAE error"
        except ModelValidationError as exc:
            assert "wan_5b_refine" in str(exc)
            assert "VAE" in str(exc) or "vae" in str(exc).lower()

    # Job 執行前缺模型 → failed，錯誤含模型名
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "p11"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "m"},
    ).json()["id"]
    job = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "required_models": ["not_registered_model_xyz"],
            "params": {
                "prompt": "p",
                "output_relative_path": f"projects/{project_id}/keyframes/{shot_id}.png",
                "input_image_relative_path": f"projects/{project_id}/script/ref.png",
            },
        },
    )
    assert job.status_code == 200
    job_id = job.json()["id"]

    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy11")
    comfy = ComfyClient("http://mock", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            result = run_once(
                session,
                comfy=comfy,
                agent_id="test-agent",
                storage_base=tmp_path / "media",
                models_root=models_dir,
            )
    finally:
        comfy.close()

    assert result is not None
    assert result["status"] == "failed"
    assert "not_registered_model_xyz" in (result.get("error") or "")
    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}").json()
    assert "not_registered_model_xyz" in (detail.get("error") or "")
    assert detail.get("error_summary")


# ---- P0-12 ----


def test_p0_12_job_log_file_and_ui_error_summary(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "p0-12.sqlite3")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": "p12"}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "log"},
    ).json()["id"]

    # 故意用缺 mapping node 的匯入模板讓 job 失敗
    client.post(
        "/local-video-studio/api/v1/workflows",
        json={
            "name": "log_fail_wf",
            "workflow_json": _MIN_WF,
            "mapping_json": _MIN_MAP,
        },
    )
    from sqlalchemy import select

    from backend.local_video_studio.models import WorkflowTemplate

    with session_scope() as session:
        row = session.scalars(
            select(WorkflowTemplate).where(WorkflowTemplate.name == "log_fail_wf")
        ).first()
        assert row is not None
        row.mapping_json = _BAD_MAP

    job = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "log_fail_wf",
            "params": {"prompt": "x", "seed": 1},
        },
    ).json()
    job_id = job["id"]
    assert job["log_relative_path"] == f"projects/{project_id}/logs/{job_id}.log"

    mock_app = create_mock_comfy_app(output_dir=tmp_path / "comfy12")
    comfy = ComfyClient("http://mock", client=_TestClientAsHttpx(mock_app))
    try:
        with session_scope() as session:
            run_once(
                session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media"
            )
    finally:
        comfy.close()

    log_path = tmp_path / "media" / "projects" / project_id / "logs" / f"{job_id}.log"
    assert log_path.is_file(), f"missing log file: {log_path}"
    text = log_path.read_text(encoding="utf-8")
    assert "error" in text.lower() or "99" in text

    log_api = client.get(f"/local-video-studio/api/v1/jobs/{job_id}/log")
    assert log_api.status_code == 200
    body = log_api.json()
    assert body["exists"] is True
    assert body["error_summary"]
    assert "99" in body["error_summary"] or "node" in body["error_summary"].lower()

    # JobsPage 同源：GET /jobs 帶 error／error_summary
    jobs = client.get(f"/local-video-studio/api/v1/jobs?project_id={project_id}").json()
    failed = next(j for j in jobs if j["id"] == job_id)
    assert failed["status"] == "failed"
    assert failed["error"]
    assert failed["error_summary"] == failed["error"]


# ---- P0-13 ----


def test_p0_13_api_md_lists_lvs_routes():
    root = Path(__file__).resolve().parents[2]
    api_md = root / "docs" / "API.md"
    assert api_md.is_file(), "docs/API.md 必須存在"
    text = api_md.read_text(encoding="utf-8")
    required = [
        "/local-video-studio/api/v1/projects",
        "/local-video-studio/api/v1/jobs",
        "/local-video-studio/api/v1/workflows",
        "/local-video-studio/api/v1/models",
        "/local-video-studio/api/v1/jobs/{job_id}/log",
        "X-API-Key",
        "curl",
        "/docs",
    ]
    for needle in required:
        assert needle in text, f"docs/API.md 缺少：{needle}"

    # 與 api.py 路由對照（關鍵 v1 路徑字串）
    api_py = (root / "backend" / "local_video_studio" / "api.py").read_text(encoding="utf-8")
    for route in (
        '"/workflows"',
        '"/models"',
        '"/jobs/{job_id}/log"',
        "api_import_workflow",
        "api_register_model",
        "api_job_log",
    ):
        assert route in api_py, f"api.py 缺少：{route}"
