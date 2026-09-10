"""性能优化路线图相关单元测试。"""

import json

import pytest

from backend.company.state import BudgetTier
from backend.core.routing_feedback import (
    adaptive_length_threshold,
    record_outcome,
    routing_stats,
)
from backend.core.stage_router import reset_stage_budget, resolve_stage_model, stage_tier


class TestStageRouter:
    def test_default_tiers(self):
        assert stage_tier("generate") == BudgetTier.ROUTINE
        assert stage_tier("evaluate") == BudgetTier.SUMMARY
        assert stage_tier("reflect") == BudgetTier.REASONING
        assert stage_tier("improve") == BudgetTier.ROUTINE

    def test_resolve_stage_model(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_BASE", raising=False)

        def _fake_explicit():
            return None

        monkeypatch.setattr(
            "backend.core.llm_config.get_explicit_model", _fake_explicit
        )
        reset_stage_budget()
        eval_model = resolve_stage_model("evaluate")
        reflect_model = resolve_stage_model("reflect")
        assert eval_model
        assert reflect_model

    def test_env_override_tier(self, monkeypatch):
        monkeypatch.setenv("EVOL_STAGE_TIER_EVALUATE", "reasoning")
        assert stage_tier("evaluate") == BudgetTier.REASONING


class TestRoutingFeedback:
    def test_adaptive_threshold_increases_on_simple_miss(self, tmp_path, monkeypatch):
        fb_path = tmp_path / "routing_feedback.json"
        monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb_path))
        base = 200
        for _ in range(12):
            record_outcome("simple", 50, 4.0, False)
        threshold = adaptive_length_threshold(base)
        assert threshold > base

    def test_routing_stats(self, tmp_path, monkeypatch):
        fb_path = tmp_path / "routing_feedback.json"
        monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb_path))
        record_outcome("company", 300, 8.5, True)
        stats = routing_stats()
        assert stats["total"] >= 1
        assert stats["company_count"] >= 1


class TestMergeReviewSynth:
    @pytest.mark.asyncio
    async def test_review_and_synthesize(self, monkeypatch):
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.state import CompanyConfig

        orch = CompanyOrchestrator(CompanyConfig())

        async def _fake_synth(goal):
            return "fallback output"

        monkeypatch.setattr(orch, "_collect_artifacts", lambda: "artifact-1")
        monkeypatch.setattr(orch.work_items, "get_stats", lambda: {"total": 1, "done": 1})
        monkeypatch.setattr(orch, "_count_review_rounds", lambda: 0)

        def _fake_llm(prompt, system=None, model=None, **kwargs):
            return json.dumps({
                "quality_passed": True,
                "quality_score": 9,
                "quality_notes": "",
                "final_output": "merged final",
            })

        monkeypatch.setattr("backend.company.orchestrator.call_llm", _fake_llm)

        output, meta = await orch._review_and_synthesize("test goal")
        assert output == "merged final"
        assert meta.get("merged") is True


class TestReflectionEarlyStop:
    def test_should_improve_stops_on_low_improvement(self, monkeypatch):
        from backend.core.graph import should_improve

        monkeypatch.setattr("backend.core.graph.MIN_SCORE_IMPROVEMENT", 0.5)
        state = {
            "score": 7.5,
            "iteration": 2,
            "reflections": [{"score": 7.2}],
        }
        assert should_improve(state) == "finalize"

    def test_should_improve_continues_when_improving(self, monkeypatch):
        from backend.core.graph import should_improve

        monkeypatch.setattr("backend.core.graph.PASS_THRESHOLD", 8.0)
        monkeypatch.setattr("backend.core.graph.MAX_ITERATIONS", 5)
        state = {
            "score": 6.0,
            "iteration": 1,
            "reflections": [{"score": 4.0}],
        }
        assert should_improve(state) == "reflect"


class TestOpcEdgeCache:
    @pytest.mark.asyncio
    async def test_edge_cache_hit(self, tmp_path, monkeypatch):
        cache_file = tmp_path / "edge_cache.json"
        import time

        cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "updated_at": time.time(),
                "readings": {"tag1": {"value": 42, "quality": "Good"}},
            }, f)

        monkeypatch.setenv("EVOL_OPC_EDGE_CACHE", str(cache_file))
        monkeypatch.setenv("EVOL_OPC_TIER", "auto")
        monkeypatch.setenv("EVOL_OPC_EDGE_TTL", "30")

        from opc_service import sense

        # 重新加载模块级常量
        sense._EDGE_CACHE_PATH = cache_file
        sense.OPC_TIER = "auto"
        sense.OPC_EDGE_TTL = 30.0

        result = await sense.sense_opc({})
        assert result["opc_source"] == "edge"
        assert result["opc_readings"]["tag1"]["value"] == 42
