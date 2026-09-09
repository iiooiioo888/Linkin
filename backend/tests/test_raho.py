"""RAHO：遞歸對抗式分層組織單元測試。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.company.raho.atomic_pool import assemble, recycle
from backend.company.raho.context_bus import compress, downward_context, upward_brief
from backend.company.raho.grill_user import (
    grill_user_lock,
    grill_user_start,
    grill_user_turn,
    score_requirement,
    should_grill_user,
)
from backend.company.raho.mgp import (
    apply_mgp_system,
    parse_grill_output,
    rule_inspect_instruction,
)
from backend.company.raho.protocol import (
    GRILL_MARK,
    LAYER_LABELS,
    MGP_EXECUTOR_PREAMBLE,
    RahoLayer,
    annotate_edge,
    attach_raho_fields,
    canonical_role_id,
    raho_directory,
    raho_identity,
    role_to_raho_layer,
)
from backend.company.raho.scorecard import (
    metrics_for,
    record_execution,
    record_grill,
    reset_scorecard,
    should_demote,
)
from backend.company.raho.store import STORE
from backend.company.state import RoleType, WorkItem, WorkItemStatus


@pytest.fixture(autouse=True)
def _reset_raho(monkeypatch):
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_USER_GRILL", "true")
    monkeypatch.setenv("EVOL_RAHO_MGP", "true")
    monkeypatch.setenv("EVOL_RAHO_DECISION_TTL", "0")
    STORE.user_sessions.clear()
    STORE.trees.clear()
    STORE.pending.clear()
    STORE.battle_plans.clear()
    STORE.grill_rounds.clear()
    STORE.shared_memory.clear()
    STORE.l0_traces.clear()
    STORE.l0_prefs.clear()
    STORE.l0_entities.clear()
    reset_scorecard()
    yield
    STORE.user_sessions.clear()
    STORE.trees.clear()
    STORE.pending.clear()
    STORE.battle_plans.clear()
    STORE.grill_rounds.clear()
    STORE.shared_memory.clear()
    STORE.l0_traces.clear()
    STORE.l0_prefs.clear()
    STORE.l0_entities.clear()
    reset_scorecard()


class TestSemanticLock:
    def test_vague_query_scores_low(self):
        score, gaps = score_requirement("提升轉化率")
        assert score < 0.92
        assert gaps

    def test_specific_query_scores_higher(self):
        vague, _ = score_requirement("提升轉化率")
        score, _ = score_requirement(
            "把現有用戶復購率從 12% 提升到 18%，預算上限 8 萬，兩週內上線促銷頁，品質不可降。"
        )
        assert score > vague
        assert score > 0.2

    def test_should_grill_skips_simple_and_chitchat(self):
        assert should_grill_user("你好", "simple") is False
        assert should_grill_user("你好", "auto") is False
        assert should_grill_user("開發一個完整登入系統", "auto") is True
        assert should_grill_user("隨便", "company") is True

    def test_start_asks_then_lock(self, monkeypatch):
        monkeypatch.setattr(
            "backend.services.auditor._llm_question",
            lambda *a, **k: None,
        )
        started = grill_user_start("提升轉化率")
        assert started["locked"] is False
        assert started["question"]["question"]
        assert started["role"] == "requirement_auditor"
        sid = started["session_id"]
        mid = grill_user_turn(
            sid,
            "現有用戶復購，目標從 12% 到 18%，預算 5 萬，超支先縮範圍。",
        )
        assert mid["session_id"] == sid
        assert mid["locked"] is False
        locked = grill_user_lock(sid, "最小可用成果是一頁促銷與追蹤報表")
        assert locked["terminated"] is True
        assert locked["locked"] is False
        assert "無法為我無法理解的目標負責" in (locked.get("termination_reason") or "")
        tree = STORE.get_tree(STORE.user_grill_run_id(sid))
        assert tree is not None
        kinds = {n.kind for n in tree.nodes}
        assert "user_grill" in kinds
        assert any(n.from_layer == 4 and n.to_layer == 5 for n in tree.nodes)


class TestMgp:
    def test_unmarked_output_is_clear(self):
        kind, issues = parse_grill_output("API 文件已完成")
        assert kind == "clear"
        assert issues == []

    def test_grill_marker_parsed(self):
        kind, issues = parse_grill_output(f"{GRILL_MARK} 缺少競品 B 訂價區間")
        assert kind == "grill"
        assert issues and "競品" in issues[0].message

    def test_preamble_injected_once(self):
        first = apply_mgp_system("你是開發者")
        assert first.startswith(MGP_EXECUTOR_PREAMBLE)
        second = apply_mgp_system(first)
        assert second.count("強制質詢協議") == 1

    def test_rule_inspect_short_description(self):
        issues = rule_inspect_instruction("SWOT", "")
        assert any(i.field == "description" for i in issues)


class TestAtomicAndBus:
    def test_assemble_and_recycle(self):
        item = WorkItem(title="撰寫競品 A 的 SWOT 報告", description="產出四象限", assignee=RoleType.ANALYST)
        card = assemble(item)
        assert card["disposable"] is True
        assert "SWOT" in card["system_prompt"] or "swot" in card["template_id"]
        item.artifacts["output"] = "S/W/O/T"
        distilled = recycle(item)
        assert distilled is not None
        assert "atomic_role" not in item.artifacts
        assert item.artifacts["atomic_distill"]["title"] == item.title

    def test_downward_context_truncates(self):
        parent = WorkItem(title="調研", description="d")
        parent.status = WorkItemStatus.DONE
        parent.artifacts["output"] = "X" * 4000
        child = WorkItem(title="分析", description="d", depends_on=[parent.id])
        ctx = downward_context(child, [parent])
        assert "前置交付" in ctx
        assert len(ctx) < 1200

    def test_downward_context_prefers_input_ref(self):
        parent = WorkItem(title="調研", description="d")
        parent.status = WorkItemStatus.DONE
        parent.artifacts["output"] = "不該灌進 L2 的長文" * 40
        child = WorkItem(title="分析", description="d", depends_on=[parent.id])
        child.artifacts["input_ref"] = "shared_memory://results/N1_output.json"
        child.artifacts["allowed_tools"] = ["read_memory"]
        ctx = downward_context(child, [parent])
        assert "shared_memory://results/N1_output.json" in ctx
        assert "不該灌進 L2 的長文" not in ctx

    def test_upward_brief_and_compress(self):
        brief = upward_brief(title="T", description="D" * 400, issues=["缺欄位"])
        assert "缺欄位" in brief
        assert "…" in compress("A" * 900, 40)


class TestScorecardAndTree:
    def test_grill_rate_lowers_clarity(self):
        record_execution("manager")
        record_execution("manager")
        record_grill("manager")
        card = metrics_for("manager")
        assert card["grill_count"] == 1
        assert card["grill_rate"] == 0.5
        assert card["decision_clarity"] < 1.0
        assert card["rank"] in {"ok", "watch", "demoted"}
        record_execution("manager")
        record_grill("manager")
        record_grill("manager")
        assert should_demote("manager") is True
        demoted = metrics_for("manager")
        assert demoted["demoted"] is True
        assert demoted["rank"] == "demoted"

    def test_tree_records_nodes(self):
        node = STORE.add_node(
            "run1",
            from_layer=int(RahoLayer.L2_EXECUTOR),
            to_layer=int(RahoLayer.L3_DECOMPOSER),
            kind="mgp",
            summary="缺資料",
            goal="戰役",
        )
        snap = STORE.snapshot()
        assert snap["trees"]
        assert snap["blocked"]
        payload = node.to_dict()
        assert payload["from_label"] == LAYER_LABELS[2]
        assert payload["to_label"] == LAYER_LABELS[3]
        assert payload["kind_label"] == "戰前質詢"
        assert snap["directory"][0]["full"] == LAYER_LABELS[0]
        assert snap["directory"][1]["full"] == LAYER_LABELS[1]
        assert snap["l0"]["role_id"] == "environment_kernel"
        STORE.resolve_node("run1", node.node_id)
        tree = STORE.get_tree("run1")
        assert tree is not None
        assert tree.nodes[0].status == "resolved"


class TestRahoIdentity:
    def test_spine_roles_match_layers(self):
        assert role_to_raho_layer(RoleType.CONSTITUTIONAL_INSPECTOR) == RahoLayer.L1_INSPECTOR
        assert role_to_raho_layer(RoleType.TACTICAL_COMMANDER) == RahoLayer.L3_COMMANDER
        assert role_to_raho_layer(RoleType.REQUIREMENT_AUDITOR) == RahoLayer.L4_AUDITOR
        assert RahoLayer.L1_GRILL is RahoLayer.L1_INSPECTOR
        assert RahoLayer.L3_DECOMPOSER is RahoLayer.L3_COMMANDER
        assert RahoLayer.L4_PLANNER is RahoLayer.L4_AUDITOR

    def test_identity_labels_are_canonical(self):
        inspector = raho_identity("constitutional_inspector")
        assert inspector["full"] == "L1 憲兵審查官"
        assert inspector["spine"] is True
        commander = raho_identity("tactical_commander")
        assert commander["full"] == "L3 戰術指揮官"
        auditor = raho_identity("requirement_auditor")
        assert auditor["full"] == "L4 需求審計官"
        user = raho_identity(layer=5)
        assert user["role_id"] == "user"
        kernel = raho_identity("environment_kernel")
        assert kernel["full"] == "L0 環境與記憶核心"
        assert kernel["spine"] is True
        assert kernel["lane"] == "kernel"
        l2 = raho_identity(layer=2)
        assert l2["role_id"] == "atomic_executor"
        assert l2["full"] == "L2 原子執行者"
        assert l2["lane"] == "command"
        assert canonical_role_id(2) == "atomic_executor"
        assert [row["full"] for row in raho_directory()] == [
            "L0 環境與記憶核心",
            "L1 憲兵審查官",
            "L2 原子執行者",
            "L3 戰術指揮官",
            "L4 需求審計官",
            "L5 用戶",
        ]

    def test_attach_and_edge_use_same_names(self):
        snap = attach_raho_fields({"id": "constitutional_inspector", "name": "憲兵審查官"})
        assert snap["raho_label"] == "L1 憲兵審查官"
        lead = attach_raho_fields({"id": "tech_lead", "name": "技術主管"})
        assert lead["raho_layer"] == 3
        assert lead["raho_label"] == "L3 技術主管"
        assert lead["raho_spine"] is False
        edge = annotate_edge(1, 3)
        assert edge["from_label"] == "L1 憲兵審查官"
        assert edge["to_label"] == "L3 戰術指揮官"
        l2_edge = annotate_edge(2, 3)
        assert l2_edge["from_role"] == "atomic_executor"
        assert l2_edge["from_label"] == "L2 原子執行者"

    def test_grill_chain_and_reports(self):
        from backend.company.raho.protocol import (
            COMMAND_CHAIN,
            GRILL_EDGES,
            INSPECT_CHAIN,
            KERNEL_CHAIN,
            grill_edges,
            raho_graph,
            superior_layer,
        )
        from backend.company.roles import STANDARD_ROLES

        inspector = raho_identity("constitutional_inspector")
        assert inspector["grill_targets"] == ["atomic_executor", "tactical_commander"]
        assert inspector["independent"] is True
        assert inspector["reports_to"] is None
        assert inspector["lane"] == "inspect"
        commander = STANDARD_ROLES[RoleType.TACTICAL_COMMANDER]
        assert commander.reporting_to == RoleType.REQUIREMENT_AUDITOR
        executor = STANDARD_ROLES[RoleType.ATOMIC_EXECUTOR]
        assert executor.reporting_to == RoleType.TACTICAL_COMMANDER
        l2 = raho_identity("atomic_executor")
        assert l2["grill_targets"] == ["tactical_commander"]
        assert l2["escalate_targets"] == [
            "tactical_commander",
            "requirement_auditor",
            "user",
        ]
        assert l2["submit_targets"] == ["constitutional_inspector"]
        l3 = raho_identity("tactical_commander")
        assert l3["grill_targets"] == ["requirement_auditor"]
        assert "user" not in l3["grill_targets"]
        assert "user" in l3["escalate_targets"]
        edges = grill_edges()
        assert len(edges) == len(GRILL_EDGES)
        assert any(e["from_role"] == "atomic_executor" and e["to_role"] == "tactical_commander" for e in edges)
        assert any(e["kind"] == "campaign" and e["direction"] == "down" for e in edges)
        rework = next(e for e in edges if e["kind"] == "rework")
        assert rework["direction"] == "inspect"
        assert rework["from_role"] == "constitutional_inspector"
        submit = next(e for e in edges if e["kind"] == "submit")
        assert submit["from_role"] == "atomic_executor"
        assert submit["to_role"] == "constitutional_inspector"
        assert submit["direction"] == "inspect"
        assert any(e["kind"] == "l0" and e["direction"] == "inject" for e in edges)
        assert superior_layer(RahoLayer.L1_INSPECTOR) == RahoLayer.L4_AUDITOR
        assert superior_layer(RahoLayer.L2_EXECUTOR) == RahoLayer.L3_COMMANDER
        assert superior_layer(RahoLayer.L0_KERNEL) == RahoLayer.L0_KERNEL
        directory = raho_directory()
        assert directory[1]["grill_targets"] == ["atomic_executor", "tactical_commander"]
        assert "L2 原子執行者" in directory[1]["grill_target_labels"]
        graph = raho_graph()
        assert graph["command_chain"] == list(COMMAND_CHAIN)
        assert graph["inspect_chain"] == list(INSPECT_CHAIN)
        assert graph["kernel_chain"] == list(KERNEL_CHAIN)
        assert graph["lanes"]["inspect"]["layers"] == [1]


class TestEscalationTtl:
    @pytest.mark.asyncio
    async def test_timeout_zero_auto_picks(self, monkeypatch):
        from backend.company.raho.escalation import wait_user_decision
        from backend.company.raho.protocol import EscalationChoice

        result = await wait_user_decision(
            run_id="r2",
            item_id="i1",
            question="選路",
            choices=[EscalationChoice("assume", "假設後繼續")],
            ttl=0,
        )
        assert result["timeout"] is True
        assert result["choice"] == "assume"

    def test_decide_idempotent_after_timeout(self):
        """逾時後再點選應回傳既有結果，勿 404。"""
        from backend.company.raho.escalation import decide
        from backend.company.raho.protocol import EscalationChoice, RahoLayer
        from backend.company.raho.store import STORE, PendingDecision
        import time

        pending = PendingDecision(
            decision_id="idem01",
            run_id="r-idem",
            item_id="i1",
            layer=int(RahoLayer.L5_USER),
            question="ALLOWED_TOOLS 為空，但任務描述需要讀檔／擷取／解析類工具。",
            choices=[c.to_dict() for c in [
                EscalationChoice("assume", "標註合理假設後繼續執行"),
                EscalationChoice("narrow", "縮小輸出規格，先交付最小可用版本"),
            ]],
            created_at=time.time() - 120,
            ttl=60,
            resolution={
                "action": "auto",
                "choice": "assume",
                "reply": "標註合理假設後繼續執行（決策逾時自動裁決）",
                "timeout": True,
            },
        )
        STORE.add_pending(pending)
        out = decide("idem01", "narrow")
        assert out.get("idempotent") is True
        assert out["resolution"]["choice"] == "assume"

    def test_auto_reissue_tools_for_allowed_tools_gap(self):
        from backend.company.raho.atomic_executor import BLOCKER_TOOL, GrillMessage
        from backend.company.raho.escalation import _auto_reissue_tools, _tool_only_issues

        issue = GrillMessage(
            blocker_type=BLOCKER_TOOL,
            details="ALLOWED_TOOLS 為空，但任務描述需要讀檔／擷取／解析類工具。",
            suggested_fix="請重發工具白名單",
        ).to_issue()
        assert _tool_only_issues([issue]) is True
        tools = _auto_reissue_tools([issue], None)
        assert tools
        assert "read_file" in tools


class TestRahoApi:
    def test_grill_and_tree_endpoints(self, monkeypatch):
        monkeypatch.setattr(
            "backend.services.auditor._llm_question",
            lambda *a, **k: None,
        )
        from backend.main import app

        with TestClient(app) as client:
            skipped = client.post(
                "/raho/grill/start",
                json={"query": "你好", "execution_strategy": "auto"},
            )
            assert skipped.status_code == 200
            assert skipped.json()["should_grill"] is False

            started = client.post(
                "/raho/grill/start",
                json={"query": "打造完整成長策略", "execution_strategy": "company"},
            )
            assert started.status_code == 200
            body = started.json()
            assert body["locked"] is False
            sid = body["session_id"]
            locked = client.post(
                "/raho/grill/turn",
                json={"session_id": sid, "answer": "直接執行", "force_lock": True},
            )
            assert locked.status_code == 200
            body = locked.json()
            assert body["locked"] is False
            assert body["terminated"] is True
            assert body["status"] == "FAILED"

            tree = client.get("/raho/tree")
            assert tree.status_code == 200
            assert "trees" in tree.json()
            status = client.get("/raho/grill/status")
            assert status.json()["enabled"] is True
            assert status.json()["lock_threshold"] == 0.92


class TestCampaignPlanner:
    def test_rule_plan_growth_goal(self):
        from backend.company.raho.planner import plan_campaign_rule, tag_work_items

        cmap = plan_campaign_rule("把現有用戶復購率從 12% 提升到 18%，並做促銷頁")
        assert len(cmap.nodes) >= 3
        assert cmap.nodes[0].node_id == "A"
        assert any(n.depends_on for n in cmap.nodes[1:])
        assert cmap.success_criteria
        item = WorkItem(title="撰寫競品 SWOT", description="四象限", assignee=RoleType.ANALYST)
        tag_work_items([item], cmap)
        assert item.artifacts["campaign_node"]["node_id"]

    def test_choice_parse_and_superior_scorecard(self):
        from backend.company.raho.mgp import parse_choices, parse_grill_output
        from backend.company.raho.protocol import CHOICE_MARK, GRILL_MARK

        kind, issues = parse_grill_output(
            f"{CHOICE_MARK} 競品 B 發布新產品\nA: 改打差異化\nB: 暫緩等數據\nC: 轉向競品 A"
        )
        assert kind == "escalate"
        assert issues
        choices = parse_choices(f"{CHOICE_MARK}\nA: 改打差異化\nB: 暫緩等數據")
        assert [c.key for c in choices] == ["a", "b"]
        record_grill("manager")
        card = metrics_for("manager")
        assert card["grill_count"] >= 1
        assert GRILL_MARK


class TestOrchestratorCompatible:
    @pytest.mark.asyncio
    async def test_mgp_clear_does_not_extra_call(self):
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.raho.mgp import parse_grill_output

        orch = CompanyOrchestrator()
        kind, _ = parse_grill_output("交付物正文")
        raw, prompt = await orch._maybe_resolve_mgp(
            "goal",
            WorkItem(title="t", description="enough text here"),
            RoleType.DEVELOPER,
            "交付物正文",
            "prompt",
            "sys",
            "m",
            {},
            5,
        )
        assert kind == "clear"
        assert raw == "交付物正文"
        assert prompt == "prompt"

    def test_escalation_patch_writes_tools_and_budget(self):
        from backend.company.orchestrator import CompanyOrchestrator

        orch = CompanyOrchestrator()
        item = WorkItem(title="t", description="enough text here")
        item.artifacts["atomic_role"] = {"task_layer": {}, "allowed_tools": []}
        orch._apply_escalation_patch(
            item,
            {
                "reissued_tools": ["web_search"],
                "reissued_budget": {"max_iterations": 3, "token_budget": 800},
            },
        )
        assert item.artifacts["allowed_tools"] == ["web_search"]
        assert item.artifacts["max_iterations"] == 3
        assert item.artifacts["atomic_role"]["allowed_tools"] == ["web_search"]
