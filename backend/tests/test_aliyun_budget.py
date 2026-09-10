"""阿里雲 BSS 接入與 Agent 預算（API＋雲資源）測試。"""

from __future__ import annotations

from backend.company.budget import BudgetManager
from backend.company.state import BudgetConfig, BudgetTier
from backend.services.aliyun_bss import AliyunBssClient, reset_aliyun_bss
from backend.services.cloud_console import CloudBilling


class _FakeDocker:
    available = True

    def list_containers(self):
        return [
            {
                "name": "evoloop-backend",
                "service": "backend",
                "status": "Up 2 hours",
                "uptime_seconds": 7200,
            }
        ]


def test_aliyun_unconfigured_returns_empty(monkeypatch):
    monkeypatch.delenv("ALIYUN_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("ALIYUN_ACCESS_KEY_SECRET", raising=False)
    reset_aliyun_bss()
    client = AliyunBssClient()
    data = client.get_billing_overview(force=True)
    assert data["configured"] is False
    assert data["month_total_usd"] == 0.0
    assert data["error"]


def test_aliyun_overview_parses_rpc(monkeypatch):
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_ID", "test-key")
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setenv("ALIYUN_CNY_USD_RATE", "0.1")
    reset_aliyun_bss()

    def fake_rpc(action, business):
        assert action == "QueryBillOverview"
        return {
            "Data": {
                "Items": {
                    "Item": [
                        {
                            "ProductCode": "ecs",
                            "ProductName": "雲伺服器 ECS",
                            "PretaxAmount": 100.0,
                        },
                        {
                            "ProductCode": "oss",
                            "ProductName": "物件儲存",
                            "PretaxAmount": 50.0,
                        },
                    ]
                }
            }
        }

    monkeypatch.setattr("backend.services.aliyun_bss._rpc_get", fake_rpc)
    data = AliyunBssClient().get_billing_overview(force=True)
    assert data["configured"] is True
    assert data["ok"] is True
    assert data["month_total_cny"] == 150.0
    assert data["month_total_usd"] == 15.0  # 150 * 0.1
    assert len(data["products"]) == 2


def test_cloud_billing_merges_docker_and_aliyun(monkeypatch):
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("ALIYUN_ACCESS_KEY_SECRET", "s")
    monkeypatch.setenv("ALIYUN_CNY_USD_RATE", "0.1")
    reset_aliyun_bss()

    monkeypatch.setattr(
        "backend.services.aliyun_bss._rpc_get",
        lambda action, business: {
            "Data": {
                "Items": {
                    "Item": [{"ProductCode": "ecs", "ProductName": "ECS", "PretaxAmount": 70.0}]
                }
            }
        },
    )
    billing = CloudBilling(docker=_FakeDocker())  # type: ignore[arg-type]
    summary = billing.get_billing_summary()
    assert summary["breakdown"]["aliyun_usd"] == 7.0
    assert summary["breakdown"]["docker_usd"] > 0
    assert summary["total_now"] == summary["breakdown"]["cloud_total_usd"]
    assert any(s.get("source") == "aliyun" for s in summary["per_service"])
    assert any(s.get("source") == "docker" for s in summary["per_service"])


def test_budget_manager_tracks_api_and_cloud_separately():
    bm = BudgetManager(BudgetConfig(monthly_limit_usd=100.0, task_limit_usd=0, session_limit_usd=0))
    bm.record_cost(10.0)
    bm.record_aliyun_cost(5.0)
    assert bm.api_cost == 10.0
    assert bm.aliyun_cost == 5.0
    assert bm.cloud_cost == 5.0
    assert bm.total_spent == 15.0
    assert bm.monthly_spent == 15.0
    assert bm.task_api_spent == 10.0
    d = bm.to_dict()
    assert d["api_cost"] == 10.0
    assert d["aliyun_cost"] == 5.0
    assert d["cloud_cost"] == 5.0
    assert d["task_api_spent"] == 10.0


def test_task_api_spent_ignores_monthly_aliyun_level():
    """阿里雲採設值語意；task_api 只扣本任務增量，不扣整月帳面。"""
    bm = BudgetManager(BudgetConfig(monthly_limit_usd=100.0, task_limit_usd=0, session_limit_usd=0))
    bm.record_aliyun_cost(20.0)  # 先同步月帳
    bm.reset_task()
    bm.record_cost(3.0)
    bm.record_aliyun_cost(22.0)  # 本任務僅 Δ2
    assert bm.aliyun_cost == 22.0
    assert bm.task_api_spent == 3.0
    assert abs(bm.task_spent - (3.0 + 2.0)) < 1e-6


def test_budget_manager_docker_not_double_counted_in_monthly():
    """Docker 只計入 cloud，不應再疊加到 api monthly。"""
    bm = BudgetManager(BudgetConfig(monthly_limit_usd=100.0))
    bm.record_cost(2.0)
    # 直接設置 docker（略過 docker_tools 依賴）
    bm._docker_cost = 3.0
    assert bm.api_cost == 2.0
    assert bm.monthly_spent == 5.0
    assert bm.total_spent == 5.0


def test_can_afford_uses_combined_monthly(monkeypatch):
    config = BudgetConfig(monthly_limit_usd=10.0, hard_stop=True, task_limit_usd=0, session_limit_usd=0)
    bm = BudgetManager(config)
    bm.record_cost(6.0)
    bm.record_aliyun_cost(3.5)
    can, reason = bm.can_afford(1.0, BudgetTier.ROUTINE)
    assert can is False
    assert "月度預算" in reason


def test_agent_monitor_allocates_cloud_into_budget(monkeypatch):
    from backend.services import agent_monitor as am

    monkeypatch.setattr(
        am,
        "list_role_snapshots",
        lambda: [
            {
                "id": "developer",
                "name": "開發工程師",
                "level": 3,
                "level_label": "執行層",
                "category": "backend",
                "daily_budget_usd": 1.0,
                "cloud_daily_budget_usd": 2.0,
                "alert_on_budget": True,
                "enabled": True,
            },
            {
                "id": "manager",
                "name": "專案經理",
                "level": 0,
                "level_label": "決策層",
                "category": "management",
                "daily_budget_usd": 0,
                "cloud_daily_budget_usd": 0,
                "enabled": True,
            },
        ],
    )
    monkeypatch.setattr(am.task_manager, "tasks", {})
    monkeypatch.setattr(am, "_ingest_run_logs", lambda agents: None)
    monkeypatch.setattr(
        am,
        "catalog_meta",
        lambda: {"categories": [], "org_templates": [], "presets": []},
    )
    monkeypatch.setattr(am, "get_monitor_prefs", dict)

    class _Billing:
        def get_billing_summary(self):
            return {
                "breakdown": {
                    "docker_usd": 4.0,
                    "aliyun_usd": 6.0,
                    "cloud_total_usd": 10.0,
                }
            }

    monkeypatch.setattr(
        "backend.services.cloud_console.get_cloud_billing",
        lambda: _Billing(),
    )

    # 模擬 API 花費
    real_finalize = am._finalize_agent

    def finalize(agent):
        if agent["id"] == "developer":
            agent["cost_usd"] = 0.5
            agent["status"] = "busy"
        return real_finalize(agent)

    monkeypatch.setattr(am, "_finalize_agent", finalize)

    data = am.collect_agent_monitor()
    by_id = {a["id"]: a for a in data["agents"]}
    assert data["summary"]["total_cloud_cost_usd"] == 10.0
    # developer 有 API 花費，應拿到全部雲資源分攤
    assert by_id["developer"]["api_cost_usd"] == 0.5
    assert by_id["developer"]["cloud_cost_usd"] == 10.0
    assert by_id["developer"]["cost_usd"] == 10.5
    assert by_id["developer"]["ai_budget_over"] is False
    assert by_id["developer"]["cloud_budget_over"] is True
    assert by_id["developer"]["budget_over"] is True
    messages = [x["message"] for x in by_id["developer"]["alerts"]]
    assert any("雲服務" in m for m in messages)
    assert not any("AI 使用已超過日預算" in m for m in messages)


def test_apply_split_budgets_independent():
    from backend.services.agent_monitor import _apply_split_budgets

    agent = {
        "api_cost_usd": 2.0,
        "cloud_cost_usd": 0.4,
        "daily_budget_usd": 1.0,
        "cloud_daily_budget_usd": 5.0,
        "weekly_budget_usd": 0,
        "monthly_budget_usd": 0,
        "cloud_weekly_budget_usd": 0,
        "cloud_monthly_budget_usd": 0,
        "alert_on_budget": True,
        "alerts": [{"level": "info", "message": "目前值班中"}],
    }
    _apply_split_budgets(agent)
    assert agent["ai_budget_over"] is True
    assert agent["cloud_budget_over"] is False
    assert agent["budget_over"] is True
    assert agent["ai_budget_remaining_usd"] == 0.0
    assert agent["cloud_budget_remaining_usd"] == 4.6
    messages = [x["message"] for x in agent["alerts"]]
    assert "目前值班中" in messages
    assert any("AI 使用已超過日預算" in m for m in messages)
    assert not any("雲服務" in m for m in messages)
