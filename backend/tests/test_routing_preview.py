"""POST /routing/preview 契約與效能測試。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.core.execution_path import resolve_execution_path
from backend.core.reflection_limits import reflection_max_iterations, resolve_task_complexity
from backend.core.routing_preview import build_routing_preview
from backend.main import app
from backend.services.task_manager import TaskManager, TaskRecord


@pytest.fixture(autouse=True)
def _cost_speed_default(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class TestRoutingPreviewContract:
    MATRIX = [
        ("在坐标(100, 64, 200)处放置一个钻石块", "auto"),
        ("在灵境精灵森林建造一座树桥聚落", "auto"),
        ("解釋一下 CI pipeline 怎麼設定", "auto"),
        ("今天天氣如何", "auto"),
        ("產線馬達溫度感測異常請診斷", "auto"),
        ("請設計並實現一個完整的微服務系統架構", "auto"),
    ]

    def test_preview_path_matches_resolve_execution_path(self):
        for query, mode in self.MATRIX:
            complexity = resolve_task_complexity(query, mode)
            expected = resolve_execution_path(query, mode, task_complexity=complexity)
            preview = build_routing_preview(query, mode=mode)
            assert preview["path"] == expected

    def test_preview_never_calls_llm(self, monkeypatch):
        def _boom(*_a, **_k):
            raise AssertionError("preview must not call LLM")

        monkeypatch.setattr("backend.core.llm.call_llm", _boom)
        monkeypatch.setattr("backend.core.llm.call_llm_stream", _boom)
        with patch("backend.core.nodes.call_llm", side_effect=_boom):
            build_routing_preview("今天天氣如何", mode="auto")

    def test_preview_latency_under_50ms(self):
        query = "在灵境精灵森林建造一座树桥聚落"
        start = time.perf_counter()
        for _ in range(20):
            build_routing_preview(query, mode="auto")
        elapsed_ms = (time.perf_counter() - start) / 20 * 1000
        assert elapsed_ms < 50, f"avg preview {elapsed_ms:.1f}ms"

    def test_http_preview_endpoint(self):
        with TestClient(app) as client:
            resp = client.post(
                "/routing/preview",
                json={"query": "今天天氣如何", "mode": "auto"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["path"] == "simple"
        assert "estimated_cost" in body
        assert "credits" not in str(body).lower()

    def test_should_grill_only_for_company_path(self):
        from backend.company.raho.grill_user import should_grill_user

        assert should_grill_user("今天天氣如何", "auto") is False
        assert should_grill_user("在坐标(100, 64, 200)处放置一个钻石块", "auto") is False
        assert should_grill_user("開發一個完整登入系統", "auto") is True


class TestCompanyPreviewReflectionCap:
    def test_preview_company_cap_differs_from_runtime_reflection_state(self):
        query = "請設計並實現一個完整的微服務系統架構"
        preview = build_routing_preview(query, mode="auto")
        assert preview["path"] == "company"
        runtime_state = {
            "query": query,
            "execution_strategy": "auto",
            "task_complexity": preview["complexity"],
            "resolved_execution_path": "company",
            "score": 7.0,
            "iteration": 1,
        }
        assert preview["max_reflection_rounds"] == reflection_max_iterations(
            runtime_state,
            routing_preview=True,
        )
        assert reflection_max_iterations(runtime_state) > preview["max_reflection_rounds"]


class TestTaskPathResolvedSingleSource:
    @pytest.mark.asyncio
    async def test_path_resolved_event_matches_record_resolved_path(self, monkeypatch):
        cases = [
            ("今天天氣如何", "auto", "simple"),
            ("在坐标(100, 64, 200)处放置一个钻石块", "auto", "minecraft_ops"),
            ("請設計並實現一個完整的微服務系統架構", "auto", "company"),
        ]
        mgr = TaskManager()

        async def _noop(*_args, **_kwargs):
            return None

        monkeypatch.setattr(mgr, "_run_simple_task", _noop)
        monkeypatch.setattr(mgr, "_run_company_task", _noop)
        monkeypatch.setattr(mgr, "_run_minecraft_ops_task", _noop)
        monkeypatch.setattr(mgr, "_run_opc_task", _noop)

        for query, strategy, expected in cases:
            record = TaskRecord(f"path-{expected}", query, strategy, "quick_task")
            await mgr._run_unified_task(record)
            evt = next(e for e in record.events if e.get("event") == "path_resolved")
            assert evt["data"]["path"] == expected
            assert record.resolved_path == expected
            assert evt["data"]["path"] == record.resolved_path


class TestTaskChatReflectionAlignment:
    def test_same_query_same_complexity_and_cap(self):
        query = "請解釋 Python 裝飾器的工作原理並舉例"
        mode = "auto"
        complexity = resolve_task_complexity(query, mode)
        preview = build_routing_preview(query, mode=mode)
        record = TaskRecord("align", query, mode, "quick_task")
        record.task_complexity = complexity
        record.resolved_path = preview["path"]
        state = {
            "query": query,
            "execution_strategy": mode,
            "task_complexity": complexity,
            "resolved_execution_path": record.resolved_path,
        }
        assert preview["complexity"] == complexity
        assert preview["max_reflection_rounds"] == reflection_max_iterations(state)
        assert TaskManager()._reflection_max_iterations(record, state) == preview["max_reflection_rounds"]
