"""Render agent 單步循環：claim → validate models → inject → Comfy → complete。"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from backend.local_video_studio.comfy_client import ComfyClient, ComfyClientError, new_client_id
from backend.local_video_studio.config import load_config
from backend.local_video_studio.job_log import append_job_log
from backend.local_video_studio.jobs import claim_job, complete_job, list_jobs
from backend.local_video_studio.model_registry import ModelValidationError, validate_required_models
from backend.local_video_studio.models import GenerationJob
from backend.local_video_studio.schemas import AssetPayload, JobComplete, ResourcePayload
from backend.local_video_studio.storage import LocalPathStorage
from backend.local_video_studio.workflow_inject import WorkflowMappingError, inject_params
from backend.local_video_studio.workflow_templates import load_template_payload


def _asset_type_for_job(job_type: str) -> str:
    return {
        "keyframe": "keyframe",
        "draft": "draft",
        "refine": "refine",
        "audio": "audio",
    }.get(job_type, "keyframe")


def _ensure_output_path(storage_base: Path, relative: str, payload: bytes) -> tuple[int, str]:
    dest = storage_base / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    return len(payload), digest


def _fail_job(
    session: Session,
    job: GenerationJob,
    exc: BaseException,
    *,
    storage: LocalPathStorage,
) -> dict[str, Any]:
    msg = str(exc)
    append_job_log(
        job.project_id,
        job.id,
        "error",
        msg,
        storage=storage,
        error=msg,
        attempt=job.attempt,
    )
    job.log_relative_path = f"projects/{job.project_id}/logs/{job.id}.log"
    result = complete_job(
        session,
        job.id,
        JobComplete(status="failed", error=msg),
    )
    session.flush()
    return result.model_dump(mode="json")


def run_once(
    session: Session,
    *,
    comfy: ComfyClient | None = None,
    agent_id: str | None = None,
    storage_base: Path | None = None,
    models_root: Path | None = None,
) -> dict[str, Any] | None:
    """處理一個 queued 任務；若無任務回傳 None。"""
    cfg = load_config()
    agent = agent_id or cfg.agent_id
    root = Path(storage_base or cfg.storage_base)
    store = LocalPathStorage(root)

    queued = list_jobs(session, status="queued", unassigned=True)
    if not queued:
        return None
    job_out = queued[0]
    claimed = claim_job(session, job_out.id, agent)
    session.flush()
    row = session.get(GenerationJob, claimed.id)
    assert row is not None

    append_job_log(
        row.project_id,
        row.id,
        "info",
        "claimed",
        storage=store,
        agent=agent,
        workflow_template=row.workflow_template,
        workflow_version=row.workflow_version,
        attempt=row.attempt,
    )
    row.log_relative_path = f"projects/{row.project_id}/logs/{row.id}.log"
    session.flush()

    started = time.monotonic()
    owns_client = False
    if comfy is not None:
        client = comfy
    elif cfg.use_mock_comfy:
        from fastapi.testclient import TestClient

        from backend.local_video_studio.mock_comfyui import create_mock_comfy_app

        class _Adapter:
            def __init__(self, app):
                self._c = TestClient(app)

            def post(self, url, **kwargs):
                return self._c.post(url, **kwargs)

            def get(self, url, **kwargs):
                return self._c.get(url, **kwargs)

            def close(self):
                self._c.close()

        mock_server = create_mock_comfy_app(output_dir=root / "_mock_comfy")
        # _Adapter 是 TestClient 包裝，duck-type 成 httpx.Client；刻意不對齊靜態型別。
        client = ComfyClient(
            cfg.comfyui_url,
            client=_Adapter(mock_server),  # type: ignore[arg-type]
        )
        owns_client = True
    else:
        client = ComfyClient(cfg.comfyui_url)
        owns_client = True
    try:
        template_json, mapping, resolved_ver, tmpl_models = load_template_payload(
            session,
            claimed.workflow_template,
            version=row.workflow_version,
        )
        if resolved_ver is not None and row.workflow_version is None:
            row.workflow_version = resolved_ver
            session.flush()

        params = dict(claimed.params_json or {})
        required = list(params.get("required_models") or []) + list(tmpl_models)
        # 去重保序
        seen: set[str] = set()
        required_unique: list[str] = []
        for name in required:
            key = str(name).strip()
            if key and key not in seen:
                seen.add(key)
                required_unique.append(key)

        if required_unique:
            append_job_log(
                row.project_id,
                row.id,
                "info",
                "validating models",
                storage=store,
                required_models=required_unique,
            )
            validate_required_models(
                session,
                required_unique,
                models_root=models_root or root / "models",
            )

        injected = inject_params(template_json, params, mapping)
        append_job_log(
            row.project_id,
            row.id,
            "info",
            "params injected",
            storage=store,
        )

        input_rel = params.get("input_image_relative_path")
        if input_rel:
            input_path = root / str(input_rel)
            if not input_path.is_file():
                # 測試／缺檔時寫入極小 PNG
                input_path.parent.mkdir(parents=True, exist_ok=True)
                input_path.write_bytes(
                    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
                    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f"
                    b"\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
                )
            uploaded = client.upload_image(input_path)
            for entry in mapping.get("mappings") or []:
                if entry.get("param") == "input_image_relative_path":
                    node = injected.get(str(entry["node_id"]), {})
                    if isinstance(node.get("inputs"), dict):
                        node["inputs"][entry["input"]] = uploaded.get("name", input_path.name)

        prompt_id = client.submit_prompt(injected, new_client_id())
        append_job_log(
            row.project_id,
            row.id,
            "info",
            "comfy submitted",
            storage=store,
            prompt_id=prompt_id,
        )
        hist = client.wait_history(prompt_id, timeout_sec=15.0)
        outputs = hist.get("outputs") or {}
        filename = None
        for node_out in outputs.values():
            for key in ("images", "gifs", "videos"):
                items = node_out.get(key) or []
                if items:
                    filename = items[0].get("filename")
                    break
            if filename:
                break
        if not filename:
            raise ComfyClientError("mock/comfy 未回傳輸出檔名")

        raw = client.fetch_output_bytes(filename)
        folder = {
            "keyframe": "keyframes",
            "draft": "drafts",
            "refine": "refines",
            "audio": "audio",
        }.get(claimed.job_type, "keyframes")
        default_name = filename if "." in filename else f"{claimed.shot_id}_{filename}"
        out_rel = params.get("output_relative_path") or (
            f"projects/{claimed.project_id}/{folder}/{default_name}"
        )
        if isinstance(out_rel, str) and not str(out_rel).startswith("projects/"):
            out_rel = f"projects/{claimed.project_id}/{folder}/{claimed.shot_id}_{filename}"
        size, sha = _ensure_output_path(root, str(out_rel), raw)
        wall = (time.monotonic() - started) / 60.0

        append_job_log(
            row.project_id,
            row.id,
            "info",
            "succeeded",
            storage=store,
            relative_path=str(out_rel),
            bytes=size,
            sha256=sha,
        )
        result = complete_job(
            session,
            claimed.id,
            JobComplete(
                status="succeeded",
                asset=AssetPayload(
                    relative_path=str(out_rel),
                    type=_asset_type_for_job(claimed.job_type),
                    bytes=size,
                    sha256=sha,
                    mime="image/png" if str(out_rel).endswith(".png") else "video/mp4",
                ),
                resource=ResourcePayload(
                    wall_minutes=round(wall, 4),
                    gpu_minutes=round(wall, 4),
                    attempts=claimed.attempt,
                    storage_bytes=size,
                    api_calls=1,
                ),
            ),
        )
        session.flush()
        return result.model_dump(mode="json")
    except (
        ComfyClientError,
        WorkflowMappingError,
        ModelValidationError,
        FileNotFoundError,
        OSError,
    ) as exc:
        return _fail_job(session, row, exc, storage=store)
    finally:
        if owns_client:
            client.close()
