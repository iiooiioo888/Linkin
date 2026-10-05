"""規則回退必須可單獨測試，且回退分不能觸發提升不足的提前終止。"""

from __future__ import annotations

from backend.core.evaluation import EvaluationResult
from backend.core.fallback_rules import RuleBasedFallback
from backend.core.graph import should_improve


def test_short_answer_lowers_accuracy() -> None:
    result = RuleBasedFallback.evaluate("什麼是 Python", "太短")
    assert result.source == "rule_fallback"
    assert result.accuracy.score < 6
    assert "回答過短" in result.accuracy.reason


def test_definition_question_rewards_relevance() -> None:
    result = RuleBasedFallback.evaluate(
        "什麼是 Python",
        "Python 是一種直譯式程式語言，指通用腳本與應用開發。",
    )
    assert "問題類型匹配（定義）" in result.relevance.reason
    assert 0 <= result.overall <= 10


def test_fallback_dict_marks_source() -> None:
    result = RuleBasedFallback.evaluate("Python 裝飾器是什麼", "裝飾器是包住函式的函式。")
    result.fallback_reason = "timeout"
    data = result.to_dict()
    assert data["fallback_used"] is True
    assert data["score_source"] == "fallback"
    assert data["fallback_reason"] == "timeout"


def test_llm_dict_is_not_fallback() -> None:
    data = EvaluationResult(source="llm", overall=8).to_dict()
    assert data["fallback_used"] is False
    assert data["score_source"] == "llm"
    assert data["fallback_reason"] == ""


def test_fallback_low_improvement_does_not_finalize() -> None:
    state = {
        "score": 7.4,
        "iteration": 1,
        "query": "測試",
        "reflections": [{"score": 7.2}],
        "multi_dim_evaluation": {
            "fallback_used": True,
            "score_source": "fallback",
            "fallback_reason": "timeout",
        },
    }
    assert should_improve(state) == "reflect"


def test_fallback_above_pass_threshold_still_finalizes() -> None:
    """回退分一旦跨過通過門檻仍會終止。呼叫方要看 score_source。"""
    state = {
        "score": 9.0,
        "iteration": 1,
        "query": "測試",
        "reflections": [{"score": 7.0}],
        "multi_dim_evaluation": {
            "fallback_used": True,
            "score_source": "fallback",
            "fallback_reason": "timeout",
        },
    }
    assert should_improve(state) == "finalize"
