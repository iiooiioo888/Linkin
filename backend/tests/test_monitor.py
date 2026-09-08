"""監控中心聚合 API 測試：OPC 離線降級 + Hub 快照不含 Claude。"""

from __future__ import annotations

from datetime import datetime, timezone

from backend.hub.monitor import collect_hub_monitor
from backend.hub.runtime import reset_runtime, runtime
from backend.hub.store import AgentTask, new_task_id
from backend.services.opc_monitor import collect_opc_monitor
from backend.services.task_manager import TaskRecord, task_manager


def test_opc_monitor_degrades_when_service_down(tmp_path, monkeypatch):
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(tmp_path / "audit"))
    monkeypatch.setattr(task_manager, "tasks", {})
    monkeypatch.setattr(
        "backend.services.opc_monitor.fetch_opc_live",
        lambda base_url=None: {
            "reachable": False,
            "health": None,
            "browse_tags": [],
            "readings": [],
            "error": "connection refused",
        },
    )

    data = collect_opc_monitor()

    assert data["live"]["reachable"] is False
    assert data["live"]["error"] == "connection refused"
    assert data["live"]["simulated"] is True
    assert len(data["live"]["readings"]) == 8
    assert data["live"]["readings"][0]["tag_name"] == "Temperature"
    assert data["live"]["readings"][0]["value"] == 25.0
    assert "Temperature" in {t["name"] for t in data["catalog"]}
    assert "write_bounds" in data["guard"]
    assert "Temperature" in data["guard"]["write_bounds"]
    assert data["audit"]["recent"] == []
    assert data["recent_tasks"] == []


def test_opc_monitor_aligns_foreign_readings(tmp_path, monkeypatch):
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(tmp_path / "audit"))
    monkeypatch.setattr(task_manager, "tasks", {})
    monkeypatch.setattr(
        "backend.services.opc_monitor.fetch_opc_live",
        lambda base_url=None: {
            "reachable": True,
            "health": {"status": "ok", "opc_connected": True},
            "browse_tags": [],
            "readings": [
                {"tag_name": "Locations", "value": 1.0, "quality": "Good"},
                {"tag_name": "Server", "value": 2.0, "quality": "Good"},
            ],
            "simulated": False,
            "error": None,
        },
    )

    data = collect_opc_monitor()

    assert data["live"]["readings"][0]["tag_name"] == "Temperature"
    assert data["live"]["readings"][0]["value"] == 25.0
    assert data["live"]["simulated"] is True
    assert len(data["live"]["readings"]) == 8


def test_opc_monitor_includes_latest_opc_task(tmp_path, monkeypatch):
    monkeypatch.setenv("OPC_AUDIT_LOG_DIR", str(tmp_path / "audit"))
    rec = TaskRecord("opc-1", "檢查反應槽溫度", "auto", "quick_task")
    rec.resolved_path = "opc"
    rec.phase = "analyze_opc"
    rec.opc_state = {"sense": {"tag_count": 3, "readings": {}}}
    rec.created_at = 2000.0
    monkeypatch.setattr(task_manager, "tasks", {"opc-1": rec})
    monkeypatch.setattr(
        "backend.services.opc_monitor.fetch_opc_live",
        lambda base_url=None: {
            "reachable": True,
            "health": {"status": "ok", "opc_connected": True},
            "browse_tags": [{"tag_name": "Temperature", "value": 87.2}],
            "readings": [
                {"tag_name": "Temperature", "value": 87.2, "quality": "Good"}
            ],
            "error": None,
        },
    )

    data = collect_opc_monitor()

    assert data["live"]["reachable"] is True
    assert data["live"]["readings"][0]["tag_name"] == "Temperature"
    assert data["recent_tasks"][0]["task_id"] == "opc-1"
    assert "events" not in data["recent_tasks"][0]
    assert data["recent_tasks"][0]["opc_state"]["sense"]["tag_count"] == 3


