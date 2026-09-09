"""公司任務軌跡鏡像測試：CompanyEvent→trace、llm_trace 鉤子、read_trace 篩選。"""

import json
import os

import pytest

os.environ.setdefault("EVOL_TRACE_DIR", "")  # conftest 已提供測試目錄


@pytest.fixture()
def trace_env(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_TRACE_DIR", str(tmp_path))
    return tmp_path


class TestCompanyEventMirror:
    def test_log_company_event_promotes_fields(self, trace_env):
        from backend.services.trace_logger import TraceLogger, read_trace

        tracer = TraceLogger("t_mirror")
        tracer.log_company_event("work_item_done", {
            "item_id": "i1", "title": "寫模組", "role": "js_dev",
            "cost": 0.01, "output": "def f(): ...", "thinking": "先想",
        })
        tracer.log_company_event("review_pass", {"item_id": "i1", "rounds": 1, "score": 8.5})
        tracer.log_company_event("phase_change", {"phase": "synthesize"})

        events = read_trace("t_mirror", limit=100)
        assert len(events) == 3
        done, review, phase = events
        assert done["event"] == "work_item_done"
        assert done["role"] == "js_dev"
        assert done["item_id"] == "i1"
        assert done["title"] == "寫模組"
        assert done["output"] == "def f(): ..."
        # 缺 role 的審查類事件自動歸位 reviewer
        assert review["role"] == "reviewer"
        # phase 事件保留 phase 欄位
        assert phase["phase"] == "synthesize"
        # 序號連續
        assert [e["seq"] for e in events] == [1, 2, 3]

    def test_read_trace_filters(self, trace_env):
        from backend.services.trace_logger import (
            TraceLogger,
            read_trace,
            trace_event_counts,
        )

        tracer = TraceLogger("t_filter")
        for i in range(3):
            tracer.log_company_event("work_item_done", {"item_id": f"i{i%2}", "role": f"r{i%2}", "output": "x"})
        tracer.log_company_event("review_pass", {"item_id": "i0"})
        tracer.log_llm_call(prompt="p", response="r", role="r1", item_id="i1", phase="execute")

        assert read_trace("t_filter", 100, 0, role="r0")
        only_r0 = read_trace("t_filter", 100, 0, role="r0")
        assert all(e["role"] == "r0" for e in only_r0)
        assert len(only_r0) == 2

        by_event = read_trace("t_filter", 100, 0, event="work_item_done,llm_call")
        assert {e["event"] for e in by_event} == {"work_item_done", "llm_call"}

        by_item = read_trace("t_filter", 100, 0, item_id="i1")
        assert all(e["item_id"] == "i1" for e in by_item)

        counts = trace_event_counts("t_filter")
        assert counts["work_item_done"] == 3
        assert counts["llm_call"] == 1

    def test_llm_trace_hook_gating(self, trace_env, monkeypatch):
        """contextvar 未啟用時 call_llm 不觸發鉤子；啟用時觸發並帶上下文。"""
        from backend.core import llm_trace

        captured: list[dict] = []
        llm_trace.register_hook(captured.append)
        try:
            llm_trace.trace_task_id.set("t_hook")
            llm_trace.emit({"prompt": "p", "response": "r"})
            # emit 直接繞過 call_llm 但受 enabled 閘門約束
            assert captured == []  # trace_enabled 默認 False
            llm_trace.trace_enabled.set(True)
            llm_trace.trace_role.set("tester")
            llm_trace.emit({"prompt": "p", "response": "r"})
            assert len(captured) == 1
            entry = captured[0]
            assert entry["task_id"] == "t_hook"
            assert entry["role"] == "tester"
        finally:
            llm_trace.unregister_hook(captured.append)
            llm_trace.trace_enabled.set(False)
            llm_trace.trace_task_id.set("")
            llm_trace.trace_role.set("")

    def test_llm_call_full_flag_no_truncation(self, trace_env):
        from backend.services.trace_logger import TraceLogger, read_trace

        big = "甲" * 20000
        tracer = TraceLogger("t_full")
        tracer.log_llm_call(prompt=big, response="resp", full=True)
        tracer.log_llm_call(prompt=big, response="resp")
        events = read_trace("t_full", 100, 0)
        assert len(events[0]["prompt"]) == 20000
        assert len(events[1]["prompt"]) == 8000


class TestTaskManagerWiring:
    def test_listener_mirrors_company_events_to_trace(self, trace_env, monkeypatch):
        """_attach_company_listener 把 CompanyEvent 鏡像進 trace_<task_id>.jsonl。"""
        import asyncio

        from backend.company.events import CompanyEvent, EventBus
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import BUILTIN_TEMPLATES
        from backend.services.task_manager import TaskManager, TaskRecord
        from backend.services.trace_logger import read_trace

        # 隔離持久化與 WS 廣播
        monkeypatch.setenv("REDIS_URL", "redis://localhost:1/15")
        mgr = TaskManager()
        monkeypatch.setattr(mgr, "_persist", lambda record: None)
        monkeypatch.setattr(mgr, "_broadcast_event", lambda *a, **k: None)

        record = TaskRecord("t_wire", "做個網站", "company", "quick_task")
        orch = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        mgr._attach_company_listener(record, orch)

        orch.events.emit(CompanyEvent.WORK_ITEM_START, {
            "item_id": "i1", "title": "首頁", "assignee": "js_dev",
        })
        orch.events.emit(CompanyEvent.REVIEW_PASS, {"item_id": "i1", "rounds": 1, "score": 9})

        events = read_trace("t_wire", 100)
        names = [e["event"] for e in events]
        assert "work_item_start" in names and "review_pass" in names
        start = next(e for e in events if e["event"] == "work_item_start")
        assert start["role"] == "js_dev"
        assert start["item_id"] == "i1"
        # tracer 注入到 orchestrator（seat_io 全文軌跡用）
        assert orch.tracer is not None
