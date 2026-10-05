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
