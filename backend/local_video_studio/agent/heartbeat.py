"""Render agent 心跳。覆寫同一份 JSON，避免等待期間把日誌寫爆。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_LATEST: dict[str, dict[str, Any]] = {}


def reset_heartbeats() -> None:
    _LATEST.clear()


def latest_heartbeat(agent_id: str) -> dict[str, Any] | None:
    row = _LATEST.get(agent_id)
    return dict(row) if row else None


def record_heartbeat(
    *,
    agent_id: str,
    status: str,
    job_id: str | None = None,
    detail: str = "",
    storage_base: Path | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "status": status,
        "job_id": job_id,
        "detail": detail,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    _LATEST[agent_id] = payload
    if storage_base is not None:
        path = Path(storage_base) / "agents" / f"{agent_id}.heartbeat.json"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            payload["path"] = str(path)
        except OSError as exc:
            payload["persist_error"] = str(exc)
    return dict(payload)
