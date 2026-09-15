"""公司任務簡化：規劃重用、反思跳過、run_log 單寫。"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.company.precomputed_planner import normalize_precomputed, precomputed_usable
from backend.company.run_log import run_log_path
from backend.services.task_manager import TaskManager, TaskRecord, _post_company_reflect_mode


VALID_TICKET = {
    "status": "APPROVED_FOR_PLANNING",
    "confidence_score": 88,
    "clarified_goal": {"core_action": "交付登入模組"},
}


def _minimal_battle_plan() -> dict:
    return {
        "plan_id": "bp_test",
        "dag_nodes": [
            {
                "node_id": "n1",
                "title": "實作",
                "atomic_role": "js_dev",
                "depends_on": [],
            }
        ],
        "global_settings": {},
    }


def _precomputed_pack() -> dict:
    return {
        "status": "PLANNER_TRIGGERED",
        "ticket": VALID_TICKET,
        "campaign": {
            "goal": "交付登入模組",
            "nodes": [
                {
                    "node_id": "c1",
                    "title": "里程碑",
                    "outcome": "完成",
                    "success_criteria": "可登入",
                    "depends_on": [],
                }
            ],
            "source": "rule",
        },
        "commander": {
            "status": "PLAN_READY",
            "battle_plan": _minimal_battle_plan(),
            "battle_plan_yaml": "plan_id: bp_test",
        },
    }


class TestPrecomputedPlanner:
    def test_normalize_and_usable(self):
        raw = _precomputed_pack()
        norm = normalize_precomputed(raw)
        assert norm is not None
        assert precomputed_usable(norm)


class TestPlannerReuse:
    @pytest.mark.asyncio
    async def test_orchestrator_skips_plan_campaign_and_commander(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")

        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import BUILTIN_TEMPLATES

        calls = {"plan_campaign": 0, "command_from_ticket": 0}

        def fake_plan_campaign(goal: str):
            calls["plan_campaign"] += 1
            raise AssertionError("不應重算 L4")

        def fake_command_from_ticket(ticket, use_llm=True):
            calls["command_from_ticket"] += 1
            raise AssertionError("不應重算 L3")

        monkeypatch.setattr(
            "backend.company.raho.planner.plan_campaign",
            fake_plan_campaign,
        )
        monkeypatch.setattr(
            "backend.company.raho.commander.command_from_ticket",
            fake_command_from_ticket,
        )

        orch = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        monkeypatch.setattr(orch, "_execute_review_loop", AsyncMock(return_value=None))
        monkeypatch.setattr(
            orch,
            "_review_and_synthesize",
            AsyncMock(return_value=("完成", {})),
        )
        monkeypatch.setattr(
            orch,
            "_manager_final_review",
            AsyncMock(return_value={"approved": True, "score": 9}),
        )

        result = await orch.execute(
            "交付登入模組",
            ticket=VALID_TICKET,
            precomputed_planner=_precomputed_pack(),
        )
        assert result.get("success") is True
        assert calls == {"plan_campaign": 0, "command_from_ticket": 0}
        log_events = [row["event"] for row in orch._run_log]
        assert "planner_reused" in log_events


class TestPostCompanyReflection:
    def test_default_reflect_mode_off(self, monkeypatch):
        monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
        monkeypatch.delenv("EVOL_SKIP_POST_COMPANY_REFLECT", raising=False)
        assert _post_company_reflect_mode() == "off"

    @pytest.mark.asyncio
    async def test_company_task_skips_reflection_by_default(self, monkeypatch):
        monkeypatch.setenv("EVOL_SKIP_POST_COMPANY_REFLECT", "1")
        mgr = TaskManager()
        record = TaskRecord("t_skip_refl", "公司任務", "company", "quick_task")
        record.status = "running"
        record.resolved_path = "company"
        mgr.tasks[record.task_id] = record

        reflect_called = False

        async def fake_reflect(*_a, **_k):
            nonlocal reflect_called
            reflect_called = True

        monkeypatch.setattr(mgr, "_run_reflection_loop", fake_reflect)
        monkeypatch.setattr(mgr, "_add_event", lambda *a, **k: None)
        monkeypatch.setattr(mgr, "_set_phase", lambda *a, **k: None)

        tracer = MagicMock()
        state = {"query": "q", "current_answer": "產出", "iteration": 0, "score": 0.0}
        await mgr._run_post_company_reflection(record, state, tracer)
        assert reflect_called is False


class TestRunLogSingleWrite:
    def test_company_start_not_doubled_in_jsonl(self, monkeypatch, tmp_path):
        monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path))
        monkeypatch.setenv("EVOL_RAHO_ENABLED", "false")

        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.roles import BUILTIN_TEMPLATES

        orch = CompanyOrchestrator(BUILTIN_TEMPLATES["quick_task"])
        run_id = "abcd1234" * 2
        orch._run_id = run_id
        orch._log("company_start", {"goal": "測試", "config": "quick"}, level=20)
        from backend.company.events import CompanyEvent

        orch.events.emit(CompanyEvent.COMPANY_START, {"goal": "測試", "config": "quick"})

        path = run_log_path(run_id)
        assert path.exists()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        events = [json.loads(line)["event"] for line in lines]
        assert events.count("company_start") == 1
