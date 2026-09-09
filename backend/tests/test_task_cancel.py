"""任務取消／中斷狀態語義測試。

釘死的行為：
1. 取消後未完成工作項轉 CANCELLED 終態（看板不再錯位）
2. 取消的公司任務保留檢查點 → resumable=True（可斷點續跑）
3. 三條路徑結尾不會把 cancelled 覆蓋成 completed
4. 服務重啟殘留 running → interrupted（非 failed），公司路徑帶檢查點時 resumable
5. 強制中斷（CancelledError）收尾為 cancelled
6. 已結束任務不可再取消；resume 對無檢查點任務明確拒絕
"""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.company.state import WorkItemStatus
from backend.company.work_item import WorkItemManager
from backend.services import task_manager as tm


# ══════════════ 工作項取消 ══════════════


class TestWorkItemCancel:
    PATHS = {
        WorkItemStatus.READY: [WorkItemStatus.READY],
        WorkItemStatus.EXECUTING: [WorkItemStatus.READY, WorkItemStatus.EXECUTING],
        WorkItemStatus.IN_REVIEW: [WorkItemStatus.READY, WorkItemStatus.EXECUTING, WorkItemStatus.IN_REVIEW],
        WorkItemStatus.BLOCKED: [WorkItemStatus.READY, WorkItemStatus.BLOCKED],
        WorkItemStatus.DONE: [WorkItemStatus.READY, WorkItemStatus.EXECUTING, WorkItemStatus.IN_REVIEW, WorkItemStatus.DONE],
    }

    def _mgr_with_items(self):
        mgr = WorkItemManager()
        ids = []
        for i, target in enumerate(self.PATHS):
            item = mgr.create(title=f"項{i}")
            for status in self.PATHS[target]:
                ok, msg = mgr.transition(item.id, status)
                assert ok, msg
            ids.append(item.id)
        return mgr, ids

    def test_cancel_all_pending_marks_unfinished(self):
        mgr, ids = self._mgr_with_items()
        count = mgr.cancel_all_pending("測試取消")
        assert count == 4  # 除 DONE 外全部
        statuses = {mgr.get(i).status for i in ids}
        assert WorkItemStatus.DONE in statuses
        assert statuses - {WorkItemStatus.DONE} == {WorkItemStatus.CANCELLED}

    def test_cancelled_is_terminal(self):
        mgr, ids = self._mgr_with_items()
        mgr.cancel_all_pending()
        cancelled_id = ids[0]
        ok, msg = mgr.transition(cancelled_id, WorkItemStatus.READY)
        assert ok is False

    def test_has_work_remaining_ignores_cancelled(self):
        mgr, ids = self._mgr_with_items()
        assert mgr.has_work_remaining() is True
        mgr.cancel_all_pending()
        assert mgr.has_work_remaining() is False


# ══════════════ TaskManager 狀態語義 ══════════════


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    """隔離的 TaskManager：Redis 關閉、檢查點目錄指到 tmp。"""
    m = tm.TaskManager()
    m._redis_failed = True  # 不碰真實 Redis
    monkeypatch.setattr(tm, "save_checkpoint", lambda tid, data: (tmp_path / f"{tid}.json").write_text(
        json.dumps(data), encoding="utf-8") or str(tmp_path / f"{tid}.json"))
    monkeypatch.setattr(tm, "load_checkpoint", lambda tid: (
        json.loads((tmp_path / f"{tid}.json").read_text(encoding="utf-8"))
        if (tmp_path / f"{tid}.json").exists() else None))
    monkeypatch.setattr(tm, "delete_checkpoint", lambda tid: (tmp_path / f"{tid}.json").unlink(missing_ok=True))
    return m


