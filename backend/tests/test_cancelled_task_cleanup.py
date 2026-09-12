"""已取消任務 TTL 磁碟回收測試。"""

from __future__ import annotations

import time

import pytest

from backend.company.run_log import append_run_record, run_log_path
from backend.company.seat_io import seat_log_path
from backend.services import task_manager as tm
from backend.services.cancelled_task_cleanup import (
    is_eligible_record,
    is_past_ttl,
    purge_task_artifacts,
    resolve_run_id,
    run_cleanup,
    terminal_timestamp,
    ttl_seconds,
)
from backend.services.trace_logger import (
    checkpoint_path,
    delete_trace,
    save_checkpoint,
    trace_path,
)


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    trace_root = tmp_path / "traces"
    ckpt_root = tmp_path / "checkpoints"
    run_root = tmp_path / "company_runs"
    trace_root.mkdir()
    ckpt_root.mkdir()
    run_root.mkdir()
    monkeypatch.setenv("EVOL_TRACE_DIR", str(trace_root))
    monkeypatch.setenv("EVOL_CHECKPOINT_DIR", str(ckpt_root))
    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(run_root))
    monkeypatch.setenv("LINKIN_CANCELLED_TASK_TTL_HOURS", "0.001")
    monkeypatch.delenv("LINKIN_CANCELLED_TASK_TTL_DAYS", raising=False)
    m = tm.TaskManager()
    m._redis_failed = True
    return m


def _write_file(path, content: str = "x" * 100) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    old = time.time() - 3600
    path.touch()
    import os

    os.utime(path, (old, old))


def _cancelled_record(task_id: str = "abc123456789", *, age_seconds: float = 7200.0) -> tm.TaskRecord:
    record = tm.TaskRecord(task_id, "test query", "auto", "quick_task")
    record.status = "cancelled"
    record.finished_at = time.time() - age_seconds
    record.resolved_path = "company"
    record.resumable = True
    return record


class TestCancelledTaskCleanup:
    def test_ttl_hours_override(self, monkeypatch):
        monkeypatch.setenv("LINKIN_CANCELLED_TASK_TTL_HOURS", "2")
        monkeypatch.delenv("LINKIN_CANCELLED_TASK_TTL_DAYS", raising=False)
        assert ttl_seconds() == 7200.0

    def test_terminal_timestamp_uses_finished_at(self):
        record = _cancelled_record()
        assert terminal_timestamp(record) == record.finished_at

    def test_is_past_ttl_with_short_hours(self, manager):
        record = _cancelled_record(age_seconds=7200.0)
        assert is_past_ttl(record) is True
        recent = _cancelled_record(age_seconds=1.0)
        assert is_past_ttl(recent) is False

    def test_eligible_only_cancelled_by_default(self, manager):
        record = _cancelled_record()
        assert is_eligible_record(record) is True
        failed = _cancelled_record()
        failed.status = "failed"
        assert is_eligible_record(failed) is False

    def test_purge_deletes_trace_checkpoint_and_company_runs(self, manager, tmp_path):
        task_id = "deadbeef1234"
        run_id = "run" * 8
        _write_file(trace_path(task_id))
        save_checkpoint(task_id, {"task_id": task_id, "run_id": run_id, "goal": "g"})
        _write_file(run_log_path(run_id))
        _write_file(seat_log_path(run_id))

        result = purge_task_artifacts(task_id, run_id=run_id)
        assert result.files_deleted == 4
        assert result.bytes_freed >= 400
        assert not trace_path(task_id).exists()
        assert not checkpoint_path(task_id).exists()
        assert not run_log_path(run_id).exists()
        assert not seat_log_path(run_id).exists()

    def test_run_cleanup_purges_expired_cancelled_task(self, manager):
        task_id = "cafebabef00d"
        run_id = "abc" * 10 + "ab"
        record = _cancelled_record(task_id)
        manager.tasks[task_id] = record
        _write_file(trace_path(task_id))
        save_checkpoint(task_id, {"task_id": task_id, "run_id": run_id})
        _write_file(run_log_path(run_id))

        summary = run_cleanup(manager)
        assert summary.tasks_purged == 1
        assert summary.files_deleted >= 3
        assert task_id not in manager.tasks
        assert not trace_path(task_id).exists()

    def test_run_cleanup_skips_recent_cancelled(self, manager, monkeypatch):
        monkeypatch.setenv("LINKIN_CANCELLED_TASK_TTL_HOURS", "24")
        task_id = "recentcancel1"
        record = _cancelled_record(task_id, age_seconds=60.0)
        manager.tasks[task_id] = record
        _write_file(trace_path(task_id))

        summary = run_cleanup(manager)
        assert summary.tasks_purged == 0
        assert trace_path(task_id).exists()

    def test_run_cleanup_skips_completed(self, manager):
        task_id = "completedtask1"
        record = tm.TaskRecord(task_id, "q", "auto", "quick_task")
        record.status = "completed"
        record.finished_at = time.time() - 99999
        manager.tasks[task_id] = record
        _write_file(trace_path(task_id))

        summary = run_cleanup(manager)
        assert summary.tasks_purged == 0
        assert trace_path(task_id).exists()

    def test_orphan_files_purged_without_record(self, manager):
        task_id = "orphantask001"
        _write_file(trace_path(task_id))
        summary = run_cleanup(manager)
        assert summary.orphan_files_purged == 1
        assert not trace_path(task_id).exists()

    def test_resolve_run_id_from_checkpoint(self, manager):
        task_id = "resolve0000001"
        run_id = "feed" * 8
        save_checkpoint(task_id, {"task_id": task_id, "run_id": run_id})
        assert resolve_run_id(task_id) == run_id

    def test_resolve_run_id_from_run_log(self, manager):
        task_id = "resolve0000002"
        run_id = "beef" * 8
        append_run_record(
            {
                "run_id": run_id,
                "task_id": task_id,
                "event": "company_start",
                "ts": "2026-01-01T00:00:00+00:00",
            }
        )
        assert resolve_run_id(task_id) == run_id

    def test_purge_is_idempotent(self, manager):
        task_id = "idempotent001"
        _write_file(trace_path(task_id))
        first = purge_task_artifacts(task_id)
        second = purge_task_artifacts(task_id)
        assert first.files_deleted == 1
        assert second.files_deleted == 0

    def test_include_failed_when_enabled(self, manager, monkeypatch):
        monkeypatch.setenv("LINKIN_CANCELLED_TASK_CLEANUP_INCLUDE_FAILED", "true")
        task_id = "failedtask0001"
        record = _cancelled_record(task_id)
        record.status = "failed"
        manager.tasks[task_id] = record
        _write_file(trace_path(task_id))

        summary = run_cleanup(manager)
        assert summary.tasks_purged == 1
        assert not trace_path(task_id).exists()

    def test_delete_trace_helper(self, manager):
        task_id = "tracehelper01"
        _write_file(trace_path(task_id))
        assert delete_trace(task_id) is True
        assert delete_trace(task_id) is False
