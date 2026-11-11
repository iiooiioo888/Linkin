"""每 job 獨立日誌檔：``projects/{project_id}/logs/{job_id}.log``（JSON Lines）。"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from backend.local_video_studio.storage import LocalPathStorage, get_storage


def log_relative_path(project_id: str, job_id: str) -> str:
    return f"projects/{project_id}/logs/{job_id}.log"


def append_job_log(
    project_id: str,
    job_id: str,
    level: str,
    message: str,
    *,
    storage: LocalPathStorage | None = None,
    **fields: Any,
) -> str:
    """追加一筆 JSON line；回傳相對路徑。"""
    store = storage or get_storage()
    store.ensure_project_dirs(project_id)
    rel = log_relative_path(project_id, job_id)
    path = store.resolve(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "project_id": project_id,
        "level": level,
        "message": message,
        **{k: v for k, v in fields.items() if v is not None},
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return rel


def read_job_log(
    project_id: str,
    job_id: str,
    *,
    storage: LocalPathStorage | None = None,
    tail_lines: int | None = None,
) -> tuple[str, str | None]:
    """回傳 (relative_path, content)；檔案不存在時 content 為 None。"""
    store = storage or get_storage()
    rel = log_relative_path(project_id, job_id)
    path = store.resolve(rel)
    if not path.is_file():
        return rel, None
    text = path.read_text(encoding="utf-8")
    if tail_lines is not None and tail_lines > 0:
        lines = text.splitlines()
        text = "\n".join(lines[-tail_lines:])
        if text:
            text += "\n"
    return rel, text


def error_summary_from_log(content: str | None, fallback: str | None = None) -> str | None:
    """從日誌尾部抽取最後一筆 error level 訊息，否則回 fallback。"""
    if content:
        for line in reversed(content.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(obj.get("level", "")).lower() in {"error", "failed", "exception"}:
                msg = obj.get("message") or obj.get("error")
                if msg:
                    return str(msg)
    return fallback
