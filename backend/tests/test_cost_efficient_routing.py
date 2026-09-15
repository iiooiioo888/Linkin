"""成本感知路由：簡單策略不走公司 SSE、公司後反思與 TaskManager 對齊。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.core.reflection_limits import reflection_max_iterations, simple_path_max_iterations
from backend.services.task_manager import TaskManager, TaskRecord, _post_company_reflect_mode


@pytest.fixture(autouse=True)
def _enable_cost_speed(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class TestReflectionLimits:
    def test_simple_max_iterations_default(self, monkeypatch):
        monkeypatch.delenv("EVOL_SIMPLE_MAX_ITERATIONS", raising=False)
        assert simple_path_max_iterations() == 1

    def test_simple_strategy_caps_graph_style_state(self):
        state = {
            "execution_strategy": "simple",
            "query": "請設計並實現一個完整的微服務系統架構",
        }
        assert reflection_max_iterations(state) == 1


class TestChatStreamSimpleStrategy:
    def test_long_query_with_simple_does_not_emit_company_events(self, monkeypatch):
        """對應 PR #67：UI 選「簡單」時不得因長文誤觸公司 SSE。"""
        from fastapi.testclient import TestClient

        from backend.main import app

        monkeypatch.delenv("EVOL_SIMPLE_MAX_ITERATIONS", raising=False)

        long_query = "請說明" + "微服務" * 80 + "的設計要點"
        assert len(long_query) >= 200

        def fake_stream(prompt, system=None, model=None, **kwargs):
            yield "簡短回答"

        def fake_eval(prompt, system=None, model=None, **kwargs):
            return json.dumps(
                {"score": 9.0, "strengths": "ok", "weaknesses": ""},
                ensure_ascii=False,
            )

        store = MagicMock()
        store.search_similar.return_value = []

        lines: list[str] = []
        with (
            patch("backend.main.call_llm_stream", side_effect=fake_stream),
            patch("backend.core.nodes.call_llm", side_effect=fake_eval),
            patch("backend.core.evaluation.call_llm", side_effect=fake_eval),
            patch("backend.core.nodes._memory_store", store),
            TestClient(app) as client,client.stream(
            "POST",
            "/chat/stream",
            json={"query": long_query, "execution_strategy": "simple"},
        ) as resp
        ):
            assert resp.status_code == 200
            for line in resp.iter_lines():
                if line:
                    lines.append(line)

        joined = "\n".join(lines)
        assert "event: company" not in joined
        assert "event: token" in joined or "event: done" in joined


class TestCompanyStreamPostReflect:
    def test_default_skips_reflect_phases(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.company.orchestrator import CompanyOrchestrator
        from backend.main import app

        monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
        monkeypatch.delenv("EVOL_SKIP_POST_COMPANY_REFLECT", raising=False)
        assert _post_company_reflect_mode() == "off"

        async def _fake_execute(self, query):
            return {"final_output": "公司產出", "success": True, "stats": {}}

        monkeypatch.setattr(CompanyOrchestrator, "execute", _fake_execute)

        phases: list[str] = []
        with TestClient(app) as client, client.stream(
            "POST",
            "/chat/stream",
            json={
                "query": "請設計並實現一個完整的微服務系統架構",
                "execution_strategy": "company",
            },
        ) as resp:
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                try:
                    payload = json.loads(line.split("data:", 1)[1].strip())
                except json.JSONDecodeError:
                    continue
                if "phase" in payload:
                    phases.append(str(payload["phase"]))

        assert "post_company_reflect_skipped" in phases
        assert "reflect" not in phases
        assert "improve" not in phases


class TestTaskManagerSimpleReflectCap:
    @pytest.mark.asyncio
    async def test_simple_task_respects_evol_simple_max_iterations(self, monkeypatch):
        monkeypatch.setenv("EVOL_SIMPLE_MAX_ITERATIONS", "0")
        mgr = TaskManager()
        record = TaskRecord("t_cap", "簡單問", "simple", "quick_task")
        record.resolved_path = "simple"
        state = {"query": "q", "iteration": 0, "score": 5.0}
        assert mgr._reflection_max_iterations(record, state) == 0
