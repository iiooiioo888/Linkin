"""統一執行路徑：各入口對同一查詢應一致。"""

from __future__ import annotations

import pytest

from backend.core.company_nodes import route_by_complexity
from backend.core.execution_path import (
    chat_stream_uses_company_sse,
    is_minecraft_heavy_task,
    is_minecraft_ops_query,
    resolve_execution_path,
    route_by_complexity_target,
)
from backend.core.reflection_limits import (
    reflection_max_iterations,
    resolve_task_complexity,
)
from backend.core.routing_preview import build_routing_preview
from backend.services.task_manager import TaskManager, TaskRecord


@pytest.fixture(autouse=True)
def _cost_speed_default(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class TestExecutionPathMatrix:
    SIMPLE_Q = "今天天氣如何"
    COMPLEX_Q = "請設計並實現一個完整的微服務系統架構"
    LINKIN_Q = "在灵境精灵森林建造一座树桥聚落"
    MC_Q = "在坐标(100, 64, 200)处放置一个钻石块"
    MC_HEAVY_Q = "在灵境精灵森林建造一座树桥聚落"
    MC_BUILD_Q = "使用 place_block 設計並建造完整主城結構"
    MC_NARRATIVE_Q = "minecraft story_studio 敘事管線 phase 2 待落地"
    GENERIC_PIPELINE_Q = "解釋一下 CI pipeline 怎麼設定"
    GENERIC_PIPELINE_ZH = "資料管線優化"
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

    def test_auto_minecraft_simple_to_ops(self):
        self._assert_all_agree(self.MC_Q, "auto", "run_minecraft_ops", "minecraft_ops")
        assert is_minecraft_ops_query(self.MC_Q) is True
        assert is_minecraft_heavy_task(self.MC_Q) is False

    def test_auto_minecraft_heavy_stays_company(self):
        self._assert_all_agree(self.MC_HEAVY_Q, "auto", "run_company", "company")
        self._assert_all_agree(self.MC_BUILD_Q, "auto", "run_company", "company")
        self._assert_all_agree(self.MC_NARRATIVE_Q, "auto", "run_company", "company")
        assert is_minecraft_heavy_task(self.MC_NARRATIVE_Q) is True

    def test_generic_pipeline_queries_stay_simple(self):
        self._assert_all_agree(self.GENERIC_PIPELINE_Q, "auto", "generate_initial_answer", "simple")
        self._assert_all_agree(self.GENERIC_PIPELINE_ZH, "auto", "generate_initial_answer", "simple")
        assert is_minecraft_heavy_task(self.GENERIC_PIPELINE_Q) is False
        assert is_minecraft_heavy_task(self.GENERIC_PIPELINE_ZH) is False

    def test_auto_generic_simple(self):
        self._assert_all_agree(self.SIMPLE_Q, "auto", "generate_initial_answer", "simple")

    def test_auto_keyword_complex(self):
        self._assert_all_agree(self.COMPLEX_Q, "auto", "run_company", "company")

    def test_auto_opc_task_path(self):
        self._assert_all_agree(self.OPC_Q, "auto", "generate_initial_answer", "opc")
        assert chat_stream_uses_company_sse(self.OPC_Q, "auto") is False


class TestMinecraftOpsReflectionCap:
    def test_minecraft_ops_skips_score_driven_reflection(self):
        state = {
            "resolved_execution_path": "minecraft_ops",
            "task_complexity": "simple",
            "execution_strategy": "auto",
        }
        assert reflection_max_iterations(state) == 0

    def test_should_improve_finalizes_without_length_directive(self, monkeypatch):
        monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
        from backend.core.graph import should_improve

        state = {
            "resolved_execution_path": "minecraft_ops",
            "score": 3.0,
            "iteration": 0,
            "query": "在坐标(100, 64, 200)处放置一个钻石块",
        }
        assert should_improve(state) == "finalize"


class TestPreviewMatchesExecution:
    QUERIES = TestExecutionPathMatrix.SIMPLE_Q, TestExecutionPathMatrix.MC_Q

    def test_preview_and_task_share_path_and_reflection_cap(self):
        query = "請解釋 Python 裝飾器的工作原理並舉例"
        mode = "auto"
        complexity = resolve_task_complexity(query, mode)
        path = resolve_execution_path(query, mode, task_complexity=complexity)
        preview = build_routing_preview(query, mode=mode)
        assert preview["path"] == path
        assert preview["complexity"] == complexity
        routing_state = {
            "query": query,
            "execution_strategy": mode,
            "task_complexity": complexity,
            "resolved_execution_path": path,
        }
        assert preview["max_reflection_rounds"] == reflection_max_iterations(routing_state)
        record = TaskRecord("t-prev", query, mode, "quick_task")
        record.task_complexity = complexity
        record.resolved_path = path
        mgr = TaskManager()
        assert mgr._reflection_max_iterations(record, routing_state) == preview["max_reflection_rounds"]


class TestGraphPostCompanyReflectOff:
    def test_success_skips_evaluate_loop(self, monkeypatch):
        monkeypatch.delenv("EVOL_POST_COMPANY_REFLECT", raising=False)
        from backend.core.company_nodes import should_evaluate_company

        state = {
            "company_result": {"success": True},
            "post_company_reflect_mode": "off",
        }
        assert should_evaluate_company(state) == "company_finalize"
