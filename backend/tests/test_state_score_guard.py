"""score 缺失時終止判斷必須失敗，不能當成 0.0。"""

from __future__ import annotations

import pytest

from backend.core.graph import should_improve


def test_missing_score_raises() -> None:
    with pytest.raises(ValueError, match="score"):
        should_improve({"iteration": 1, "query": "測試", "reflections": []})


def test_score_none_raises() -> None:
    with pytest.raises(ValueError, match="score"):
        should_improve({"score": None, "iteration": 1, "query": "測試"})


def test_present_score_still_routes() -> None:
    assert should_improve({"score": 9.0, "iteration": 0, "query": "測試"}) == "finalize"
