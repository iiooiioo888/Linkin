"""成本感知路由（cost_speed）單元測試。"""

from __future__ import annotations

import json

import pytest

from backend.core.company_nodes import route_by_complexity
from backend.core.cost_speed_router import (
    classify_task_complexity,
    cost_speed_enabled,
    max_output_chars_for_complexity,
    reload_cost_speed,
    resolve_cost_speed_model,
    resolve_path_for_complexity,
)
from backend.core.llm_config import reset_runtime_config, save_runtime_config
from backend.core.stage_router import reset_stage_budget, resolve_stage_model


@pytest.fixture(autouse=True)
def _enable_cost_speed(monkeypatch):
    monkeypatch.delenv("EVOL_COST_SPEED_ENABLED", raising=False)


class TestCostSpeedClassification:
    def test_simple_query(self):
        assert classify_task_complexity("什麼是 Python？") == "simple"

    def test_complex_query_by_keyword(self):
        assert classify_task_complexity("請設計並實現一個完整的微服務系統架構") == "complex"

    def test_medium_query(self):
        # 長度介於 simple 與 complex 門檻之間，且不含複雜關鍵詞
        query = "請說明" + "Python 列表推導式" * 8 + "的常見寫法與注意事項"
        assert 81 <= len(query) < 200
        assert classify_task_complexity(query) == "medium"


class TestCostSpeedRouting:
    def test_complex_path_goes_company(self):
        assert resolve_path_for_complexity("complex") == "company"
        assert resolve_path_for_complexity("simple") == "simple"

    def test_resolve_model_prefers_config(self, monkeypatch):
        monkeypatch.setattr(
            "backend.core.llm_config.get_explicit_model",
            lambda: None,
        )
        monkeypatch.setattr(
            "backend.core.cost_speed_router.clamp_model",
            lambda m, **kwargs: m,
        )
        reset_stage_budget()
        model = resolve_stage_model(
            "evaluate",
            query="什麼是 Python？",
            complexity="simple",
        )
        assert model == "qwen-turbo"

    def test_clamp_to_allowed_pool(self, monkeypatch):
        save_runtime_config(
            api_key="sk-test",
            api_base="https://api.deepseek.com",
            model="deepseek-v4-flash",
        )
        monkeypatch.setattr(
            "backend.core.provider_pool._http_get_json",
            lambda url, key, timeout=15.0: (_ for _ in ()).throw(RuntimeError("offline")),
        )
        from backend.core.provider_pool import refresh_model_catalog

        refresh_model_catalog(reason="test")
        picked = resolve_cost_speed_model("simple", "generate", "deepseek-v4-flash")
        assert picked in {"deepseek-v4-flash", "deepseek-v4-pro", "deepseek-v4-flash-vision-exp"}
        reset_runtime_config()


class TestRouteByComplexityIntegration:
    def test_auto_complex_uses_company(self):
        state = {
            "execution_strategy": "auto",
            "query": "請設計並實現一個完整的微服務系統架構",
        }
        assert route_by_complexity(state) == "run_company"

    def test_auto_simple_uses_generate(self):
        state = {
            "execution_strategy": "auto",
            "query": "什麼是 Python？",
            "task_complexity": "simple",
        }
        assert route_by_complexity(state) == "generate_initial_answer"


class TestCostSpeedHotReload:
    def test_reload_picks_up_config(self, tmp_path, monkeypatch):
        cfg = tmp_path / "cost_speed.json"
        cfg.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "complexity": {
                        "simple": {"max_query_length": 50, "path": "simple"},
                        "complex": {"min_query_length": 100, "path": "company", "keywords": []},
                    },
                    "stage_models": {
                        "simple": {"generate": "qwen-turbo"},
                    },
                    "models": {},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(cfg))
        status = reload_cost_speed()
        assert status["enabled"] is True
        assert cost_speed_enabled()


class TestMaxOutputCharsByComplexity:
    def test_defaults_follow_complexity(self):
        assert max_output_chars_for_complexity("simple") == 800
        assert max_output_chars_for_complexity("medium") == 2000
        assert max_output_chars_for_complexity("complex") == 4000

    def test_config_file_overrides_with_fallback(self, tmp_path, monkeypatch):
        cfg = tmp_path / "cost_speed.json"
        cfg.write_text(
            json.dumps(
                {
                    "enabled": True,
                    "complexity": {
                        "simple": {"max_output_chars": 123},
                        "medium": {"max_query_length": 200, "path": "simple"},
                    },
                    "stage_models": {},
                    "models": {},
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(cfg))
        reload_cost_speed()
        try:
            assert max_output_chars_for_complexity("simple") == 123
            # 未寫 max_output_chars 的等級退回內建兜底值
            assert max_output_chars_for_complexity("medium") == 2000
            assert max_output_chars_for_complexity("complex") == 4000
        finally:
            monkeypatch.delenv("EVOL_COST_SPEED_PATH", raising=False)
            reload_cost_speed()
