"""動態閾值與用戶反饋單元測試。"""


from backend.core.dynamic_threshold import resolve_pass_threshold, threshold_config
from backend.core.user_feedback import feedback_stats, record_feedback, satisfaction_bias


class TestDynamicThreshold:
    def test_simple_query_lowers_threshold(self):
        simple = resolve_pass_threshold("什麼是 Python？")
        complex_q = resolve_pass_threshold("請設計並實現一個完整的微服務系統架構")
        assert simple < complex_q

    def test_threshold_config(self):
        cfg = threshold_config()
        assert "base" in cfg
        assert "min" in cfg
        assert cfg["min"] <= cfg["base"] <= cfg["max"]


class TestUserFeedback:
    def test_record_and_stats(self, tmp_path, monkeypatch):
        fb_path = tmp_path / "user_feedback.json"
        monkeypatch.setenv("EVOL_USER_FEEDBACK_PATH", str(fb_path))
        record_feedback(
            session_id="sess-1",
            signal="thumbs_up",
            score=9.0,
            query_length=50,
        )
        record_feedback(
            session_id="sess-2",
            signal="thumbs_down",
            score=4.0,
            query_length=100,
        )
        stats = feedback_stats()
        assert stats["total"] >= 2
        assert stats["stats"]["thumbs_up"] >= 1
        assert stats["stats"]["thumbs_down"] >= 1

    def test_satisfaction_bias_insufficient_data(self, tmp_path, monkeypatch):
        fb_path = tmp_path / "user_feedback.json"
        monkeypatch.setenv("EVOL_USER_FEEDBACK_PATH", str(fb_path))
        assert satisfaction_bias() == 0.0
