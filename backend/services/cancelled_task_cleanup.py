"""已取消／失敗任務的磁碟與 Redis 過期清理。

依 `LINKIN_CANCELLED_TASK_TTL_*` 回收 checkpoints、traces、
company_runs（run_/seat_ JSONL）與任務 Redis 記錄。預設僅處理
`cancelled`；可選納入 `failed`／`interrupted`。
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.company.run_log import run_log_dir, run_log_path
from backend.company.seat_io import seat_log_path
from backend.services.trace_logger import (
    checkpoint_dir,
    checkpoint_path,
    delete_checkpoint,
    delete_trace,
    load_checkpoint,
    trace_dir,
    trace_path,
)

if TYPE_CHECKING:
    from backend.services.task_manager import TaskManager, TaskRecord

logger = logging.getLogger(__name__)

_TERMINAL_PHASES = frozenset({"cancelled", "failed", "interrupted", "done"})


@dataclass
class PurgeResult:
    task_id: str
    files_deleted: int = 0
    bytes_freed: int = 0
    record_purged: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass
class CleanupSummary:
    tasks_scanned: int = 0
    tasks_purged: int = 0
    orphan_files_purged: int = 0
    files_deleted: int = 0
    bytes_freed: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tasks_scanned": self.tasks_scanned,
            "tasks_purged": self.tasks_purged,
            "orphan_files_purged": self.orphan_files_purged,
            "files_deleted": self.files_deleted,
            "bytes_freed": self.bytes_freed,
            "errors": self.errors,
        }


def cleanup_enabled() -> bool:
    raw = os.getenv("LINKIN_CANCELLED_TASK_CLEANUP_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def cleanup_interval_seconds() -> int:
    return max(60, int(os.getenv("LINKIN_CANCELLED_TASK_CLEANUP_INTERVAL_SEC", "3600")))


def ttl_seconds() -> float:
    """過期 TTL（秒）。`LINKIN_CANCELLED_TASK_TTL_HOURS` 優先於 DAYS。"""
    hours_raw = os.getenv("LINKIN_CANCELLED_TASK_TTL_HOURS", "").strip()
    if hours_raw:
        return max(0.0, float(hours_raw)) * 3600.0
    days = float(os.getenv("LINKIN_CANCELLED_TASK_TTL_DAYS", "7"))
    return max(0.0, days) * 86400.0


def include_failed() -> bool:
    raw = os.getenv("LINKIN_CANCELLED_TASK_CLEANUP_INCLUDE_FAILED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def include_interrupted() -> bool:
    raw = os.getenv("LINKIN_CANCELLED_TASK_CLEANUP_INCLUDE_INTERRUPTED", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def eligible_statuses() -> frozenset[str]:
    statuses = {"cancelled"}
    if include_failed():
        statuses.add("failed")
    if include_interrupted():
        statuses.add("interrupted")
    return frozenset(statuses)


def terminal_timestamp(record: TaskRecord, *, now: float | None = None) -> float:
    """推斷任務進入終態的時間戳（秒）。"""
    if record.finished_at is not None:
        return record.finished_at
    for event in reversed(record.events):
        if event.get("event") == "phase_change":
            phase = (event.get("data") or {}).get("phase", "")
            if phase in _TERMINAL_PHASES:
                return float(event.get("ts") or record.created_at)
    if record.events:
        return float(record.events[-1].get("ts") or record.created_at)
    return float(record.created_at)


def is_past_ttl(record: TaskRecord, *, now: float | None = None) -> bool:
    now = time.time() if now is None else now
    ttl = ttl_seconds()
    if ttl <= 0:
        return True
    return (now - terminal_timestamp(record, now=now)) >= ttl


def is_eligible_record(record: TaskRecord, *, now: float | None = None) -> bool:
    if record.status not in eligible_statuses():
        return False
    if record.status in ("running", "pending", "completed"):
        return False
    return is_past_ttl(record, now=now)


def resolve_run_id(task_id: str) -> str | None:
    """由檢查點或 company_runs 掃描解析 run_id。"""
    checkpoint = load_checkpoint(task_id)
    if isinstance(checkpoint, dict):
        run_id = checkpoint.get("run_id")
        if run_id:
            return str(run_id)
    directory = run_log_dir()
    if not directory.exists():
        return None
    for path in directory.glob("run_*.jsonl"):
        run_id = path.stem.removeprefix("run_")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for _ in range(20):
                    line = handle.readline()
                    if not line:
                        break
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("task_id") == task_id:
                        return run_id
        except OSError:
            continue
    for path in directory.glob("seat_*.jsonl"):
        run_id = path.stem.removeprefix("seat_")
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for _ in range(5):
                    line = handle.readline()
                    if not line:
                        break
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if row.get("task_id") == task_id:
                        return run_id
        except OSError:
            continue
    return None


def _safe_unlink(path: Path) -> tuple[int, str | None]:
    if not path.exists():
        return 0, None
    try:
        size = path.stat().st_size
        path.unlink()
        return size, None
    except OSError as exc:
        return 0, f"{path}: {exc}"


def purge_task_artifacts(
    task_id: str,
    *,
    run_id: str | None = None,
    purge_record: bool = False,
    task_manager: TaskManager | None = None,
) -> PurgeResult:
    """刪除單一任務的磁碟產物（冪等、逐檔 fail-soft）。"""
    result = PurgeResult(task_id=task_id)
    paths: list[Path] = [
        trace_path(task_id),
        checkpoint_path(task_id),
    ]
    resolved_run_id = run_id or resolve_run_id(task_id)
    if resolved_run_id:
        paths.extend([run_log_path(resolved_run_id), seat_log_path(resolved_run_id)])

    for path in paths:
        freed, err = _safe_unlink(path)
        if err:
            result.errors.append(err)
        elif freed:
            result.files_deleted += 1
            result.bytes_freed += freed

    if purge_record and task_manager is not None:
        if task_manager.delete_task_record(task_id):
            result.record_purged = True
        else:
            result.errors.append(f"task record delete failed: {task_id}")

    if result.files_deleted or result.record_purged:
        logger.info(
            "已清理任務產物 task_id=%s files=%d bytes=%d record=%s",
            task_id,
            result.files_deleted,
            result.bytes_freed,
            result.record_purged,
        )
    return result


def _orphan_task_ids_from_disk() -> dict[str, float]:
    """從磁碟檔名推斷 task_id → 最舊 mtime（無 Redis 記錄時的兜底）。"""
    orphans: dict[str, float] = {}
    trace_root = trace_dir()
    if trace_root.exists():
        for path in trace_root.glob("trace_*.jsonl"):
            task_id = path.stem.removeprefix("trace_")
            if not task_id:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            orphans[task_id] = min(orphans.get(task_id, mtime), mtime)
    ckpt_root = checkpoint_dir()
    if ckpt_root.exists():
        for path in ckpt_root.glob("checkpoint_*.json"):
            task_id = path.stem.removeprefix("checkpoint_")
            if not task_id:
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            orphans[task_id] = min(orphans.get(task_id, mtime), mtime)
    return orphans


def run_cleanup(
    task_manager: TaskManager | None = None,
    *,
    now: float | None = None,
) -> CleanupSummary:
    """掃描 eligible 任務與孤兒檔案，執行過期清理。"""
    from backend.services.task_manager import task_manager as default_manager

    manager = task_manager or default_manager
    now = time.time() if now is None else now
    summary = CleanupSummary()
    purged_ids: set[str] = set()

    records = manager.iter_all_records()
    summary.tasks_scanned = len(records)
    known_ids = {record.task_id for record in records}

    for record in records:
        if not is_eligible_record(record, now=now):
            continue
        run_id = resolve_run_id(record.task_id)
        result = purge_task_artifacts(
            record.task_id,
            run_id=run_id,
            purge_record=True,
            task_manager=manager,
        )
        summary.tasks_purged += 1
        purged_ids.add(record.task_id)
        summary.files_deleted += result.files_deleted
        summary.bytes_freed += result.bytes_freed
        summary.errors.extend(result.errors)

    ttl = ttl_seconds()
    if ttl > 0:
        for task_id, mtime in _orphan_task_ids_from_disk().items():
            if task_id in known_ids or task_id in purged_ids:
                continue
            if (now - mtime) < ttl:
                continue
            result = purge_task_artifacts(task_id, purge_record=False)
            if result.files_deleted:
                summary.orphan_files_purged += 1
                summary.files_deleted += result.files_deleted
                summary.bytes_freed += result.bytes_freed
                summary.errors.extend(result.errors)

    if summary.tasks_purged or summary.orphan_files_purged:
        logger.info(
            "取消任務清理完成：tasks=%d orphans=%d files=%d bytes=%d",
            summary.tasks_purged,
            summary.orphan_files_purged,
            summary.files_deleted,
            summary.bytes_freed,
        )
    return summary
