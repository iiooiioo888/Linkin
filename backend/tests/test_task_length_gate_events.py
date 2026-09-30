"""Task API / SSE 須 surfaced 長度守門結果（與 LangGraph 狀態一致）。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core import nodes
from backend.services.task_manager import TaskManager, TaskRecord


def _evaluation(score: float) -> str:
    return json.dumps({"score": score, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)


class TestLengthGateEventFields:
    def test_ok_compliance_only_includes_compliance_dict(self):
        state = {
            "length_compliance": {
                "status": "ok",
                "actual_chars": 10,
                "target_chars": 800,
                "rewrites": 0,
            },
            "length_warning": False,
            "length_refused": False,
        }
        fields = nodes.length_gate_event_fields(state)
        assert fields["length_compliance"]["status"] == "ok"
        assert "length_warning" not in fields
        assert "length_refused" not in fields

    def test_failed_includes_warning_and_compliance(self):
        state = {
            "length_compliance": {
                "status": "failed",
                "actual_chars": 1000,
                "target_chars": 800,
                "rewrites": 2,
            },
            "length_warning": True,
            "length_refused": False,
        }
        fields = nodes.length_gate_event_fields(state)
        assert fields["length_compliance"]["status"] == "failed"
        assert fields["length_warning"] is True

    def test_refused_includes_refused_flag(self):
        state = {
            "length_compliance": {
                "status": "failed",
                "actual_chars": 1000,
                "target_chars": 800,
                "rewrites": 2,
            },
            "length_warning": False,
            "length_refused": True,
        }
        fields = nodes.length_gate_event_fields(state)
        assert fields["length_refused"] is True


class TestTaskManagerLengthGateEvents:
    @pytest.mark.asyncio
    async def test_failed_compliance_on_first_evaluation_event(self, monkeypatch):
        """守門預算用盡後，evaluation 事件須帶 length_compliance.status=failed。"""
        monkeypatch.delenv("EVOL_FAIL_CLOSED_ON_LENGTH", raising=False)
        monkeypatch.delenv("EVOL_MIN_LENGTH_ACCEPT_RATIO", raising=False)

        fake = MagicMock(side_effect=[_evaluation(9.0)])
        store = MagicMock()
        store.search_similar.return_value = []
        record = TaskRecord("task-len-ev", "什麼是 Python？", "simple", "quick_task")
        record.resolved_path = "simple"
        long_answer = "說" * 1000
        state = {
            "query": record.query,
            "session_id": record.task_id,
            "task_complexity": "simple",
            "initial_answer": long_answer,
            "current_answer": long_answer,
            "length_rewrites": 2,
            "length_best_answer": long_answer,
            "iteration": 0,
        }
        mgr = TaskManager()
        with (
            patch("backend.core.nodes.call_llm", fake),
            patch("backend.core.evaluation.call_llm", fake),
            patch("backend.core.nodes._memory_store", store),
        ):
            await mgr._run_reflection_loop(record, state, MagicMock())

        eval_events = [e for e in record.events if e.get("event") == "evaluation"]
        assert eval_events, record.events
        first = eval_events[0]["data"]
        assert first["length_compliance"]["status"] == "failed"
        assert first["length_warning"] is True
        assert first.get("length_refused") is not True

    @pytest.mark.asyncio
    async def test_refused_path_surfaces_on_task_finished_payload(self, monkeypatch):
        monkeypatch.setenv("EVOL_FAIL_CLOSED_ON_LENGTH", "true")

        fake = MagicMock(side_effect=[_evaluation(9.0)])
        store = MagicMock()
        store.search_similar.return_value = []
        record = TaskRecord("task-len-refuse", "什麼是 Python？", "simple", "quick_task")
        record.resolved_path = "simple"
        long_answer = "說" * 1000
        state = {
            "query": record.query,
            "session_id": record.task_id,
            "task_complexity": "simple",
            "initial_answer": long_answer,
            "current_answer": long_answer,
            "length_rewrites": 2,
            "length_best_answer": long_answer,
            "iteration": 0,
        }
        mgr = TaskManager()
        with (
            patch("backend.core.nodes.call_llm", fake),
            patch("backend.core.evaluation.call_llm", fake),
            patch("backend.core.nodes._memory_store", store),
        ):
            await mgr._run_reflection_loop(record, state, MagicMock())

        assert record.length_refused is True
        assert record.length_compliance["status"] == "failed"
        finish_payload = mgr._length_gate_finish_payload(record)
        assert finish_payload["length_refused"] is True
        assert finish_payload["length_compliance"]["status"] == "failed"
        assert state.get("final_answer") == ""

    def test_get_task_dict_includes_length_fields(self):
        record = TaskRecord("task-api", "q", "simple", "quick_task")
        record.length_compliance = {
            "status": "failed",
            "actual_chars": 1000,
            "target_chars": 800,
            "rewrites": 2,
        }
        record.length_warning = True
        snap = record.to_dict(events_limit=0)
        assert snap["length_compliance"]["status"] == "failed"
        assert snap["length_warning"] is True
