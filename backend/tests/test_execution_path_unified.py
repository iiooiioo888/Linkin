"""統一執行路徑：各入口對同一查詢應一致。"""

from __future__ import annotations

import pytest

from backend.core.company_nodes import route_by_complexity
from backend.core.execution_path import (
    chat_stream_uses_company_sse,
    resolve_execution_path,
    route_by_complexity_target,
)
from backend.services.task_manager import TaskManager, TaskRecord


@pytest.fixture(autouse=True)
def _cost_speed_default(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class TestExecutionPathMatrix:
    SIMPLE_Q = "今天天氣如何"
    COMPLEX_Q = "請設計並實現一個完整的微服務系統架構"
    LINKIN_Q = "在灵境精灵森林建造一座树桥聚落"
    MC_Q = "在坐标(100, 64, 200)处放置一个钻石块"
    OPC_Q = "產線馬達溫度感測異常請診斷"

    def _assert_all_agree(self, query: str, strategy: str, expected_graph: str, expected_task: str):
        state = {"query": query, "execution_strategy": strategy}
        assert route_by_complexity(state) == expected_graph
        assert route_by_complexity_target(query, strategy) == expected_graph
        assert resolve_execution_path(query, strategy) == expected_task
        record = TaskRecord("t", query, strategy, "quick_task")
        assert TaskManager()._resolve_path(record) == expected_task
        uses_sse = chat_stream_uses_company_sse(query, strategy)
        assert uses_sse == (expected_task == "company")

    def test_simple_strategy_never_company(self):
        for q in (self.COMPLEX_Q, self.LINKIN_Q, self.MC_Q):
            self._assert_all_agree(q, "simple", "generate_initial_answer", "simple")

    def test_company_strategy_always_company(self):
        self._assert_all_agree(self.SIMPLE_Q, "company", "run_company", "company")

    def test_auto_linkin_complex_to_company(self):
        self._assert_all_agree(self.LINKIN_Q, "auto", "run_company", "company")

    def test_auto_minecraft_to_company(self):
        self._assert_all_agree(self.MC_Q, "auto", "run_company", "company")

    def test_auto_generic_simple(self):
        self._assert_all_agree(self.SIMPLE_Q, "auto", "generate_initial_answer", "simple")

    def test_auto_keyword_complex(self):
        self._assert_all_agree(self.COMPLEX_Q, "auto", "run_company", "company")

    def test_auto_opc_task_path(self):
        self._assert_all_agree(self.OPC_Q, "auto", "generate_initial_answer", "opc")
        assert chat_stream_uses_company_sse(self.OPC_Q, "auto") is False


class TestGraphPostCompanyReflectOff:
    def test_success_skips_evaluate_loop(self, monkeypatch):
        monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
        from backend.core.company_nodes import should_evaluate_company

        state = {
            "company_result": {"success": True},
            "post_company_reflect_mode": "off",
        }
        assert should_evaluate_company(state) == "company_finalize"
