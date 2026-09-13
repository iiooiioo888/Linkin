"""MediaCrawler 任務狀態機與子進程編排。"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from backend.mediacrawler.config import (
    CrawlJobRequest,
    MediaCrawlerEnvConfig,
    get_stored_cookie,
    load_env_config,
    validate_job_request,
)
from backend.mediacrawler.paths import job_results_dir

logger = logging.getLogger(__name__)

JOB_STATUSES = frozenset({"pending", "validating", "running", "completed", "failed", "cancelled"})


@dataclass
class MediaCrawlerJob:
    job_id: str
    status: str = "pending"
    request: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    error: str = ""
    log_path: str = ""
    results_dir: str = ""
    command: list[str] = field(default_factory=list)
    dry_run: bool = False
    pid: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["duration_seconds"] = None
        if self.started_at is not None:
            end = self.finished_at or time.time()
            data["duration_seconds"] = round(end - self.started_at, 2)
        return data


class MediaCrawlerJobManager:
    def __init__(self, env: MediaCrawlerEnvConfig | None = None) -> None:
        self._env = env or load_env_config()
        self._lock = threading.RLock()
        self._jobs: dict[str, MediaCrawlerJob] = {}
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._load_persisted()

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            return [j.to_dict() for j in items[: max(1, min(limit, 200))]]

    def get_job(self, job_id: str) -> MediaCrawlerJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.status == "running")

    def validate(self, req: CrawlJobRequest) -> dict[str, Any]:
        errors = validate_job_request(req, self._env)
        command = build_command(req, self._env) if not errors else []
        return {
            "valid": not errors,
            "errors": errors,
            "dry_run": req.normalized().dry_run,
            "command": command,
            "status": integration_summary(self._env),
        }

    def submit(self, req: CrawlJobRequest) -> MediaCrawlerJob:
        normalized = req.normalized()
        errors = validate_job_request(normalized, self._env)
        if errors:
            raise ValueError("; ".join(errors))

        with self._lock:
            if self.running_count() >= self._env.max_concurrent_jobs and not normalized.dry_run:
                raise ValueError(f"並發任務已達上限（{self._env.max_concurrent_jobs}）")

            job_id = uuid.uuid4().hex[:12]
            results_dir = job_results_dir(job_id, self._env)
            log_path = results_dir / "job.log"
            command = build_command(normalized, self._env)
            job = MediaCrawlerJob(
                job_id=job_id,
                status="validating" if normalized.dry_run else "pending",
                request=_public_request(normalized),
                log_path=str(log_path),
                results_dir=str(results_dir),
                command=command,
                dry_run=normalized.dry_run,
            )
            self._jobs[job_id] = job
            self._persist()

        if normalized.dry_run:
            self._finish_dry_run(job)
        else:
            threading.Thread(target=self._run_job, args=(job_id, normalized), daemon=True).start()
        return job

    def tail_log(self, job_id: str, max_bytes: int = 64_000) -> str:
        job = self.get_job(job_id)
        if job is None or not job.log_path:
            return ""
        path = Path(job.log_path)
        if not path.is_file():
            return ""
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        if len(data) > max_bytes:
            data = data[-max_bytes:]
        return data.decode("utf-8", errors="replace")

    def _finish_dry_run(self, job: MediaCrawlerJob) -> None:
        with self._lock:
            job.status = "completed"
            job.finished_at = time.time()
            job.started_at = job.created_at
            Path(job.log_path).parent.mkdir(parents=True, exist_ok=True)
            Path(job.log_path).write_text(
                "DRY RUN: configuration validated successfully.\n"
                f"Command: {' '.join(job.command)}\n",
                encoding="utf-8",
            )
            self._persist()

    def _run_job(self, job_id: str, req: CrawlJobRequest) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        env = os.environ.copy()
        cookie = req.cookie or get_stored_cookie(self._env)
        if cookie:
            env["MEDIACRAWLER_COOKIE"] = cookie
        command = job.command
        log_path = Path(job.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            job.status = "running"
            job.started_at = time.time()
            self._persist()

        try:
            with log_path.open("w", encoding="utf-8") as logf:
                logf.write(f"$ {' '.join(command)}\n\n")
                logf.flush()
                proc = subprocess.Popen(
                    command,
                    cwd=str(self._env.home) if self._env.home else None,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    env=env,
                    text=True,
                )
                with self._lock:
                    self._processes[job_id] = proc
                    job.pid = proc.pid
                    self._persist()
                try:
                    proc.wait(timeout=self._env.job_timeout_seconds)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                    raise TimeoutError(f"任務逾時（>{self._env.job_timeout_seconds}s）")
                rc = proc.returncode
            if rc != 0:
                raise RuntimeError(f"MediaCrawler 退出碼 {rc}")
            with self._lock:
                job.status = "completed"
        except Exception as exc:
            logger.warning("MediaCrawler job %s failed: %s", job_id, exc)
            with self._lock:
                job.status = "failed"
                job.error = str(exc)
        finally:
            with self._lock:
                job.finished_at = time.time()
                self._processes.pop(job_id, None)
                self._persist()

    def _load_persisted(self) -> None:
        path = self._env.jobs_store_path
        if not path.is_file():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        rows = raw.get("jobs") if isinstance(raw, dict) else None
        if not isinstance(rows, list):
            return
        for row in rows:
            if not isinstance(row, dict) or not row.get("job_id"):
                continue
            job = MediaCrawlerJob(
                job_id=str(row["job_id"]),
                status=str(row.get("status") or "failed"),
                request=(
                    dict(raw_req)
                    if isinstance((raw_req := row.get("request")), dict)
                    else {}
                ),
                created_at=float(row.get("created_at") or time.time()),
                started_at=row.get("started_at"),
                finished_at=row.get("finished_at"),
                error=str(row.get("error") or ""),
                log_path=str(row.get("log_path") or ""),
                results_dir=str(row.get("results_dir") or ""),
                command=list(row.get("command") or []),
                dry_run=bool(row.get("dry_run")),
                pid=row.get("pid"),
            )
            if job.status == "running":
                job.status = "failed"
                job.error = job.error or "服務重啟導致任務中斷"
            self._jobs[job.job_id] = job

    def _persist(self) -> None:
        path = self._env.jobs_store_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": [j.to_dict() for j in sorted(self._jobs.values(), key=lambda x: x.created_at)]}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


_manager: MediaCrawlerJobManager | None = None


def get_job_manager(env: MediaCrawlerEnvConfig | None = None) -> MediaCrawlerJobManager:
    global _manager
    if _manager is None or (env is not None and env != _manager._env):
        _manager = MediaCrawlerJobManager(env)
    return _manager


def reset_job_manager() -> None:
    global _manager
    _manager = None


def build_command(req: CrawlJobRequest, env: MediaCrawlerEnvConfig | None = None) -> list[str]:
    cfg = env or load_env_config()
    if cfg.home is None:
        return []
    normalized = req.normalized()
    runner = detect_installation_runner(cfg.home)
    if runner == "uv":
        cmd = ["uv", "run", "main.py"]
    else:
        cmd = ["python", "main.py"]
    cmd.extend(["--platform", normalized.platform, "--lt", normalized.login_type, "--type", normalized.crawl_type])
    return cmd


def detect_installation_runner(home: Path) -> str:
    if (home / "uv.lock").is_file() or (home / "pyproject.toml").is_file():
        return "uv"
    return "python"


def _public_request(req: CrawlJobRequest) -> dict[str, Any]:
    data = asdict(req.normalized())
    if data.get("cookie"):
        data["cookie"] = "***"
    return data


def integration_summary(env: MediaCrawlerEnvConfig | None = None) -> dict[str, Any]:
    from backend.mediacrawler.config import integration_status

    return integration_status(env)
