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
from backend.company.raho.protocol import GRILL_MARK, MGP_EXECUTOR_PREAMBLE, RahoLayer
from backend.company.raho.scorecard import (
    metrics_for,
    record_execution,
    record_grill,
    reset_scorecard,
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
    reset_scorecard()
    yield
    STORE.user_sessions.clear()
    STORE.trees.clear()
    STORE.pending.clear()
    reset_scorecard()


class TestSemanticLock:
    def test_vague_query_scores_low(self):
        score, gaps = score_requirement("提升轉化率")
        assert score < 0.92
        assert "metric" in gaps

    def test_specific_query_scores_higher(self):
        score, _ = score_requirement(
            "把現有用戶復購率從 12% 提升到 18%，預算上限 8 萬，兩週內上線促銷頁，品質不可降。"
        )
        assert score > 0.55

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
        STORE.resolve_node("run1", node.node_id)
        tree = STORE.get_tree("run1")
        assert tree is not None
        assert tree.nodes[0].status == "resolved"


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
