"""Phase A（M8）硬化：假成片、缺圖、逾時／停滯、sha256、字型、daemon。"""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.local_video_studio.agent.daemon import build_stop_handler, serve
from backend.local_video_studio.agent.heartbeat import latest_heartbeat, reset_heartbeats
from backend.local_video_studio.agent.lease import LeaseManager, reclaim_expired_leases
from backend.local_video_studio.agent.poller import run_once
from backend.local_video_studio.comfy_client import ComfyClient, ComfyClientError
from backend.local_video_studio.config import load_config
from backend.local_video_studio.db import init_db, reset_db_state, session_scope
from backend.local_video_studio.ffmpeg_compose import (
    ComposeError,
    build_ffmpeg_command,
    compose_shots,
)
from backend.local_video_studio.jobs import claim_job
from backend.local_video_studio.mock_comfyui import create_mock_comfy_app
from backend.local_video_studio.model_registry import (
    ModelValidationError,
    hash_file_sha256,
    validate_required_models,
)
from backend.local_video_studio.models import Asset, ComplianceRecord, GenerationJob
from backend.local_video_studio.schemas import ModelRegister
from backend.local_video_studio.storage import LocalPathStorage
from backend.main import app

_REPO = Path(__file__).resolve().parents[2]


class _Resp:
    def __init__(self, code: int, payload: dict, content: bytes = b""):
        self.status_code = code
        self._payload = payload
        self.text = ""
        self.content = content

    def json(self) -> dict:
        return self._payload


class _QueueHttp:
    """history 不完成；queue 簽名可固定或每次遞增。"""

    def __init__(self, *, prompt_id: str, vary_queue: bool = False, complete_on: int | None = None):
        self.prompt_id = prompt_id
        self.vary_queue = vary_queue
        self.complete_on = complete_on
        self.queue_n = 0
        self.history_n = 0

    def post(self, url, **kwargs):
        if "upload" in url:
            return _Resp(200, {"name": "ref.png"})
        return _Resp(200, {"prompt_id": self.prompt_id})

    def get(self, url, **kwargs):
        if str(url).startswith("/history"):
            self.history_n += 1
            if self.complete_on is not None and self.history_n >= self.complete_on:
                return _Resp(
                    200,
                    {
                        self.prompt_id: {
                            "status": {"completed": True},
                            "outputs": {"9": {"images": [{"filename": "out.png"}]}},
                        }
                    },
                )
            return _Resp(200, {})
        if url == "/queue":
            self.queue_n += 1
            number = self.queue_n if self.vary_queue else 1
            return _Resp(
                200,
                {"queue_running": [[number, self.prompt_id]], "queue_pending": []},
            )
        return _Resp(404, {}, b"")

    def close(self) -> None:
        return None


def _boot(monkeypatch, tmp_path, name: str) -> TestClient:
    monkeypatch.setenv("LVS_CLOUD_ENABLED", "false")
    monkeypatch.setenv("CLOUD_ENABLED", "false")
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / name}.sqlite3")
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path / "media"))
    monkeypatch.setenv("LVS_AGENT_ID", "test-agent")
    monkeypatch.delenv("LVS_ALLOW_FAKE_MEDIA", raising=False)
    reset_db_state()
    init_db()
    return TestClient(app)


def _approved_clip(client: TestClient, tmp_path: Path, name: str) -> tuple[str, list[str]]:
    store = LocalPathStorage(tmp_path / "media")
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": name}
    ).json()["id"]
    store.ensure_project_dirs(project_id)
    shot = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": name},
    ).json()
    rel = f"projects/{project_id}/refines/{shot['id']}.mp4"
    store.write_bytes(rel, b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)
    with session_scope() as session:
        asset = Asset(
            project_id=project_id,
            shot_id=shot["id"],
            type="refine",
            relative_path=rel,
            mime="video/mp4",
            bytes=20,
            sha256="b" * 64,
        )
        session.add(asset)
        session.flush()
        asset_id = asset.id
    assert client.post(
        f"/local-video-studio/api/v1/assets/{asset_id}/review",
        json={"decision": "approve"},
    ).status_code == 200
    return project_id, [shot["id"]]


