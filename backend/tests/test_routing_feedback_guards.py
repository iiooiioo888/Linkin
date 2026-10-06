"""routing_feedback 成本護欄與監控欄位測試。"""

import json

import pytest

from backend.core.routing_feedback import (
    adaptive_length_threshold,
    feedback_today,
    feedback_upgrade_state,
    record_outcome,
    routing_stats,
)
from backend.services.optimization_monitor import collect_optimization_monitor


@pytest.fixture
def feedback_env(tmp_path, monkeypatch):
    fb_path = tmp_path / "routing_feedback.json"
    cfg_path = tmp_path / "cost_speed.json"
    monkeypatch.setenv("EVOL_ROUTING_FEEDBACK_PATH", str(fb_path))
    monkeypatch.setenv("EVOL_COST_SPEED_PATH", str(cfg_path))
    base_cfg = {
        "enabled": True,
        "post_company_reflect": "off",
        "routing_feedback": {
            "feedback_enabled": True,
            "max_company_ratio": 0.35,
            "consecutive_low_scores_for_company": 3,
            "low_score_threshold": 6.0,
            "simple_miss_window": 50,
            "simple_miss_count_for_escalate": 3,
            "length_threshold_step": 30,
        },
        "complexity": {},
        "stage_models": {},
        "models": {},
    }
    cfg_path.write_text(json.dumps(base_cfg), encoding="utf-8")
    from backend.core.cost_speed_router import reload_cost_speed

    reload_cost_speed()
    return fb_path, cfg_path


def _seed_low_simple(n: int) -> None:
    for _ in range(n):
        record_outcome("simple", 50, 4.0, False)


def test_feedback_today_taipei_next_day_at_utc_2330(monkeypatch):
    """UTC 23:30 在 Asia/Taipei 已是翌日（UTC 日期 +1）。"""
    from datetime import UTC, date, datetime
    from unittest.mock import patch

    from backend.core import routing_feedback as rf

    instant_utc = datetime(2025, 10, 5, 23, 30, tzinfo=UTC)
    expected = date(2025, 10, 6)

    def fake_now(tz=None):
        if tz is not None:
            return instant_utc.astimezone(tz)
        return instant_utc.replace(tzinfo=None)

    monkeypatch.delenv("EVOL_ROUTING_FEEDBACK_TIMEZONE", raising=False)
    with patch.object(rf, "datetime") as mock_dt:
        mock_dt.now = fake_now
        assert feedback_today() == expected


def test_feedback_disabled_does_not_raise_threshold(feedback_env, monkeypatch):
    _, cfg_path = feedback_env
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["routing_feedback"]["feedback_enabled"] = False
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    from backend.core.cost_speed_router import reload_cost_speed

    reload_cost_speed()
    _seed_low_simple(15)
    assert adaptive_length_threshold(200) == 200


def test_max_company_ratio_blocks_company_escalation(feedback_env):
    _, _ = feedback_env
    for _ in range(8):
        record_outcome("company", 300, 9.0, True)
    for _ in range(2):
        record_outcome("simple", 50, 4.0, False)
    state = feedback_upgrade_state()
    assert state["today_route_sample_count"] == 10
    assert state["company_ratio_samples_sufficient"] is True
    assert state["company_ratio_cap_hit"] is True
    assert state["company_escalation_allowed"] is False
    assert adaptive_length_threshold(200) == 200


def test_company_ratio_min_samples_defers_cap(feedback_env):
    _, _ = feedback_env
    record_outcome("company", 300, 9.0, True)
    state = feedback_upgrade_state()
    assert state["today_route_sample_count"] == 1
    assert state["today_company_ratio"] == 1.0
    assert state["company_ratio_samples_sufficient"] is False
    assert state["company_ratio_cap_hit"] is False


def test_consecutive_low_required_before_company_threshold(feedback_env):
    fb_path, _ = feedback_env

    base = 200
    today = feedback_today().isoformat()
    records = [
        {"route": "simple", "score": 4.0, "query_length": 50, "bucket": "short"}
        for _ in range(12)
    ]
    fb_path.write_text(
        json.dumps({
            "records": records,
            "stats": {"simple": 12, "company": 0},
            "meta": {
                "consecutive_simple_low": 2,
                "today_date": today,
                "today_simple": 12,
                "today_company": 0,
            },
        }),
        encoding="utf-8",
    )
    assert adaptive_length_threshold(base) == base

    store = json.loads(fb_path.read_text(encoding="utf-8"))
    store["meta"]["consecutive_simple_low"] = 3
    fb_path.write_text(json.dumps(store), encoding="utf-8")
    assert adaptive_length_threshold(base) > base


def test_monitor_exposes_feedback_fields(feedback_env):
    _seed_low_simple(2)
    data = collect_optimization_monitor()
    fb = data["routing_feedback"]
    assert "feedback" in fb
    assert "today_company_ratio" in fb["feedback"]
    assert "consecutive_simple_low" in fb["feedback"]
    assert "config" in fb


def test_routing_stats_includes_feedback(feedback_env):
    record_outcome("simple", 40, 5.0, False)
    stats = routing_stats()
    assert stats["feedback"]["tier_bump_active"] is True


def test_minecraft_ops_excluded_from_feedback(feedback_env):
    _, _ = feedback_env
    for _ in range(5):
        record_outcome(
            "simple",
            50,
            3.0,
            False,
            execution_path="minecraft_ops",
        )
    stats = routing_stats()
    assert stats["total"] == 0
    assert feedback_upgrade_state()["consecutive_simple_low"] == 0


def test_adaptive_threshold_does_not_steal_minecraft_ops_path(feedback_env, monkeypatch):
    from backend.core.execution_path import is_minecraft_ops_query, resolve_execution_path

    _, cfg_path = feedback_env
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["routing_feedback"]["max_company_ratio"] = 1.0
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    from backend.core.cost_speed_router import reload_cost_speed

    reload_cost_speed()
    _seed_low_simple(15)
    mc_q = "在坐标(100, 64, 200)处放置一个钻石块" + ("，請確認" * 40)
    assert is_minecraft_ops_query(mc_q)
    assert resolve_execution_path(mc_q, "auto") == "minecraft_ops"