def test_hub_monitor_snapshot_has_nine_models_no_claude():
    reset_runtime()
    runtime.store.append_log(
        {
            "id": "chatcmpl-test",
            "provider": "openai",
            "model_name": "gpt-5.6-sol",
            "status": "success",
            "cost_usd": 0.01,
            "latency_ms": 120,
        }
    )
    task = AgentTask(
        task_id=new_task_id(),
        user_id=runtime.store.seed_dev_user().id,
        status="succeeded",
        input="分析茅台當前估值",
        tools=["StocksX_get_price"],
        cost_usd=0.02,
        chosen_provider="openai",
        created_at=datetime.now(timezone.utc),
    )
    runtime.store.tasks[task.task_id] = task

    data = collect_hub_monitor()
    ids = {m["id"] for m in data["models"]}
    assert len(ids) == 9
    assert "gpt-5.6-sol" in ids
    assert "gemini-3.1-pro" in ids
    joined = " ".join(ids).lower()
    assert "claude" not in joined
    assert "anthropic" not in joined
    assert data["routing"]["forbidden_vendor"] == "anthropic"
    assert data["routing"]["default_chain"][0] == "gpt-5.6-sol"
    assert data["call_log_count"] >= 1
    assert data["call_logs"][0]["model_name"] == "gpt-5.6-sol"
    assert "create_time" in data["call_logs"][0]
    assert data["agent_tasks"][0]["tools"] == ["StocksX_get_price"]
    assert data["cache"]["target_hit_rate"] == 0.40
    for model in data["models"]:
        assert model["circuit"]["state"] in {"CLOSED", "OPEN", "HALF_OPEN"}
    reset_runtime()


def test_agent_monitor_catalog_when_empty(tmp_path, monkeypatch):
    from backend.company.roles import STANDARD_ROLES
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "company_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})
    from backend.company.raho.store import STORE
    STORE.user_sessions.clear()

    data = collect_agent_monitor()
    ids = [a["id"] for a in data["agents"]]

    assert data["summary"]["roles_total"] == len(STANDARD_ROLES)
    assert set(ids) == {role.value for role in STANDARD_ROLES}
    assert data["summary"]["roles_busy"] == 0
    assert data["summary"]["work_items_open"] == 0
    manager = next(a for a in data["agents"] if a["id"] == "manager")
    assert manager["name"] == "專案經理"
    assert manager["status"] == "idle"
    assert manager["level"] == 0
    assert manager["work_items"] == []
    assert manager["current_item"] is None
    assert "tech_lead" in manager["direct_reports"]
    assert "architect" in manager["direct_reports"]
    assert manager["metrics"]["review_pass"] == 0
    assert manager["company_tasks"] == []
    assert manager["capacity_used"] == 0
    assert "quick_task" in manager["templates"]
    assert data["agents"][0]["level"] <= data["agents"][-1]["level"]


