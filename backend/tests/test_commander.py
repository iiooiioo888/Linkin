"""L3 戰術指揮官：門票檢查、原子 DAG、Grill SOP、上交協議。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.company.raho.protocol import ESCALATE_MARK, GrillIssue
from backend.company.raho.store import STORE
from backend.company.roles import STANDARD_ROLES
from backend.company.state import RoleType
from backend.services.commander import (
    MAX_L2_PROMPT_TOKENS,
    SYSTEM_PROMPT,
    STATUS_ESCALATE_USER,
    STATUS_PLAN_READY,
    STATUS_REJECT_L4,
    TacticalCommander,
    apply_commander_system,
    classify_grill,
    count_verbs,
    estimate_tokens,
    extract_ticket,
    has_concrete_object,
    hours_until_deadline,
    l2_task_brief,
    normalize_tools,
    plan_from_ticket,
    respond_to_grill,
    serial_depth,
    validate_ticket,
)


@pytest.fixture(autouse=True)
def _reset_commander(monkeypatch):
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_COMMANDER_LLM", "false")
    STORE.user_sessions.clear()
    STORE.battle_plans.clear()
    STORE.grill_rounds.clear()
    yield
    STORE.user_sessions.clear()
    STORE.battle_plans.clear()
    STORE.grill_rounds.clear()


VALID_TICKET = {
    "status": "APPROVED_FOR_PLANNING",
    "confidence_score": 94.5,
    "clarified_goal": {
        "target_audience": "電商進階賣家",
        "core_action": "自動生成競品價格預警",
        "quantified_success": "目前每日人工 4 小時，目標壓縮至 0.5 小時，準確率 95%",
    },
    "hard_constraints": {
        "deadline": "2026-10-15",
        "budget_range": "預算新台幣 15~20 萬",
        "must_use_tech": ["Python", "PostgreSQL"],
        "absolute_exclusions": ["不做手機 APP", "不使用爬蟲"],
    },
    "risk_register": {
        "identified_risks": ["API 斷線改手動 CSV"],
        "user_priority": "Cost > Time > Quality",
    },
}


class TestRole:
    def test_builtin_l3_role_registered(self):
        assert RoleType.TACTICAL_COMMANDER in STANDARD_ROLES
        role = STANDARD_ROLES[RoleType.TACTICAL_COMMANDER]
        assert role.level == 2
        assert "原子" in "".join(role.responsibilities)
        assert "Atomic SRP" in SYSTEM_PROMPT
        assert "Context Isolation" in SYSTEM_PROMPT
        assert "Tool Whitelist" in SYSTEM_PROMPT
        assert "Grill-Response Obligation" in SYSTEM_PROMPT
        assert "拆解四步法" in SYSTEM_PROMPT
        assert "微雕與偏執" in SYSTEM_PROMPT
        assert "強制內部檢查清單" in SYSTEM_PROMPT
        assert "Grill-Me" in SYSTEM_PROMPT
        assert "ESCALATE_TO_USER" in SYSTEM_PROMPT
        assert "battle_plan" in SYSTEM_PROMPT
        assert "shared_memory://" in SYSTEM_PROMPT
        assert "Blackboard" in SYSTEM_PROMPT
        assert "以 A 為準" in SYSTEM_PROMPT
        assert "基礎設施缺失" in role.system_prompt or "極速" in role.system_prompt


class TestTicketGate:
    def test_vague_action_rejected(self):
        assert has_concrete_object("處理數據") is False
        assert has_concrete_object("分析競品定價") is True

    def test_empty_exclusions_reject(self):
        ticket = {
            **VALID_TICKET,
            "hard_constraints": {**VALID_TICKET["hard_constraints"], "absolute_exclusions": []},
        }
        check = validate_ticket(ticket)
        assert check["ok"] is False
        assert any("exclusions" in d for d in check["defects"])

    def test_placeholder_exclusions_reject(self):
        ticket = {
            **VALID_TICKET,
            "hard_constraints": {
                **VALID_TICKET["hard_constraints"],
                "absolute_exclusions": ["未明示絕對排除項，Planner 不得自行擴 scope"],
            },
        }
        assert validate_ticket(ticket)["ok"] is False

    def test_rush_mode_when_deadline_under_48h(self):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        soon = (now + timedelta(hours=24)).strftime("%Y-%m-%d")
        ticket = {
            **VALID_TICKET,
            "hard_constraints": {**VALID_TICKET["hard_constraints"], "deadline": soon},
        }
        check = validate_ticket(ticket, now=now)
        assert check["ok"] is True
        assert check["rush_mode"] is True
        assert hours_until_deadline("24小時內") == 24

    def test_invalid_ticket_rejected(self):
        pack = plan_from_ticket({"status": "DRAFT"}, use_llm=False)
        assert pack["status"] == STATUS_REJECT_L4

    def test_checklist_items_present(self):
        check = validate_ticket(VALID_TICKET)
        ids = {row["id"] for row in check["items"]}
        assert ids == {"core_action_object", "deadline_48h", "exclusions_nonempty"}
        assert all(row["pass"] for row in check["items"])

    def test_l2_brief_stays_under_token_cap(self):
        brief = l2_task_brief(
            title="擷取競品價格",
            input_ref=["shared_memory://results/N1_output.json", "shared_memory://results/N2_output.json"],
            output_schema="Plain Text (Max 200 chars)",
            success_criteria="明確包含『高/中/低』判定",
            allowed_tools=["read_memory", "text_analyzer"],
        )
        assert estimate_tokens(brief) <= MAX_L2_PROMPT_TOKENS
        assert "shared_memory://" in brief
        assert "戰役" not in brief or "禁止繼承戰役" in brief


class TestBattlePlan:
    def test_valid_ticket_emits_atomic_dag(self):
        pack = plan_from_ticket(VALID_TICKET, use_llm=False)
        assert pack["status"] == STATUS_PLAN_READY
        plan = pack["battle_plan"]
        assert plan["dag_nodes"]
        assert plan["atomic_role_instances"]
        yaml_text = pack["battle_plan_yaml"]
        assert yaml_text.startswith("# L3 戰術指揮官產出之物")
        assert "battle_plan:" in yaml_text
        assert "孵化清單" in yaml_text
        assert "節點拓撲 (DAG)" in yaml_text
        assert "reasoning:" not in yaml_text
        cot = pack["reasoning"]
        assert cot["parsing"]["core_action"]
        assert cot["topology"]["parallel"]
        assert cot["templating"]
        assert cot["budgeting"]
        roots = [n for n in plan["dag_nodes"] if not n.get("depends_on")]
        assert len(roots) >= 2
        assert serial_depth(plan["dag_nodes"]) >= 2
        for node in plan["dag_nodes"]:
            assert count_verbs(node["description"]) <= 3
        for inst in plan["atomic_role_instances"]:
            assert estimate_tokens(inst["system_prompt"]) <= MAX_L2_PROMPT_TOKENS
            assert inst["allowed_tools"]
            assert "all" not in inst["allowed_tools"]
            assert inst["input_ref"]
            assert inst["output_schema"]
            assert inst["token_budget"] > 0
            assert "web_fetch" not in inst["allowed_tools"]
            assert "Input Ref" in inst["system_prompt"] or "輸入來源" in inst["system_prompt"]
            assert inst.get("name")
            assert inst.get("trait")
            assert inst.get("template_id")
            assert inst.get("failure_fallback")
            assert "（" in inst["system_prompt"] or inst["trait"] in inst["system_prompt"]

    def test_rush_mode_caps_serial_depth_keeps_parallel(self):
        now = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
        ticket = {
            **VALID_TICKET,
            "hard_constraints": {**VALID_TICKET["hard_constraints"], "deadline": "2026-09-09"},
        }
        pack = plan_from_ticket(ticket, now=now, use_llm=False)
        assert pack["rush_mode"] is True
        assert serial_depth(pack["battle_plan"]["dag_nodes"]) <= 2
        roots = [n for n in pack["battle_plan"]["dag_nodes"] if not n.get("depends_on")]
        assert len(roots) >= 1

    def test_infeasible_escalates_to_user(self):
        ticket = {
            **VALID_TICKET,
            "clarified_goal": {
                **VALID_TICKET["clarified_goal"],
                "core_action": "24 小時內爬完 100 萬個網頁價格",
            },
            "hard_constraints": {**VALID_TICKET["hard_constraints"], "deadline": "24小時"},
        }
        pack = plan_from_ticket(ticket, use_llm=False)
        assert pack["status"] == STATUS_ESCALATE_USER
        assert pack["waiting_for_user_decision"] is True
        assert pack["suggested_alternatives"]
        assert any("1,000" in alt or "1000" in alt for alt in pack["suggested_alternatives"])

    def test_user_override_skips_infeasible(self):
        ticket = {
            **VALID_TICKET,
            "clarified_goal": {
                **VALID_TICKET["clarified_goal"],
                "core_action": "24 小時內爬完 100 萬個網頁價格",
            },
            "hard_constraints": {**VALID_TICKET["hard_constraints"], "deadline": "24小時"},
            "user_override": "方案 A：將樣本縮減至 1,000 筆（推薦）",
        }
        pack = plan_from_ticket(ticket, use_llm=False)
        assert pack["status"] == STATUS_PLAN_READY

    def test_extract_ticket_from_locked_brief(self):
        import json

        brief = "前文\n```json\n" + json.dumps(VALID_TICKET, ensure_ascii=False) + "\n```"
        parsed = extract_ticket(brief)
        assert parsed is not None
        assert parsed["clarified_goal"]["core_action"] == "自動生成競品價格預警"

    def test_tools_never_all(self):
        assert normalize_tools(["all", "web_fetch", "*"]) == ["web_fetch"]
        assert normalize_tools([]) == ["read_memory"]

    def test_crawl_allowed_uses_parallel_scouts(self):
        ticket = {
            **VALID_TICKET,
            "hard_constraints": {
                **VALID_TICKET["hard_constraints"],
                "absolute_exclusions": ["不做手機 APP"],
            },
        }
        pack = plan_from_ticket(ticket, use_llm=False)
        plan = pack["battle_plan"]
        templates = {n["assigned_role_template"] for n in plan["dag_nodes"]}
        assert "web_scraper" in templates
        assert "social_listener" in templates
        tools = {t for inst in plan["atomic_role_instances"] for t in inst["allowed_tools"]}
        assert "web_fetch" in tools


class TestGrillSop:
    def test_clarification_resolves_in_one_round(self):
        sop = respond_to_grill("你說的『高品質』具體是指語法正確還是內容深刻？")
        assert sop["kind"] == "clarification"
        assert sop["escalate"] is False
        assert "2" in sop["reply"]

    def test_data_missing_escalates_l4(self):
        sop = respond_to_grill("你給的欄位 A 不存在於來源中")
        assert sop["kind"] == "data_missing"
        assert sop["escalate_to"] == "L4"
        assert ESCALATE_MARK in sop["reply"]

    def test_data_missing_uses_alternative(self):
        sop = respond_to_grill("欄位 price 不存在", alternative_fields=["list_price"])
        assert sop["escalate"] is False
        assert "list_price" in sop["reply"]

    def test_unknown_tool_escalates_l5(self):
        sop = respond_to_grill("我無法用 read_file 處理 .mov，需要 ffmpeg")
        assert sop["kind"] == "tool_insufficient"
        assert sop["escalate_to"] == "L5"

    def test_known_tool_reissued(self):
        sop = respond_to_grill("我無法用 web_fetch 讀這個 URL", allowed_tools=["web_search"])
        assert sop["escalate"] is False
        assert "web_fetch" in sop["reply"]

    def test_empty_allowed_tools_reissued_instead_of_l5(self):
        from backend.company.raho.atomic_executor import BLOCKER_TOOL, GrillMessage
        from backend.services.commander import infer_tools_from_text

        issue = GrillMessage(
            blocker_type=BLOCKER_TOOL,
            details="ALLOWED_TOOLS 為空，但任務描述需要讀檔／擷取／解析類工具。",
            suggested_fix="請重發工具白名單",
        ).to_issue()
        sop = respond_to_grill([issue])
        assert sop["escalate"] is False
        assert sop.get("reissued_tools")
        assert "read_file" in sop["reissued_tools"]
        inferred = infer_tools_from_text(issue.message)
        assert "read_file" in inferred

    def test_tool_gap_preferred_when_mixed_with_data(self):
        from backend.company.raho.atomic_executor import BLOCKER_INPUT, BLOCKER_TOOL, GrillMessage

        issues = [
            GrillMessage(
                blocker_type=BLOCKER_INPUT,
                details="INPUT_REF 為空值或占位符，無法定位任何輸入資料。",
                suggested_fix="請提供路徑",
            ).to_issue(),
            GrillMessage(
                blocker_type=BLOCKER_TOOL,
                details="ALLOWED_TOOLS 為空，但任務描述需要讀檔／擷取／解析類工具。",
                suggested_fix="請重發工具白名單",
            ).to_issue(),
        ]
        sop = respond_to_grill(issues)
        # 資料仍上交 L4，但工具必須一併重發，避免只丟 L5 決策列
        assert sop.get("reissued_tools")
        assert "read_file" in sop["reissued_tools"]
        assert sop.get("escalate_to") == "L4"

    def test_logic_conflict_rules_when_nodes_named(self):
        sop = respond_to_grill("你的 A 節點要求保守估值，但 B 節點要求激進擴張，我無法同時滿足")
        assert sop["kind"] == "logic_conflict"
        assert sop["escalate"] is False
        assert "以 A 為準" in sop["reply"]
        assert "B 需修正" in sop["reply"]

    def test_logic_conflict_escalates_without_ruling(self):
        sop = respond_to_grill("兩條路線互相矛盾，我無法同時滿足")
        assert sop["kind"] == "logic_conflict"
        assert sop["escalate_to"] == "L4"

    def test_three_rounds_force_escalate(self):
        sop = respond_to_grill("再確認一次範圍？", rounds_used=3)
        assert sop["escalate"] is True

    def test_classify_helpers(self):
        from backend.services.commander import GRILL_SOP

        assert classify_grill([GrillIssue("資料缺失：欄位不存在", kind="gap")]) == "data_missing"
        assert set(GRILL_SOP) >= {"data_missing", "tool_insufficient", "logic_conflict", "clarification"}
        assert GRILL_SOP["clarification"]["escalate_if_unresolved"] is False

    def test_apply_commander_system_is_idempotent(self):
        once = apply_commander_system("既有上級指令")
        twice = apply_commander_system(once)
        assert once.count("微雕與偏執") == 1
        assert twice == once
        assert "Atomic SRP" in once


class TestClassAndApi:
    def test_class_gateway(self):
        cmd = TacticalCommander()
        pack = cmd.plan(VALID_TICKET, use_llm=False)
        assert pack["status"] == STATUS_PLAN_READY
        grill = cmd.grill("高品質是什麼意思")
        assert grill["escalate"] is False

    def test_plan_endpoint(self):
        from backend.main import app

        with TestClient(app) as client:
            resp = client.post("/raho/commander/plan", json={"ticket": VALID_TICKET, "use_llm": False})
            assert resp.status_code == 200
            body = resp.json()
            assert body["status"] == STATUS_PLAN_READY
            assert body["battle_plan"]["dag_nodes"]

    def test_grill_endpoint(self):
        from backend.main import app

        with TestClient(app) as client:
            resp = client.post(
                "/raho/commander/grill",
                json={"message": "欄位 A 不存在於來源中"},
            )
            assert resp.status_code == 200
            assert resp.json()["escalate_to"] == "L4"

    def test_grill_stream_endpoint(self):
        from backend.main import app

        with TestClient(app) as client:
            resp = client.post(
                "/raho/commander/grill/stream",
                json={"message": "欄位 A 不存在於來源中"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers.get("content-type", "")
            assert "event: done" in resp.text
            assert "L4" in resp.text

    def test_reject_endpoint(self):
        from backend.main import app

        bad = {
            **VALID_TICKET,
            "clarified_goal": {**VALID_TICKET["clarified_goal"], "core_action": "處理數據"},
        }
        with TestClient(app) as client:
            resp = client.post("/raho/commander/plan", json={"ticket": bad, "use_llm": False})
            assert resp.json()["status"] == STATUS_REJECT_L4


class TestOrchestratorHook:
    def test_build_from_battle_plan_incubates_l2(self):
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.raho.commander import command_from_ticket

        pack = command_from_ticket(VALID_TICKET, use_llm=False)
        orch = CompanyOrchestrator()
        items = orch._build_from_battle_plan(pack["battle_plan"])
        assert items
        assert all(item.artifacts.get("atomic_role") for item in items)
        assert all(item.artifacts["atomic_role"].get("system_prompt") for item in items)

    @pytest.mark.asyncio
    async def test_execute_rejects_bad_ticket_without_running(self):
        from backend.company.orchestrator import CompanyOrchestrator

        bad = {
            **VALID_TICKET,
            "clarified_goal": {**VALID_TICKET["clarified_goal"], "core_action": "處理數據"},
        }
        orch = CompanyOrchestrator()
        result = await orch.execute("不該被拆解", ticket=bad)
        assert result["success"] is False
        assert result["status"] == STATUS_REJECT_L4
        assert result["commander"]["waiting_for_l4"] is True
