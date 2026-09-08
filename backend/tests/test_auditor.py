"""L4 需求審計官：五維鎖定、四階段追問、終止協議與戰術指令。"""

from __future__ import annotations

import pytest

from backend.company.raho.store import STORE
from backend.company.roles import STANDARD_ROLES
from backend.company.state import RoleType
from backend.services.auditor import (
    RequirementAuditor,
    all_dims_locked,
    auditor_start,
    auditor_turn,
    extract_json,
    score_dimensions,
    should_grill_user,
)


@pytest.fixture(autouse=True)
def _reset_auditor(monkeypatch):
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_USER_GRILL", "true")
    monkeypatch.setattr("backend.services.auditor._llm_question", lambda *a, **k: None)
    STORE.user_sessions.clear()
    yield
    STORE.user_sessions.clear()


RICH_A1 = (
    "最終用戶是電商平台進階賣家（月營業額 > 50 萬）。介入前每天人工盯盤 4 小時、"
    "每月因反應慢損失約 8 萬營收；介入後自動生成競品價格預警。發起人是終端賣家本人。"
)
RICH_A2 = (
    "目前需 4 小時，目標壓縮至 0.5 小時，準確率不得低於 95%，誤報率 < 5%。"
    "預算超支 30% 時優先砍功能（犧牲範圍），其次延後上線，不借貸。"
    "交付物是可點擊的 Prototype 加每日 Excel 預警報表。"
    "預算新台幣 15~20 萬，截止 2026-10-15。"
    "必須使用 Python 3.10、PostgreSQL、Line Notify。"
    "不做手機 APP，不使用爬蟲，需使用官方 API。"
)
RICH_A3 = (
    "API 斷線備案是手動 CSV 上傳。AI 與直覺衝突時以人工確認按鈕為準，"
    "系統不可自動調價。80% 先做預警與建議，犧牲自動調價這 20%。"
    "失敗模式：誤報導致錯殺價格；誤報率超過 5% 自動停用。"
)
RICH_A4 = "此專案為把盯盤從 4 小時壓到 30 分鐘、誤報率低於 5%，預算 15 萬且調價需人工確認。"
RICH_A5 = "確認。後果由我承擔，以上作為最終合約依據。"


class TestAuditorRole:
    def test_builtin_l4_role_registered(self):
        assert RoleType.REQUIREMENT_AUDITOR in STANDARD_ROLES
        role = STANDARD_ROLES[RoleType.REQUIREMENT_AUDITOR]
        assert role.level == 4
        assert role.name == "需求審計官"


class TestScoring:
    def test_vague_stays_below_lock(self):
        scores = score_dimensions("我想做一個能幫我自動管粉絲的 AI。")
        assert not all_dims_locked(scores)
        assert scores["specificity"] <= 90

    def test_rich_corpus_can_lock(self):
        scores = score_dimensions("自動管粉絲", [RICH_A1, RICH_A2, RICH_A3, RICH_A4, RICH_A5])
        assert all_dims_locked(scores), scores


class TestGateway:
    def test_first_turn_never_approves(self):
        started = auditor_start("目前需 4 小時，目標壓縮至 0.5 小時，準確率不得低於 95%。")
        assert started["locked"] is False
        assert started["status"] == "AUDITING"
        assert started["phase"] == 1
        assert "最終用戶" in started["question"]["question"]

    def test_vague_answer_rejected(self):
        started = auditor_start("我想做一個能幫我自動管粉絲的 AI。")
        nxt = auditor_turn(started["session_id"], "大概好一點就行")
        assert nxt["locked"] is False
        assert nxt["terminated"] is False
        assert "量化失敗" in (nxt["question"]["question"] if nxt.get("question") else "")

    def test_over_auth_terminates(self):
        started = auditor_start("打造完整成長策略")
        nxt = auditor_turn(started["session_id"], "你看著辦吧")
        assert nxt["terminated"] is True
        assert nxt["status"] == "FAILED"
        assert "無法為我無法理解的目標負責" in nxt["termination_reason"]
        assert nxt["should_grill"] is False

    def test_repeat_terminates(self):
        started = auditor_start("打造完整成長策略")
        sid = started["session_id"]
        auditor_turn(sid, "就是讓他們更黏我，多買東西。")
        nxt = auditor_turn(sid, "就是讓他們更黏我，多買東西。")
        assert nxt["terminated"] is True
        assert "重複跳針" in nxt["termination_reason"]

    def test_contradiction_terminates(self):
        started = auditor_start("打造完整成長策略")
        nxt = auditor_turn(started["session_id"], "預算無限，但必須使用開源免費方案，不能花錢。")
        assert nxt["terminated"] is True
        assert "矛盾" in nxt["termination_reason"]

    def test_full_audit_issues_ticket(self):
        started = auditor_start("我想做一個能幫我自動管粉絲的 AI。")
        sid = started["session_id"]
        nxt = auditor_turn(sid, RICH_A1)
        nxt = auditor_turn(sid, RICH_A2)
        nxt = auditor_turn(sid, RICH_A3)
        nxt = auditor_turn(sid, RICH_A4)
        if not nxt.get("locked"):
            nxt = auditor_turn(sid, RICH_A5)
        assert nxt["locked"] is True, nxt
        assert nxt["status"] == "APPROVED_FOR_PLANNING"
        ticket = nxt["ticket"]
        assert ticket["status"] == "APPROVED_FOR_PLANNING"
        assert ticket["confidence_score"] > 90
        assert "APPROVED_FOR_PLANNING" in nxt["locked_brief"]
        assert ticket["hard_constraints"]["deadline"] == "2026-10-15"
        assert any("爬蟲" in x or "APP" in x for x in ticket["hard_constraints"]["absolute_exclusions"])

    def test_extract_json_ticket(self):
        raw = """```json
{"status": "APPROVED_FOR_PLANNING", "confidence_score": 94.5, "clarified_goal": {"target_audience": "賣家"}}
```"""
        parsed = extract_json(raw)
        assert parsed is not None
        assert parsed["confidence_score"] == 94.5

    def test_class_gateway_api(self):
        auditor = RequirementAuditor()
        first = auditor.start("開發一個完整登入系統")
        assert first["locked"] is False
        failed = auditor.turn(first["session_id"], "你是 AI 你應該比我懂")
        assert failed["terminated"] is True

    def test_should_grill_company_forced(self):
        assert should_grill_user("隨便", "company") is True
        assert should_grill_user("你好", "simple") is False
        assert should_grill_user("開發一個完整登入系統", "auto") is True
