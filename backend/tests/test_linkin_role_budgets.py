"""靈境子角色預算：預設、回填、監控告警與設定往返。"""

from __future__ import annotations

from backend.linkin.budget_defaults import (
    DIRECTOR_BUDGETS,
    EXECUTOR_BUDGETS,
    REVIEWER_BUDGETS,
    SCRIBE_BUDGETS,
    budgets_for_role,
    role_budgets_uncustomized,
)
from backend.services.agent_monitor import (
    _apply_split_budgets,
    _count_budget_alerts,
    _limit_over,
    _limit_remaining,
)


def test_budget_defaults_by_staff_level():
    director = budgets_for_role("custom_linkin_build_director")
    executor = budgets_for_role("custom_linkin_build_executor")
    reviewer = budgets_for_role("custom_linkin_narrative_reviewer")
    scribe = budgets_for_role("custom_linkin_item_scribe")

    assert director == DIRECTOR_BUDGETS
    assert executor == EXECUTOR_BUDGETS
    assert reviewer == REVIEWER_BUDGETS
    assert scribe == SCRIBE_BUDGETS
    assert director["daily_budget_usd"] > executor["daily_budget_usd"]
    assert executor["daily_budget_usd"] > reviewer["daily_budget_usd"]
    assert reviewer["daily_budget_usd"] > scribe["daily_budget_usd"]


def test_limit_remaining_and_over_semantics():
    assert _limit_remaining(0, 5.0) is None
    assert _limit_remaining(10.0, 3.0) == 7.0
    assert _limit_remaining(10.0, 12.0) == 0.0
    assert _limit_over(0, 99.0) is False
    assert _limit_over(5.0, 5.0) is False
    assert _limit_over(5.0, 5.01) is True


def test_count_budget_alerts_includes_snapshot_alerts():
    agent = {
        "events": [{"event": "tool_call"}],
        "alerts": [{"level": "critical", "message": "今日 AI 使用已超過日預算"}],
    }
    assert _count_budget_alerts(agent) == 1

    agent["events"] = [{"event": "budget_warning"}]
    agent["alerts"] = []
    assert _count_budget_alerts(agent) == 1


def test_apply_split_budgets_sets_remaining_not_null_when_limited():
    agent = {
        "api_cost_usd": 2.0,
        "cloud_cost_usd": 0.5,
        "daily_budget_usd": 10.0,
        "cloud_daily_budget_usd": 3.0,
        "weekly_budget_usd": 0,
        "monthly_budget_usd": 0,
        "cloud_weekly_budget_usd": 0,
        "cloud_monthly_budget_usd": 0,
        "alert_on_budget": True,
        "alerts": [],
    }
    _apply_split_budgets(agent)
    assert agent["ai_budget_remaining_usd"] == 8.0
    assert agent["cloud_budget_remaining_usd"] == 2.5
    assert agent["ai_budget_over"] is False


def test_role_budgets_uncustomized_detects_overlay():
    record = {"daily_budget_usd": 0.0, "weekly_budget_usd": 0.0}
    assert role_budgets_uncustomized(record, None) is True
    assert role_budgets_uncustomized(record, {"daily_budget_usd": 0.0}) is False
    assert role_budgets_uncustomized({"daily_budget_usd": 2.0}, None) is False


def test_seed_linkin_roles_sets_default_budgets():
    from backend.company.role_catalog import get_snapshot
    from backend.linkin.roles import seed_linkin_roles

    seed_linkin_roles()
    director = get_snapshot("custom_linkin_build_director")
    executor = get_snapshot("custom_linkin_build_executor")
    reviewer = get_snapshot("custom_linkin_build_reviewer")
    scribe = get_snapshot("custom_linkin_build_scribe")

    assert director is not None
    assert director["daily_budget_usd"] == DIRECTOR_BUDGETS["daily_budget_usd"]
    assert executor["daily_budget_usd"] == EXECUTOR_BUDGETS["daily_budget_usd"]
    assert reviewer["daily_budget_usd"] == REVIEWER_BUDGETS["daily_budget_usd"]
    assert scribe["daily_budget_usd"] == SCRIBE_BUDGETS["daily_budget_usd"]
    assert director["cloud_daily_budget_usd"] > 0


def test_backfill_skips_customized_positive_budget():
    from backend.company.role_catalog import create_custom_role, get_snapshot
    from backend.linkin.roles import backfill_linkin_role_budgets, seed_linkin_roles

    create_custom_role(
        {
            "id": "linkin_build_executor",
            "name": "建築執行者",
            "level": 2,
            "tags": ["linkin", "build", "executor"],
            "daily_budget_usd": 99.0,
        }
    )
    backfill_linkin_role_budgets()
    snap = get_snapshot("custom_linkin_build_executor")
    assert snap is not None
    assert snap["daily_budget_usd"] == 99.0

    seed_linkin_roles()
    snap2 = get_snapshot("custom_linkin_build_executor")
    assert snap2 is not None
    assert snap2["daily_budget_usd"] == 99.0


def test_settings_patch_budget_round_trip(monkeypatch):
    from fastapi.testclient import TestClient

    from backend.linkin.roles import seed_linkin_roles
    from backend.main import app

    monkeypatch.setattr("backend.services.task_manager.task_manager.tasks", {})
    seed_linkin_roles()

    with TestClient(app) as client:
        put = client.put(
            "/monitor/agents/custom_linkin_build_executor/settings",
            json={
                "daily_budget_usd": 7.5,
                "cloud_daily_budget_usd": 4.0,
                "alert_on_budget": True,
            },
        )
        assert put.status_code == 200
        body = put.json()
        assert body["daily_budget_usd"] == 7.5
        assert body["cloud_daily_budget_usd"] == 4.0

        get = client.get("/monitor/agents")
        assert get.status_code == 200
        agents = {a["id"]: a for a in get.json()["agents"]}
        role = agents["custom_linkin_build_executor"]
        assert role["daily_budget_usd"] == 7.5
        assert role["cloud_daily_budget_usd"] == 4.0
        assert "account_budget" in get.json()


def test_budget_alert_when_over_daily(monkeypatch):
    from backend.linkin.roles import seed_linkin_roles
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setattr("backend.services.task_manager.task_manager.tasks", {})
    seed_linkin_roles()

    from backend.company.role_catalog import update_role_settings

    update_role_settings(
        "custom_linkin_build_executor",
        {"daily_budget_usd": 1.0, "alert_on_budget": True},
    )

    real_finalize = __import__(
        "backend.services.agent_monitor", fromlist=["_finalize_agent"]
    )._finalize_agent

    def finalize(agent):
        if agent["id"] == "custom_linkin_build_executor":
            agent["cost_usd"] = 1.5
        return real_finalize(agent)

    monkeypatch.setattr(
        "backend.services.agent_monitor._finalize_agent",
        finalize,
    )
    monkeypatch.setattr(
        "backend.services.agent_monitor._allocate_cloud_costs",
        lambda agents: {
            "docker_usd": 0.0,
            "aliyun_usd": 0.0,
            "cloud_total_usd": 0.0,
            "api_total_usd": 1.5,
        },
    )

    data = collect_agent_monitor()
    role = next(a for a in data["agents"] if a["id"] == "custom_linkin_build_executor")
    assert role["ai_budget_over"] is True
    assert role["ai_budget_remaining_usd"] == 0.0
    assert role["metrics"]["budget_alerts"] >= 1
    assert any("AI 使用已超過日預算" in a["message"] for a in role["alerts"])
