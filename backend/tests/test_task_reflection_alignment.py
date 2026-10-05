"""TaskManager 手抄反思迴圈與 LangGraph should_improve 行為對齊。"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolated_routing_feedback(monkeypatch, tmp_path):
    fb = tmp_path / "routing_feedback.json"
    fb.write_text(
        json.dumps({
            "records": [],
            "stats": {"simple": 0, "company": 0},
            "meta": {"consecutive_simple_low": 0},
        }),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb))

from backend.core.graph import reflection_should_continue, should_improve
from backend.services.task_manager import TaskManager, TaskRecord


def _routing_state(**overrides):
    base = {
        "query": "測試",
        "execution_strategy": "simple",
        "task_complexity": "simple",
        "iteration": 0,
        "reflections": [],
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    "state,expected_continue",
    [
        ({"score": 9.0, "iteration": 0, "query": "測試", "execution_strategy": "simple"}, False),
        (
            {
                "score": 7.5,
                "iteration": 2,
                "query": "測試",
                "execution_strategy": "simple",
                "reflections": [{"score": 7.2}],
            },
            False,
        ),
        (
            {
                "score": 6.0,
                "iteration": 1,
                "query": "測試",
                "execution_strategy": "auto",
                "task_complexity": "medium",
                "reflections": [{"score": 4.0}],
            },
            True,
        ),
        (
            {
                "score": 7.4,
                "iteration": 1,
                "query": "測試",
                "execution_strategy": "auto",
                "task_complexity": "medium",
                "reflections": [{"score": 7.2}],
                "multi_dim_evaluation": {
                    "fallback_used": True,
                    "score_source": "fallback",
                },
            },
            True,
        ),
        ({"score": 8.0, "iteration": 0, "query": "測試", "length_directive": "精簡"}, True),
    ],
)
def test_reflection_should_continue_matches_should_improve(state, expected_continue):
    want_reflect = should_improve(state) == "reflect"
    assert reflection_should_continue(state) == (want_reflect or bool(state.get("length_directive")))
    assert reflection_should_continue(state) == expected_continue


def test_missing_prev_reflection_score_skips_early_stop(monkeypatch):
    monkeypatch.setattr("backend.core.graph.MIN_SCORE_IMPROVEMENT", 0.5)
    monkeypatch.setattr(
        "backend.core.dynamic_threshold.resolve_pass_threshold",
        lambda _q: 8.0,
    )
    state = {
        "score": 7.5,
        "iteration": 2,
        "query": "測試",
        "execution_strategy": "auto",
        "task_complexity": "medium",
        "reflections": [{"critique": "no score field"}],
    }
    assert should_improve(state) == "reflect"


class FakeLLM:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.n = 0

    def __call__(self, prompt, system=None, model=None, **kwargs):
        out = self.responses[min(self.n, len(self.responses) - 1)]
        self.n += 1
        return out


def _evaluation(score: float) -> str:
    return json.dumps({"score": score, "strengths": "ok", "weaknesses": ""}, ensure_ascii=False)


def _reflection() -> str:
    return json.dumps(
        {"critique": "可改進", "suggestion": "補細節"},
        ensure_ascii=False,
    )


class TestTaskManagerReflectionLoop:
    @pytest.mark.asyncio
    async def test_early_stop_matches_graph(self, monkeypatch):
        monkeypatch.setattr("backend.core.graph.MIN_SCORE_IMPROVEMENT", 0.5)
        monkeypatch.setenv("EVOL_SIMPLE_MAX_ITERATIONS", "3")
        monkeypatch.setattr(
            "backend.core.dynamic_threshold.resolve_pass_threshold",
            lambda _q: 8.0,
        )
        fake = FakeLLM(
            [
                _evaluation(7.5),
                _reflection(),
                "改進後答案",
                _evaluation(7.52),
            ]
        )
        store = MagicMock()
        store.search_similar.return_value = []
        record = TaskRecord("align-early", "測試", "simple", "quick_task")
        record.resolved_path = "simple"
        state = _routing_state(
            session_id=record.task_id,
            initial_answer="初稿",
            current_answer="初稿",
        )
        mgr = TaskManager()
        with (
            patch("backend.core.nodes.call_llm", side_effect=fake),
            patch("backend.core.evaluation.call_llm", side_effect=fake),
            patch("backend.core.nodes._memory_store", store),
        ):
            await mgr._run_reflection_loop(record, state, MagicMock())

        assert state["iteration"] == 1
        assert not mgr._reflection_should_continue(record, state)

    @pytest.mark.asyncio
    async def test_pass_threshold_finalizes_without_extra_reflect(self):
        fake = FakeLLM([_evaluation(9.0)])
        store = MagicMock()
        store.search_similar.return_value = []
        record = TaskRecord("align-pass", "測試", "simple", "quick_task")
        record.resolved_path = "simple"
        state = _routing_state(
            session_id=record.task_id,
            initial_answer="夠好",
            current_answer="夠好",
        )
        mgr = TaskManager()
        with (
            patch("backend.core.nodes.call_llm", side_effect=fake),
            patch("backend.core.evaluation.call_llm", side_effect=fake),
            patch("backend.core.nodes._memory_store", store),
        ):
            await mgr._run_reflection_loop(record, state, MagicMock())

        assert state["iteration"] == 0
        assert fake.n == 1

    def test_task_manager_continue_delegates_to_graph_helper(self):
        record = TaskRecord("align-fallback", "測試", "auto", "quick_task")
        record.resolved_path = "company"
        state = _routing_state(
            score=7.45,
            iteration=1,
            reflections=[{"score": 7.4}],
            multi_dim_evaluation={
                "fallback_used": True,
                "score_source": "fallback",
            },
            task_complexity="medium",
        )
        mgr = TaskManager()
        routed = mgr._reflection_routing_state(record, state)
        assert mgr._reflection_should_continue(record, state) == reflection_should_continue(
            routed
        )
        assert should_improve(routed) == "reflect"

    def test_missing_score_raises_on_continue_check(self):
        record = TaskRecord("align-noscore", "測試", "simple", "quick_task")
        record.resolved_path = "simple"
        state = _routing_state(score=None, iteration=0)
        mgr = TaskManager()
        with pytest.raises(ValueError, match="score"):
            mgr._reflection_should_continue(record, state)