def test_agent_monitor_groups_live_kanban_by_role(tmp_path, monkeypatch):
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "empty_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    rec = TaskRecord("co-1", "寫一個登入頁", "company", "fullstack_app")
    rec.resolved_path = "company"
    rec.status = "running"
    rec.phase = "execute_review"
    rec.kanban = {
        "executing": [
            {
                "id": "js-1",
                "title": "實作登入表單",
                "description": "React 表單",
                "assignee": "js_dev",
                "actual_cost": 0.012,
                "output": "",
                "updated_at": "2026-08-26T07:00:00+00:00",
            }
        ],
        "in_review": [
            {
                "id": "css-1",
                "title": "登入頁樣式",
                "description": "RWD",
                "assignee": "css_dev",
                "actual_cost": 0.004,
                "output": "ok",
                "updated_at": "2026-08-26T07:01:00+00:00",
            }
        ],
        "done": [
            {
                "id": "be-1",
                "title": "登入 API",
                "assignee": "backend_dev",
                "actual_cost": 0.02,
                "updated_at": "2026-08-26T06:50:00+00:00",
            }
        ],
    }
    rec.events = [
        {
            "ts": 1_700_000_000,
            "event": "work_item_start",
            "data": {"item_id": "js-1", "title": "實作登入表單", "assignee": "js_dev"},
        },
        {
            "ts": 1_700_000_010,
            "event": "review_pass",
            "data": {"item_id": "be-1", "title": "登入 API", "score": 8},
        },
    ]
    rec.plan = {"subtask_count": 3, "strategy": "hierarchical"}
    monkeypatch.setattr(task_manager, "tasks", {"co-1": rec})

    data = collect_agent_monitor()
    by_id = {a["id"]: a for a in data["agents"]}

    assert by_id["js_dev"]["status"] == "busy"
    assert by_id["js_dev"]["executing"] == 1
    assert by_id["js_dev"]["work_items"][0]["title"] == "實作登入表單"
    assert by_id["js_dev"]["current_item"]["id"] == "js-1"
    assert by_id["js_dev"]["events"][0]["event"] == "work_item_start"
    assert "co-1" in by_id["js_dev"]["active_task_ids"]

    assert by_id["reviewer"]["inbox"]["in_review"] == 1
    assert by_id["reviewer"]["work_items"][0]["kind"] == "review"
    assert by_id["reviewer"]["status"] in {"busy", "waiting"}
    assert by_id["reviewer"]["metrics"]["review_pass"] >= 1
    assert any(t["task_id"] == "co-1" for t in by_id["js_dev"]["company_tasks"])

    assert by_id["backend_dev"]["done"] == 1
    assert by_id["css_dev"]["inbox"]["in_review"] == 1
    assert data["summary"]["running_company_tasks"] == 1
    assert data["summary"]["roles_busy"] >= 1


def test_agent_monitor_manager_and_synthesizer_coordinate(tmp_path, monkeypatch):
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "empty_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    rec = TaskRecord("co-2", "分析茅台估值", "company", "research_report")
    rec.resolved_path = "company"
    rec.status = "running"
    rec.phase = "decompose"
    rec.kanban = {}
    rec.events = [
        {"ts": 1_700_000_100, "event": "company_start", "data": {"goal": "分析茅台估值"}},
        {"ts": 1_700_000_110, "event": "phase_change", "data": {"phase": "decompose"}},
    ]
    monkeypatch.setattr(task_manager, "tasks", {"co-2": rec})

    data = collect_agent_monitor()
    by_id = {a["id"]: a for a in data["agents"]}

    assert by_id["manager"]["status"] == "busy"
    assert any(i["kind"] == "coordinate" for i in by_id["manager"]["work_items"])
    assert any(e["event"] == "company_start" for e in by_id["manager"]["events"])