class TestCancelSemantics:
    def test_cancel_terminal_states_rejected(self, manager):
        rec = manager.create_task("q", "simple", "quick_task")
        rec.status = "completed"
        ok, msg = manager.cancel_task(rec.task_id)
        assert ok is False
        rec.status = "interrupted"
        ok, msg = manager.cancel_task(rec.task_id)
        assert ok is False
        rec.status = "cancelled"
        ok, msg = manager.cancel_task(rec.task_id)
        assert ok is False

    def test_cancel_running_sets_flag(self, manager):
        rec = manager.create_task("q", "simple", "quick_task")
        rec.status = "running"
        ok, msg = manager.cancel_task(rec.task_id)
        assert ok is True
        assert rec.cancel_requested is True
        assert rec.events[-1]["event"] == "cancel_requested"

    def test_check_cancelled_marks_status(self, manager):
        rec = manager.create_task("q", "simple", "quick_task")
        rec.status = "running"
        manager.cancel_task(rec.task_id)
        assert manager._check_cancelled(rec) is True
        assert rec.status == "cancelled"
        assert rec.phase == "cancelled"

    def test_resume_without_checkpoint_rejected(self, manager):
        rec = manager.create_task("q", "company", "quick_task")
        rec.resolved_path = "company"
        rec.status = "failed"
        rec.resumable = False
        ok, msg = manager.resume_task(rec.task_id)
        assert ok is False
        assert "檢查點" in msg

    def test_resume_non_company_rejected(self, manager):
        rec = manager.create_task("q", "simple", "quick_task")
        rec.resolved_path = "simple"
        rec.status = "failed"
        rec.resumable = True
        ok, msg = manager.resume_task(rec.task_id)
        assert ok is False


class TestForceCancel:
    def test_unified_task_cancelled_error_finalizes(self, manager):
        """強制中斷：CancelledError 收尾為 cancelled 且公司路徑可續跑。"""
        rec = manager.create_task("q", "company", "quick_task")
        rec.resolved_path = "company"

        async def boom(_record):
            raise asyncio.CancelledError

        manager._run_company_task = boom  # type: ignore[method-assign]

        async def scenario():
            task = asyncio.create_task(manager._run_unified_task(rec))
            manager._running_tasks[rec.task_id] = task
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

        asyncio.run(scenario())
        assert rec.status == "cancelled"
        assert rec.resumable is True
        assert rec.task_id not in manager._running_tasks

    def test_running_task_registry_cleaned_on_normal_finish(self, manager):
        rec = manager.create_task("q", "simple", "quick_task")

        async def ok_path(_record):
            _record.status = "completed"

        manager._run_simple_task = ok_path  # type: ignore[method-assign]

        async def scenario():
            task = asyncio.create_task(manager._run_unified_task(rec))
            manager._running_tasks[rec.task_id] = task
            await task

        asyncio.run(scenario())
        assert rec.status == "completed"
        assert rec.task_id not in manager._running_tasks


class TestRestartInterrupt:
    def test_rehydrate_marks_interrupted_not_failed(self, manager, tmp_path, monkeypatch):
        """重啟殘留 running → interrupted；公司路徑有檢查點則 resumable。"""
        rec = manager.create_task("公司任務", "company", "quick_task")
        rec.resolved_path = "company"
        rec.status = "running"
        # 假裝有檢查點
        tm.save_checkpoint(rec.task_id, {"phase": "execute_review"})

        fake = FakeRedis({tm.TASK_KEY_PREFIX + rec.task_id: json.dumps(_snapshot(rec))})
        monkeypatch.setattr(manager, "_get_redis", lambda: fake)
        manager.tasks.clear()
        loaded = manager.rehydrate()
        assert loaded == 1
        restored = manager.tasks[rec.task_id]
        assert restored.status == "interrupted"
        assert restored.resumable is True

    def test_rehydrate_simple_not_resumable(self, manager, monkeypatch):
        rec = manager.create_task("簡單任務", "simple", "quick_task")
        rec.resolved_path = "simple"
        rec.status = "running"
        fake = FakeRedis({tm.TASK_KEY_PREFIX + rec.task_id: json.dumps(_snapshot(rec))})
        monkeypatch.setattr(manager, "_get_redis", lambda: fake)
        manager.tasks.clear()
        manager.rehydrate()
        restored = manager.tasks[rec.task_id]
        assert restored.status == "interrupted"
        assert restored.resumable is False


class FakeRedis:
    def __init__(self, data: dict[str, str]):
        self._data = dict(data)

    def scan_iter(self, match=None, count=None):
        import fnmatch
        return iter([k for k in self._data if fnmatch.fnmatch(k, match or "*")])

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value, **kwargs):
        self._data[key] = value
        return True

    def setex(self, key, ttl, value):
        self._data[key] = value
        return True


def _snapshot(rec) -> dict:
    return rec.to_snapshot()
