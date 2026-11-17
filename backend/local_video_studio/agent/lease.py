"""單工作站任務租約。到期後下一個 daemon 週期把 running job 退回佇列。"""

from __future__ import annotations

import json
import time
from pathlib import Path

from sqlalchemy.orm import Session

from backend.local_video_studio.jobs import requeue_running_job
from backend.local_video_studio.models import GenerationJob


class LeaseError(RuntimeError):
    pass


class LeaseManager:
    def __init__(self, *, agent_id: str, storage_base: Path, ttl_sec: float) -> None:
        self.agent_id = agent_id
        self.ttl_sec = ttl_sec
        self.path = Path(storage_base) / "agents" / f"{agent_id}.lease.json"
        self.job_id: str | None = None

    def _write(self, status: str, job_id: str | None, expires_at: float) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "agent_id": self.agent_id,
            "job_id": job_id,
            "expires_at": expires_at,
            "status": status,
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def acquire(self, job_id: str) -> float:
        expires = time.time() + self.ttl_sec
        self.job_id = job_id
        self._write("held", job_id, expires)
        return expires

    def renew(self, job_id: str) -> float:
        if self.job_id != job_id:
            raise LeaseError(f"沒有可續約的租約：{job_id}")
        expires = time.time() + self.ttl_sec
        self.job_id = job_id
        self._write("held", job_id, expires)
        return expires

    def release(self, job_id: str | None = None) -> None:
        if job_id is not None and self.job_id not in {None, job_id}:
            return
        self.job_id = None
        self._write("released", None, 0)


def reclaim_expired_leases(session: Session, storage_base: Path) -> list[str]:
    """租約已過期且任務仍為 running → 退回 queued。"""
    agents = Path(storage_base) / "agents"
    if not agents.is_dir():
        return []
    now = time.time()
    released: list[str] = []
    for path in sorted(agents.glob("*.lease.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        if not isinstance(data, dict) or data.get("status") != "held":
            continue
        try:
            expires = float(data.get("expires_at") or 0)
        except (TypeError, ValueError):
            expires = 0
        if expires > now:
            continue
        job_id = data.get("job_id")
        agent_id = str(data.get("agent_id") or "")
        if not job_id:
            continue
        job = session.get(GenerationJob, str(job_id))
        if (
            job is not None
            and job.status == "running"
            and (not agent_id or job.assigned_agent == agent_id)
        ):
            requeue_running_job(session, job)
            released.append(job.id)
        data["status"] = "released"
        data["job_id"] = None
        data["expires_at"] = 0
        path.write_text(json.dumps(data), encoding="utf-8")
    return released