def test_agent_monitor_reads_run_logs_and_skips_bad_lines(tmp_path, monkeypatch):
    from backend.services.agent_monitor import collect_agent_monitor

    run_dir = tmp_path / "company_runs"
    run_dir.mkdir()
    (run_dir / "run_hist1.jsonl").write_text(
        "\n".join(
            [
                '{"ts": "2026-08-26T01:00:00+00:00", "run_id": "hist1", "event": "work_item_start", "item_id": "d1", "title": "寫 hello world", "assignee": "developer"}',
                "not-json",
                '{"ts": "2026-08-26T01:00:01+00:00", "run_id": "hist1", "event": "work_item_done", "item_id": "d1", "title": "寫 hello world", "assignee": "developer", "cost": 0.006}',
                '{"ts": "2026-08-26T01:00:02+00:00", "run_id": "hist1", "event": "synthesize_done", "cost": 0.1}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(run_dir))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})

    data = collect_agent_monitor()
    by_id = {a["id"]: a for a in data["agents"]}

    titles = [i["title"] for i in by_id["developer"]["work_items"]]
    assert "寫 hello world" in titles
    assert by_id["developer"]["done"] == 1
    assert by_id["developer"]["cost_usd"] >= 0.006
    assert any(e["event"] == "synthesize_done" for e in by_id["synthesizer"]["events"])
    assert by_id["synthesizer"]["cost_usd"] >= 0.1


def test_monitor_agents_http_endpoint(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})

    with TestClient(app) as client:
        resp = client.get("/monitor/agents")

    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["roles_total"] >= 16
    assert any(a["id"] == "manager" and a["name"] == "專案經理" for a in body["agents"])
    assert "work_items" in body["agents"][0]


def test_agent_monitor_includes_extended_roles_and_settings(tmp_path, monkeypatch):
    from backend.company.roles import STANDARD_ROLES
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "company_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})

    data = collect_agent_monitor()
    ids = {a["id"] for a in data["agents"]}
    assert data["summary"]["roles_total"] == len(STANDARD_ROLES)
    for expected in (
        "security_lead",
        "product_lead",
        "data_engineer",
        "prompt_engineer",
        "legal",
        "finance_lead",
        "quant_analyst",
        "industrial_lead",
        "opc_engineer",
        "creative_lead",
        "story_writer",
        "crawler",
        "support",
        "platform_lead",
        "github_ops",
        "hub_operator",
        "memory_curator",
        "risk_analyst",
        "api_engineer",
        "ai_lead",
        "growth_lead",
        "ml_engineer",
        "rag_engineer",
        "qa_automation",
        "plc_engineer",
        "portfolio_mgr",
        "router_eng",
        "customer_success",
    ):
        assert expected in ids
    manager = next(a for a in data["agents"] if a["id"] == "manager")
    assert manager["system_prompt"]
    assert manager["enabled"] is True
    assert manager["is_custom"] is False
    assert "success_rate" in manager["metrics"]
    assert "avg_latency_ms" in manager["metrics"]
    assert manager["routing_strategy"] == "quality_first"
    assert isinstance(manager["alerts"], list)
    assert "p95_latency_ms" in manager["metrics"]
    assert "require_human_approval" in manager
    assert "mainland_only" in manager
    assert "on_call" in manager
    assert data["catalog_meta"]["levels"]
    assert data["catalog_meta"]["role_presets"]
    assert any(p["id"] == "quant_analyst" for p in data["catalog_meta"]["role_presets"])
    assert data["monitor_prefs"]["poll_interval_ms"] >= 2000
    assert "group_by" in data["monitor_prefs"]


def test_custom_role_crud_and_settings_overlay(tmp_path, monkeypatch):
    from backend.company.role_catalog import create_custom_role, update_role_settings
    from backend.services.agent_monitor import collect_agent_monitor

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "company_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})

    created = create_custom_role(
        {
            "id": "trader",
            "name": "量化交易員",
            "level": 3,
            "category": "data",
            "system_prompt": "你負責估值與風險。",
            "responsibilities": ["拉取行情", "產出投資備忘"],
            "daily_budget_usd": 1.5,
            "preferred_model": "gpt-5.6-sol",
        }
    )
    assert created["id"] == "custom_trader"
    assert created["is_custom"] is True

    updated = update_role_settings(
        "manager",
        {
            "system_prompt": "覆蓋後的經理提示詞",
            "max_parallel_work": 8,
            "enabled": True,
        },
    )
    assert updated["system_prompt"] == "覆蓋後的經理提示詞"
    assert updated["max_parallel_work"] == 8

    data = collect_agent_monitor()
    by_id = {a["id"]: a for a in data["agents"]}
    assert by_id["custom_trader"]["name"] == "量化交易員"
    assert by_id["custom_trader"]["daily_budget_usd"] == 1.5
    assert by_id["manager"]["system_prompt"] == "覆蓋後的經理提示詞"
    assert data["summary"]["roles_custom"] == 1

    cloned = create_custom_role(
        {
            "clone_from": "quant_analyst",
            "id": "desk_b",
            "name": "量化分析師 B 席",
            "timeout_ms": 90000,
            "routing_strategy": "cost_first",
        }
    )
    assert cloned["id"] == "custom_desk_b"
    assert "量化分析師" in cloned["system_prompt"]
    assert "market_strategy_catalog" in cloned["system_prompt"]
    assert cloned["timeout_ms"] == 90000
    assert cloned["routing_strategy"] == "cost_first"

    overlayed = update_role_settings(
        "custom_desk_b",
        {
            "on_call": True,
            "mainland_only": True,
            "weekly_budget_usd": 4.0,
            "cloud_daily_budget_usd": 3.5,
            "cloud_weekly_budget_usd": 12.0,
            "tags": ["quant", "b-desk"],
        },
    )
    assert overlayed["on_call"] is True
    assert overlayed["mainland_only"] is True
    assert overlayed["weekly_budget_usd"] == 4.0
    assert overlayed["cloud_daily_budget_usd"] == 3.5
    assert overlayed["cloud_weekly_budget_usd"] == 12.0
    assert "quant" in overlayed["tags"] 


def test_monitor_agents_custom_role_http(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.main import app

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})

    with TestClient(app) as client:
        created = client.post(
            "/monitor/agents",
            json={
                "id": "opc_specialist",
                "name": "OPC 專家",
                "level": 3,
                "category": "devops",
                "system_prompt": "你負責工業標籤診斷。",
                "responsibilities": ["讀取標籤", "診斷異常"],
            },
        )
        assert created.status_code == 200, created.text
        assert created.json()["id"] == "custom_opc_specialist"

        patched = client.put(
            "/monitor/agents/custom_opc_specialist/settings",
            json={
                "daily_budget_usd": 2,
                "cloud_daily_budget_usd": 8,
                "alert_on_error": False,
                "on_call": True,
                "mainland_only": True,
            },
        )
        assert patched.status_code == 200
        assert patched.json()["daily_budget_usd"] == 2
        assert patched.json()["cloud_daily_budget_usd"] == 8
        assert patched.json()["on_call"] is True
        assert patched.json()["mainland_only"] is True

        prefs = client.put("/monitor/agents/prefs", json={"poll_interval_ms": 8000})
        assert prefs.status_code == 200
        assert prefs.json()["poll_interval_ms"] == 8000

        prefs2 = client.put(
            "/monitor/agents/prefs",
            json={"default_layout": "floor", "show_on_call_only": True, "filter_min_level": 1},
        )
        assert prefs2.status_code == 200
        assert prefs2.json()["default_layout"] == "floor"
        assert prefs2.json()["show_on_call_only"] is True
        assert prefs2.json()["filter_min_level"] == 1

        listed = client.get("/monitor/agents")
        ids = {a["id"] for a in listed.json()["agents"]}
        assert "custom_opc_specialist" in ids
        assert "security_eng" in ids
        assert "ai_lead" in ids
        assert "ml_engineer" in ids
        assert "router_eng" in ids

        deleted = client.delete("/monitor/agents/custom_opc_specialist")
        assert deleted.status_code == 200
        listed2 = client.get("/monitor/agents")
        ids2 = {a["id"] for a in listed2.json()["agents"]}
        assert "custom_opc_specialist" not in ids2

        builtin_del = client.delete("/monitor/agents/manager")
        assert builtin_del.status_code == 400


def test_agent_monitor_ingests_auditor_sessions(tmp_path, monkeypatch):
    from backend.company.raho.store import STORE
    from backend.services.agent_monitor import collect_agent_monitor
    from backend.services.auditor import auditor_start

    monkeypatch.setenv("EVOL_COMPANY_RUN_LOG_DIR", str(tmp_path / "empty_runs"))
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "role_catalog.json"))
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_USER_GRILL", "true")
    monkeypatch.setattr("backend.services.auditor._llm_question", lambda *a, **k: None)
    from backend.company.role_catalog import reset_catalog_cache
    reset_catalog_cache()
    monkeypatch.setattr(task_manager, "tasks", {})
    STORE.user_sessions.clear()

    started = auditor_start("我想做一個能幫我自動管粉絲的 AI。")
    data = collect_agent_monitor()
    auditor = next(a for a in data["agents"] if a["id"] == "requirement_auditor")
    assert auditor["status"] == "busy"
    assert auditor["work_items"]
    assert auditor["work_items"][0]["kind"] == "requirement_audit"
    assert started["session_id"] in auditor["work_items"][0]["id"]
    STORE.user_sessions.clear()
