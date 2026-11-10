"""公司任務在用戶確認前不能進入席位執行。"""

from __future__ import annotations

import pytest

from backend.company.execution_gate import ExecutionNotApproved, require_user_approved
from backend.services.task_manager import TaskManager


@pytest.fixture()
def manager(monkeypatch):
    m = TaskManager()
    m._redis_failed = True
    monkeypatch.setattr("backend.services.task_manager.task_manager", m)
    return m


def test_require_user_approved_blocks_until_locked(monkeypatch):
    from types import SimpleNamespace

    record = SimpleNamespace(budget_plan={"status": "pending_user"})

    class Stub:
        def get_task(self, task_id, skip_tenant_check=False):
            return record

    monkeypatch.setattr("backend.services.task_manager.task_manager", Stub())
    with pytest.raises(ExecutionNotApproved):
        require_user_approved("task-1")
    record.budget_plan["status"] = "locked"
    require_user_approved("task-1")
    require_user_approved("")


def test_run_company_without_lock_does_not_execute(monkeypatch):
    from backend.company.orchestrator import CompanyOrchestrator
    from backend.core.company_nodes import run_company

    called = {"n": 0}

    async def _execute(self, *args, **kwargs):
        called["n"] += 1
        return {"success": True, "final_output": "不該出現"}

    monkeypatch.setattr(CompanyOrchestrator, "execute", _execute)
    result = run_company({"query": "做一個完整系統", "company_template": "quick_task"})
    assert called["n"] == 0
    assert result["company_result"]["awaiting_confirmation"] is True


@pytest.mark.asyncio
async def test_draft_waits_and_reject_does_not_start(manager):
    async def fake_compose(record):
        return {
            "status": "pending_user",
            "version": 1,
            "feasibility": "go",
            "execution_plan": "先做頁面",
            "lines": [{
                "line_id": "0",
                "title": "頁面",
                "assignee": "developer",
                "subject": "unfilled",
                "assumption": "未登記",
                "amount_usd": None,
            }],
            "risks": [],
            "assumptions": [],
            "confirmation": None,
            "ledger": {"reserved_credits": 0, "frozen": False},
            "deadline": None,
        }

    started: list[str] = []
    import backend.company.execution_gate as gate

    original = gate.compose_budget_draft
    gate.compose_budget_draft = fake_compose
    try:
        record = manager.create_task("做登入頁", "company", "quick_task")
        manager.start_budget_draft(record)
        draft = manager._running_tasks[record.task_id]
        await draft
        assert record.status == "awaiting_confirmation"
        assert record.budget_plan["status"] == "pending_user"
        assert record.budget_plan["lines"][0]["assumption"] == "未登記"
        manager.start_task = lambda rec: started.append(rec.task_id)  # type: ignore[method-assign]
        ok, message = manager.decide_budget(record.task_id, "reject")
        assert ok is True
        assert "不會執行" in message
        assert record.status == "rejected"
        assert started == []
    finally:
        gate.compose_budget_draft = original


@pytest.mark.asyncio
async def test_approve_locks_then_starts(manager):
    async def fake_compose(record):
        return {
            "status": "pending_user",
            "version": 1,
            "feasibility": "go",
            "execution_plan": "草案",
            "lines": [],
            "risks": [],
            "assumptions": [],
            "confirmation": None,
            "ledger": {"reserved_credits": 0, "frozen": False},
            "deadline": None,
        }

    started: list[str] = []
    import backend.company.execution_gate as gate

    gate.compose_budget_draft = fake_compose
    record = manager.create_task("做登入頁", "company", "quick_task")
    manager.start_budget_draft(record)
    await manager._running_tasks[record.task_id]
    manager.start_task = lambda rec: started.append(rec.task_id)  # type: ignore[method-assign]
    ok, _message = manager.decide_budget(record.task_id, "approve")
    assert ok is True
    assert record.budget_plan["status"] == "locked"
    assert record.budget_plan["ledger"]["frozen"] is True
    assert started == [record.task_id]


def test_expired_confirmation_does_not_start(manager):
    record = manager.create_task("做登入頁", "company", "quick_task")
    record.resolved_path = "company"
    record.status = "awaiting_confirmation"
    record.budget_plan = {
        "status": "pending_user",
        "deadline": 1,
        "ledger": {"frozen": False},
    }
    started: list[str] = []
    manager.start_task = lambda rec: started.append(rec.task_id)  # type: ignore[method-assign]
    ok, message = manager.decide_budget(record.task_id, "approve")
    assert ok is False
    assert record.status == "expired"
    assert started == []
    assert "執行" in message or "結束" in message
