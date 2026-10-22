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

    def test_industrial_chain_assembles_answer(self, monkeypatch):
        import asyncio

        from backend.core.industrial_chain import run_industrial_chain

        async def sense(_state):
            return {"opc_status": "ok", "opc_readings": {"motor": 1}}

        async def preprocess(_state):
            return {"opc_quality_report": {"total": 1, "good": 1, "bad": 0}, "opc_readings_clean": {}}

        async def analyze(_state):
            return {"opc_analysis": {"summary": "穩定"}}

        async def diagnose(_state):
            return {"opc_diagnosis": {"anomaly_detected": False, "severity": "normal", "root_cause": "無", "analysis": "正常"}}

        async def decide(_state):
            return {"opc_decisions": [], "opc_decision_summary": ""}

        async def act(_state):
            return {"opc_actions": []}

        monkeypatch.setattr("backend.core.industrial_chain.sense_opc", sense)
        monkeypatch.setattr("backend.core.industrial_chain.preprocess_opc", preprocess)
        monkeypatch.setattr("backend.core.industrial_chain.analyze_opc", analyze)
        monkeypatch.setattr("backend.core.industrial_chain.diagnose_opc", diagnose)
        monkeypatch.setattr("backend.core.industrial_chain.decide_opc", decide)
        monkeypatch.setattr("backend.core.industrial_chain.act_opc", act)

        state = asyncio.run(run_industrial_chain({"query": self.OPC_Q}))
        assert "指揮鏈" in state["current_answer"]
        assert state.get("cancelled") is not True

    def test_auto_industrial_is_company_chain(self):
        from backend.core.routing_preview import build_routing_preview

        self._assert_all_agree(self.OPC_Q, "auto", "run_company", "company")
        preview = build_routing_preview(self.OPC_Q, mode="auto")
        assert preview["template"] == "industrial_ops"
        assert "opc_keyword" in preview["reason_codes"]
        explicit = build_routing_preview(
            self.OPC_Q, mode="auto", company_template="full_company"
        )
        assert explicit["path"] == "company"
        assert explicit["template"] == "full_company"


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