def _queue_job(client: TestClient, project_name: str, params: dict) -> tuple[str, str]:
    project_id = client.post(
        "/local-video-studio/api/v1/projects", json={"name": project_name}
    ).json()["id"]
    shot_id = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": project_name},
    ).json()["id"]
    job_id = client.post(
        "/local-video-studio/api/v1/jobs",
        json={
            "project_id": project_id,
            "shot_id": shot_id,
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "params": params,
        },
    ).json()["id"]
    return project_id, job_id


# ---- M8-01 ----


def test_fake_media_defaults_off(monkeypatch):
    monkeypatch.delenv("LVS_ALLOW_FAKE_MEDIA", raising=False)
    monkeypatch.delenv("LVS_JOB_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("JOB_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("LVS_VERIFY_MODEL_SHA256", raising=False)
    cfg = load_config()
    assert cfg.allow_fake_media is False
    assert cfg.job_timeout_sec == 7200
    assert cfg.verify_model_sha256 is False
    assert cfg.cloud_enabled is False


def test_missing_ffmpeg_raises_and_compose_job_has_no_compliance(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.local_video_studio.ffmpeg_compose.shutil.which",
        lambda _name: None,
    )
    client = _boot(monkeypatch, tmp_path, "m8-ffmpeg-missing")
    project_id, shot_ids = _approved_clip(client, tmp_path, "no-ffmpeg")
    resp = client.post(
        f"/local-video-studio/api/v1/projects/{project_id}/compose",
        json={"shot_ids": shot_ids, "output_name": "final_v1.mp4", "add_watermark": True},
    )
    assert resp.status_code == 400, resp.text
    assert "ffmpeg" in resp.json()["detail"]
    out = tmp_path / "media" / "projects" / project_id / "output" / "final_v1.mp4"
    assert not out.exists()
    with session_scope() as session:
        job = session.scalars(
            select(GenerationJob).where(GenerationJob.job_type == "compose")
        ).one()
        assert job.status == "failed"
        assert "ffmpeg" in (job.error or "")
        assert session.scalars(select(ComplianceRecord)).all() == []
        finals = session.scalars(select(Asset).where(Asset.type == "final")).all()
        assert finals == []


def test_ffmpeg_nonzero_raises_without_fake_file(monkeypatch, tmp_path):
    monkeypatch.delenv("LVS_ALLOW_FAKE_MEDIA", raising=False)
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    monkeypatch.setenv("LVS_DRAWTEXT_FONT", str(font))
    monkeypatch.setattr(
        "backend.local_video_studio.ffmpeg_compose.shutil.which",
        lambda _name: "/usr/bin/ffmpeg",
    )

    def _fail(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 7, "", "encoder exploded")

    monkeypatch.setattr(
        "backend.local_video_studio.ffmpeg_compose.subprocess.run",
        _fail,
    )
    store = LocalPathStorage(tmp_path / "media")
    pid = "nz"
    store.ensure_project_dirs(pid)
    rel = f"projects/{pid}/refines/a.mp4"
    store.write_bytes(rel, b"clip")
    try:
        compose_shots(
            project_id=pid,
            clip_relative_paths=[rel],
            output_name="out.mp4",
            storage=store,
        )
        raise AssertionError("expected ComposeError")
    except ComposeError as exc:
        assert "exit 7" in str(exc)
    assert not (tmp_path / "media" / "projects" / pid / "output" / "out.mp4").exists()
    meta = tmp_path / "media" / "projects" / pid / "output" / "out.metadata.json"
    assert not meta.exists()


# ---- M8-02 ----


def test_missing_input_image_fails_job_with_path(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m8-missing-image")
    rel = "projects/will-be-replaced/script/ref.png"
    project_id, job_id = _queue_job(
        client,
        "missing-image",
        {
            "prompt": "x",
            "input_image_relative_path": "projects/placeholder/script/ref.png",
        },
    )
    rel = f"projects/{project_id}/script/ref.png"
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        assert job is not None
        params = dict(job.params_json)
        params["input_image_relative_path"] = rel
        job.params_json = params
    missing = tmp_path / "media" / rel
    assert not missing.exists()
    comfy = ComfyClient("http://mock", client=_QueueHttp(prompt_id="unused"))  # type: ignore[arg-type]
    try:
        with session_scope() as session:
            result = run_once(
                session,
                comfy=comfy,
                agent_id="test-agent",
                storage_base=tmp_path / "media",
            )
    finally:
        comfy.close()
    assert result is not None
    assert result["status"] == "failed"
    assert rel in (result.get("error") or "")
    assert str(missing) in (result.get("error") or "")
    assert not missing.exists()


# ---- M8-03 ----


def test_poller_waits_with_job_timeout_default(monkeypatch, tmp_path):
    monkeypatch.delenv("LVS_JOB_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("JOB_TIMEOUT_SEC", raising=False)
    monkeypatch.delenv("LVS_QUEUE_STALL_SEC", raising=False)
    seen: dict[str, float] = {}
    original = ComfyClient.wait_history

    def _spy(self, prompt_id, **kwargs):
        seen["timeout"] = float(kwargs["timeout_sec"])
        seen["stall"] = float(kwargs["stall_sec"])
        return original(self, prompt_id, **kwargs)

    monkeypatch.setattr(ComfyClient, "wait_history", _spy)
    client = _boot(monkeypatch, tmp_path, "m8-timeout-default")
    _queue_job(client, "timeout-default", {"prompt": "x"})

    class _Adapter:
        def __init__(self, app_):
            self._c = TestClient(app_)

        def post(self, url, **kwargs):
            return self._c.post(url, **kwargs)

        def get(self, url, **kwargs):
            return self._c.get(url, **kwargs)

        def close(self) -> None:
            self._c.close()

    comfy = ComfyClient(
        "http://mock",
        client=_Adapter(create_mock_comfy_app(output_dir=tmp_path / "comfy")),  # type: ignore[arg-type]
    )
    try:
        with session_scope() as session:
            result = run_once(
                session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media"
            )
    finally:
        comfy.close()
    assert result is not None and result["status"] == "succeeded"
    assert seen["timeout"] == 7200.0
    assert seen["stall"] == 300.0


def test_queue_stall_fails_wait(monkeypatch):
    http = _QueueHttp(prompt_id="pid-stall", vary_queue=False)
    client = ComfyClient("http://mock", client=http)  # type: ignore[arg-type]
    beats: list[str] = []
    try:
        client.wait_history(
            "pid-stall",
            timeout_sec=5,
            stall_sec=0.05,
            poll_interval=0.01,
            on_heartbeat=beats.append,
        )
        raise AssertionError("expected stall")
    except ComfyClientError as exc:
        assert "pid-stall" in str(exc)
        assert "停滯" in str(exc)
    assert len(beats) >= 2
    client.close()


def test_history_timeout_when_queue_keeps_moving():
    http = _QueueHttp(prompt_id="pid-time", vary_queue=True)
    client = ComfyClient("http://mock", client=http)  # type: ignore[arg-type]
    try:
        client.wait_history(
            "pid-time",
            timeout_sec=0.08,
            stall_sec=10,
            poll_interval=0.02,
        )
        raise AssertionError("expected timeout")
    except ComfyClientError as exc:
        assert "timeout" in str(exc)
        assert "pid-time" in str(exc)
    client.close()


def test_wait_heartbeat_while_history_pending():
    http = _QueueHttp(prompt_id="pid-hb", vary_queue=True, complete_on=2)
    client = ComfyClient("http://mock", client=http)  # type: ignore[arg-type]
    beats: list[str] = []
    entry = client.wait_history(
        "pid-hb",
        timeout_sec=2,
        stall_sec=10,
        poll_interval=0.01,
        on_heartbeat=beats.append,
    )
    assert entry["status"]["completed"] is True
    assert len(beats) >= 2
    assert all("pid-hb" in item for item in beats)
    client.close()


def test_poller_marks_stalled_job_failed(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_QUEUE_STALL_SEC", "0.05")
    monkeypatch.setenv("LVS_COMFY_POLL_INTERVAL_SEC", "0.01")
    monkeypatch.setenv("LVS_JOB_TIMEOUT_SEC", "5")
    client = _boot(monkeypatch, tmp_path, "m8-stall-job")
    _project_id, job_id = _queue_job(client, "stall-job", {"prompt": "x"})
    comfy = ComfyClient(
        "http://mock",
        client=_QueueHttp(prompt_id="from-submit", vary_queue=False),  # type: ignore[arg-type]
    )
    try:
        with session_scope() as session:
            result = run_once(
                session, comfy=comfy, agent_id="test-agent", storage_base=tmp_path / "media"
            )
    finally:
        comfy.close()
    assert result is not None
    assert result["status"] == "failed"
    assert "停滯" in (result.get("error") or "")
    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}").json()
    assert detail["status"] == "failed"


# ---- M8-04 ----


def test_sha256_streams_chunks_and_never_read_bytes(tmp_path, monkeypatch):
    payload = b"abcdefghij"
    path = tmp_path / "weights.bin"
    path.write_bytes(payload)
    from backend.local_video_studio import model_registry as mr

    monkeypatch.setattr(mr, "SHA256_CHUNK_BYTES", 4)
    reads: list[int] = []
    real_open = Path.open

    class _CountingFile:
        def __init__(self, raw):
            self._raw = raw

        def read(self, n=-1):
            data = self._raw.read(n)
            if data:
                reads.append(len(data))
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._raw.close()

    def _tracking_open(self, mode="r", *args, **kwargs):
        fh = real_open(self, mode, *args, **kwargs)
        if self == path and "b" in str(mode):
            return _CountingFile(fh)
        return fh

    real_read_bytes = Path.read_bytes

    def _guard_read_bytes(self, *args, **kwargs):
        if self == path:
            raise AssertionError("path.read_bytes must not be used")
        return real_read_bytes(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", _tracking_open)
    monkeypatch.setattr(Path, "read_bytes", _guard_read_bytes)
    digest = hash_file_sha256(path)
    assert digest == hashlib.sha256(payload).hexdigest()
    assert reads == [4, 4, 2]


def test_verify_sha256_true_is_hard_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_DATABASE_URL", f"sqlite:///{tmp_path / 'sha.sqlite3'}")
    monkeypatch.setenv("LVS_VERIFY_MODEL_SHA256", "true")
    reset_db_state()
    init_db()
    weights = tmp_path / "wan.safetensors"
    weights.write_bytes(b"not-the-hash")
    with session_scope() as session:
        from backend.local_video_studio import model_registry as mr

        mr.register_model(
            session,
            ModelRegister(name="wan_5b", path=str(weights), sha256="f" * 64),
        )
        try:
            validate_required_models(session, ["wan_5b"], models_root=tmp_path)
            raise AssertionError("expected sha mismatch")
        except ModelValidationError as exc:
            assert "wan_5b" in str(exc)
            assert "sha256" in str(exc)

    monkeypatch.setenv("LVS_VERIFY_MODEL_SHA256", "false")
    with session_scope() as session:
        found = validate_required_models(
            session, ["wan_5b"], models_root=tmp_path, check_sha256=False
        )
        assert found[0]["name"] == "wan_5b"

    with session_scope() as session:
        from backend.local_video_studio import model_registry as mr

        mr.register_model(
            session,
            ModelRegister(name="bare_ckpt", path=str(weights), sha256=None),
        )
        monkeypatch.setenv("LVS_VERIFY_MODEL_SHA256", "true")
        try:
            validate_required_models(session, ["bare_ckpt"], models_root=tmp_path)
            raise AssertionError("expected missing sha")
        except ModelValidationError as exc:
            assert "bare_ckpt" in str(exc)


def test_poller_hard_fails_job_when_sha256_mismatches(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_VERIFY_MODEL_SHA256", "true")
    client = _boot(monkeypatch, tmp_path, "m8-sha-job")
    weights = tmp_path / "media" / "models" / "flux.bin"
    weights.parent.mkdir(parents=True)
    weights.write_bytes(b"weights")
    with session_scope() as session:
        from backend.local_video_studio import model_registry as mr

        mr.register_model(
            session,
            ModelRegister(name="flux_dev", path=str(weights), sha256="ab" * 32),
        )
    project_id, job_id = _queue_job(client, "sha-job", {"prompt": "x"})
    with session_scope() as session:
        job = session.get(GenerationJob, job_id)
        assert job is not None
        params = dict(job.params_json)
        params["required_models"] = ["flux_dev"]
        job.params_json = params
    comfy = ComfyClient("http://mock", client=_QueueHttp(prompt_id="nope"))  # type: ignore[arg-type]
    try:
        with session_scope() as session:
            result = run_once(
                session,
                comfy=comfy,
                agent_id="test-agent",
                storage_base=tmp_path / "media",
                models_root=weights.parent,
            )
    finally:
        comfy.close()
    assert result is not None
    assert result["status"] == "failed"
    assert "flux_dev" in (result.get("error") or "")
    assert project_id


# ---- M8-05 ----


def test_ffmpeg_command_maps_audio_subtitles_amix_and_font(tmp_path):
    font = tmp_path / "font.ttf"
    font.write_bytes(b"font")
    concat = tmp_path / "concat.txt"
    concat.write_text("file 'a.mp4'\n", encoding="utf-8")
    voice = tmp_path / "voice.wav"
    bgm = tmp_path / "bgm.mp3"
    voice.write_bytes(b"a")
    bgm.write_bytes(b"b")
    srt = tmp_path / "subtitles.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    out = tmp_path / "final_v1.mp4"
    argv = build_ffmpeg_command(
        concat_path=concat,
        output_path=out,
        audio_paths=[voice, bgm],
        subtitle_path=srt,
        font_path=font,
        watermark_text="AI 生成",
        metadata={"ai_generated": "true"},
    )
    graph = next(argv[i + 1] for i, token in enumerate(argv) if token == "-filter_complex")
    assert "subtitles=" in graph
    assert "amix=inputs=2" in graph
    assert "fontfile=" in graph
    assert "AI 生成" in graph
    assert argv[argv.index("-map") + 1] == "[v]"
    assert "[a]" in argv
    assert "-metadata" in argv


def test_missing_font_does_not_drop_stamp(monkeypatch, tmp_path):
    missing = tmp_path / "no-such-font.ttf"
    monkeypatch.setenv("LVS_DRAWTEXT_FONT", str(missing))
    monkeypatch.delenv("LVS_ALLOW_FAKE_MEDIA", raising=False)
    monkeypatch.setattr(
        "backend.local_video_studio.ffmpeg_compose.shutil.which",
        lambda _name: "/usr/bin/ffmpeg",
    )
    called = {"n": 0}

    def _run(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("ffmpeg must not run without a font")

    monkeypatch.setattr("backend.local_video_studio.ffmpeg_compose.subprocess.run", _run)
    store = LocalPathStorage(tmp_path / "media")
    pid = "font"
    store.ensure_project_dirs(pid)
    rel = f"projects/{pid}/refines/a.mp4"
    store.write_bytes(rel, b"clip")
    try:
        compose_shots(
            project_id=pid,
            clip_relative_paths=[rel],
            storage=store,
            add_watermark=True,
        )
        raise AssertionError("expected ComposeError")
    except ComposeError as exc:
        assert "字型" in str(exc)
        assert str(missing) in str(exc)
        assert "略過" in str(exc)
    assert called["n"] == 0
    assert not (tmp_path / "media" / "projects" / pid / "output" / "final_v1.mp4").exists()


def test_missing_subtitle_file_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "backend.local_video_studio.ffmpeg_compose.shutil.which",
        lambda _name: None,
    )
    monkeypatch.setenv("LVS_ALLOW_FAKE_MEDIA", "true")
    store = LocalPathStorage(tmp_path / "media")
    pid = "sub"
    store.ensure_project_dirs(pid)
    rel = f"projects/{pid}/refines/a.mp4"
    store.write_bytes(rel, b"clip")
    missing = f"projects/{pid}/audio/missing.srt"
    try:
        compose_shots(
            project_id=pid,
            clip_relative_paths=[rel],
            storage=store,
            subtitle_relative_path=missing,
            add_watermark=False,
        )
        raise AssertionError("expected ComposeError")
    except ComposeError as exc:
        assert missing in str(exc)


# ---- M8-06 ----


def test_shutdown_during_wait_requeues_without_failing(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m8-shutdown")
    _project_id, job_id = _queue_job(client, "shutdown", {"prompt": "x"})
    http = _QueueHttp(prompt_id="pid-stop", vary_queue=False)
    comfy = ComfyClient("http://mock", client=http)  # type: ignore[arg-type]
    try:
        with session_scope() as session:
            result = run_once(
                session,
                comfy=comfy,
                agent_id="test-agent",
                storage_base=tmp_path / "media",
                should_stop=lambda: True,
            )
    finally:
        comfy.close()
    assert result is not None
    assert result["status"] == "queued"
    assert result.get("released") is True
    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}").json()
    assert detail["status"] == "queued"
    assert detail["assigned_agent"] is None
    assert detail["error"] is None
    assert detail["attempt"] == 0


def test_expired_lease_requeues_running_job(monkeypatch, tmp_path):
    client = _boot(monkeypatch, tmp_path, "m8-lease")
    _project_id, job_id = _queue_job(client, "lease", {"prompt": "x"})
    with session_scope() as session:
        claim_job(session, job_id, "worker-a")
    path = tmp_path / "media" / "agents" / "worker-a.lease.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "agent_id": "worker-a",
                "job_id": job_id,
                "expires_at": time.time() - 10,
                "status": "held",
            }
        ),
        encoding="utf-8",
    )
    with session_scope() as session:
        released = reclaim_expired_leases(session, tmp_path / "media")
    assert job_id in released
    detail = client.get(f"/local-video-studio/api/v1/jobs/{job_id}").json()
    assert detail["status"] == "queued"
    assert detail["assigned_agent"] is None
    assert detail["attempt"] == 0
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["status"] == "released"


def test_lease_renew_extends_and_release_is_idempotent(tmp_path):
    mgr = LeaseManager(agent_id="worker-b", storage_base=tmp_path, ttl_sec=30)
    first = mgr.acquire("job-1")
    renewed = mgr.renew("job-1")
    assert renewed >= first
    mgr.release("job-1")
    mgr.release("job-1")
    try:
        mgr.renew("job-1")
        raise AssertionError("expected LeaseError")
    except Exception as exc:
        from backend.local_video_studio.agent.lease import LeaseError

        assert isinstance(exc, LeaseError)


def test_signal_handler_requests_shutdown(tmp_path):
    reset_heartbeats()
    stop = __import__("threading").Event()
    handler = build_stop_handler(stop, agent_id="sig-agent", storage_base=tmp_path)
    handler(signal.SIGTERM, None)
    assert stop.is_set()
    beat = latest_heartbeat("sig-agent")
    assert beat is not None
    assert beat["status"] == "shutting_down"
    assert (tmp_path / "agents" / "sig-agent.heartbeat.json").is_file()


def test_daemon_serve_stops_between_cycles(monkeypatch, tmp_path):
    monkeypatch.setenv("LVS_AGENT_ID", "daemon-agent")
    monkeypatch.setenv("LVS_STORAGE_BASE", str(tmp_path))
    reset_heartbeats()
    calls = {"n": 0}

    def _once(**kwargs):
        calls["n"] += 1
        assert callable(kwargs["should_stop"])
        return {"status": "idle"}

    code = serve(
        stop_event=__import__("threading").Event(),
        max_cycles=1,
        poll_interval_sec=0.01,
        run_once_fn=_once,
    )
    assert code == 0
    assert calls["n"] == 1
    beat = latest_heartbeat("daemon-agent")
    assert beat is not None
    assert beat["status"] == "stopped"


def test_agent_module_entrypoint_exits(monkeypatch, tmp_path):
    env = os.environ.copy()
    env["LVS_AGENT_MAX_CYCLES"] = "1"
    env["LVS_AGENT_POLL_INTERVAL_SEC"] = "0.01"
    env["LVS_AGENT_ID"] = "entrypoint-agent"
    env["LVS_STORAGE_BASE"] = str(tmp_path / "media")
    env["LVS_DATABASE_URL"] = f"sqlite:///{tmp_path / 'entry.sqlite3'}"
    env["LVS_CLOUD_ENABLED"] = "false"
    env["CLOUD_ENABLED"] = "false"
    env["PYTHONPATH"] = str(_REPO) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "backend.local_video_studio.agent"],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "lvs-agent stopped" in proc.stdout
    heart = tmp_path / "media" / "agents" / "entrypoint-agent.heartbeat.json"
    assert heart.is_file()
    assert json.loads(heart.read_text(encoding="utf-8"))["status"] == "stopped"
