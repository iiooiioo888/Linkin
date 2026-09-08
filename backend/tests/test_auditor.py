"""L4 需求審計官：五維鎖定、四階段追問、終止協議與戰術指令。"""

from __future__ import annotations

import pytest

from backend.company.raho.store import STORE
from backend.company.roles import STANDARD_ROLES
from backend.company.state import RoleType
from backend.services.auditor import (
    QUESTION_BANK,
    RequirementAuditor,
    all_dims_locked,
    auditor_start,
    auditor_turn,
    extract_json,
    score_dimensions,
    should_grill_user,
    trigger_planner,
)


@pytest.fixture(autouse=True)
def _reset_auditor(monkeypatch):
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_USER_GRILL", "true")
    monkeypatch.setattr("backend.services.auditor._llm_question", lambda *a, **k: None)
    STORE.user_sessions.clear()
    STORE.trees.clear()
    yield
    STORE.user_sessions.clear()
    STORE.trees.clear()


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
        assert RoleType.TACTICAL_COMMANDER in STANDARD_ROLES
        commander = STANDARD_ROLES[RoleType.TACTICAL_COMMANDER]
        assert commander.name == "戰術指揮官"
        assert commander.reporting_to == RoleType.REQUIREMENT_AUDITOR


SPEC_QUESTIONS = {
    1: "我們現在不談解決方案。請用『最終用戶』的視角，描述他完成任務前後那一刻的具體變化。",
    2: "現狀的痛點是什麼？如果用數字量化這個痛點，目前每個月損失多少錢 / 浪費多少小時？",
    3: "這個需求的發起人是誰？是終端使用者要的，還是你老闆覺得要的？這兩者的差異你怎麼處理？",
    4: "我不接受『提升效率』。請填入數字：『目前需 X 小時，目標壓縮至 Y 小時，且準確率不得低於 Z%』，請現在給出 X、Y、Z。",
    5: "若預算超支 30%，你是要砍功能（犧牲範圍），還是延後上線（犧牲時間），還是借貸補足（犧牲成本）？請排序。",
    6: "所謂的『完成』，具體會產出什麼格式的交付物？是 Excel 報表、可點擊的 Prototype，還是一份純文字的備忘錄？",
    7: "假設這個方案做出來，但關鍵數據源（如 API）突然斷了，你的備案是什麼？如果沒有備案，我將標記此需求為高風險。",
    8: "你提到希望系統『智慧』一點，但同時又要求『絕對可控』。這兩者是互斥的，當 AI 的判斷與你的直覺衝突時，你聽誰的？具體情境下如何取捨？",
    9: "如果只能做到現在所提需求的 80%，剩下的 20% 你願意犧牲哪一部分？請具體指出這 20% 的內容。",
    10: "為了避免誤會，請用你自己的話（不許複製貼上）重新定義一次『成功』，字數不得超過 50 字。",
    11: "如果我現在交付了你說的 A 功能，但你實際想要的是 B 感覺，後果由誰承擔？你現在確定要將剛才的所有回答作為最終合約依據嗎？",
}


class TestScoring:
    def test_vague_stays_below_lock(self):
        scores = score_dimensions("我想做一個能幫我自動管粉絲的 AI。")
        assert not all_dims_locked(scores)
        assert scores["specificity"] <= 90

    def test_rich_corpus_can_lock(self):
        scores = score_dimensions("自動管粉絲", [RICH_A1, RICH_A2, RICH_A3, RICH_A4, RICH_A5])
        assert all_dims_locked(scores), scores

    def test_question_bank_matches_spec_verbatim(self):
        by_id = {item["id"]: item["question"] for item in QUESTION_BANK}
        for qid, text in SPEC_QUESTIONS.items():
            assert by_id[qid] == text
        assert len(QUESTION_BANK) == 16


class TestGateway:
    def test_first_turn_never_approves(self):
        started = auditor_start("目前需 4 小時，目標壓縮至 0.5 小時，準確率不得低於 95%。")
        assert started["locked"] is False
        assert started["status"] == "AUDITING"
        assert started["phase"] == 1
        assert "最終用戶" in started["question"]["question"]
        assert "Phase 1" in started["question"]["question"]
        assert "收到需求" in started["question"]["question"]

    def test_opening_rejects_vague_verb(self):
        started = auditor_start("我想做一個能幫我自動管粉絲的 AI。")
        question = started["question"]["question"]
        assert "管粉" in question
        assert "最終用戶" in question
        assert started["role"] == "requirement_auditor"
        assert "介入前" in question
        assert "介入後" in question
        assert "Phase 1" in question
        tree = STORE.get_tree(STORE.user_grill_run_id(started["session_id"]))
        assert tree is not None
        assert tree.nodes
        assert tree.nodes[0].kind == "user_grill"
        assert tree.nodes[0].from_layer == 4

    def test_role_uses_gateway_system_prompt(self):
        from backend.services.auditor import SYSTEM_PROMPT

        role = STANDARD_ROLES[RoleType.REQUIREMENT_AUDITOR]
        assert role.system_prompt == SYSTEM_PROMPT
        assert "禁止確認偏誤" in role.system_prompt
        assert "APPROVED_FOR_PLANNING" in role.system_prompt

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

    def test_process_user_request_terminates_over_auth(self):
        auditor = RequirementAuditor()
        gen = auditor.process_user_request("打造完整成長策略")
        first = next(gen)
        assert first["status"] == "AUDITING"
        assert first["question"]["question"]
        try:
            gen.send("你看著辦吧")
            raise AssertionError("產生器應以終止協議結束")
        except StopIteration as stop:
            failed = stop.value
        assert failed["terminated"] is True
        assert failed["status"] == "FAILED"
        assert "無法為我無法理解的目標負責" in failed["termination_reason"]

    def test_process_user_request_issues_ticket(self):
        auditor = RequirementAuditor()
        gen = auditor.process_user_request("我想做一個能幫我自動管粉絲的 AI。")
        next(gen)
        result = None
        for reply in (RICH_A1, RICH_A2, RICH_A3, RICH_A4, RICH_A5):
            try:
                result = gen.send(reply)
            except StopIteration as stop:
                result = stop.value
                break
        assert result is not None
        assert result["locked"] is True
        assert result["status"] == "APPROVED_FOR_PLANNING"
        assert result["ticket"]["status"] == "APPROVED_FOR_PLANNING"
        assert result["planner"]["status"] == "PLANNER_TRIGGERED"

    def test_spec_example_fan_dialogue(self):
        started = auditor_start("我想做一個能幫我自動管粉絲的 AI。")
        q1 = started["question"]["question"]
        assert "管粉" in q1
        assert "介入前" in q1
        sid = started["session_id"]

        p2 = auditor_turn(sid, "就是讓他們更黏我，多買東西。")
        q2 = (p2.get("question") or {}).get("question") or ""
        assert p2["terminated"] is False
        assert p2["phase"] == 2
        assert "量化失敗" in q2
        assert "復購率" in q2
        assert "行銷成本" in q2

        p3 = auditor_turn(sid, "大概從 15% 提升到 25% 吧，成本的話大概 50 塊。")
        q3 = (p3.get("question") or {}).get("question") or ""
        assert p3["phase"] == 3
        assert "退粉" in q3
        assert "人工審核" in q3

        p4 = auditor_turn(sid, "那還是先人工審核好了。")
        q4 = (p4.get("question") or {}).get("question") or ""
        if not p4.get("locked"):
            assert p4["phase"] == 4
            assert "50 字" in q4 or "復購率" in q4
            locked = auditor_turn(sid, "確認。")
        else:
            locked = p4
        assert locked["locked"] is True
        assert locked["status"] == "APPROVED_FOR_PLANNING"
        assert locked["ticket"]["status"] == "APPROVED_FOR_PLANNING"
        assert locked["ticket"]["confidence_score"] > 90
        assert "25" in str(locked["ticket"]["clarified_goal"]["quantified_success"])
        assert "50" in str(locked["ticket"]["hard_constraints"]["budget_range"])
        assert any("人工" in x for x in locked["ticket"]["hard_constraints"]["absolute_exclusions"])
        assert locked["planner"]["status"] == "PLANNER_TRIGGERED"

    def test_trigger_planner_rejects_low_score(self):
        rejected = trigger_planner({"status": "APPROVED_FOR_PLANNING", "confidence_score": 70})
        assert rejected["status"] == "REJECTED"

    def test_auditor_http_and_sse(self):
        from fastapi.testclient import TestClient

        from backend.main import app

        with TestClient(app) as client:
            started = client.post("/auditor/start", json={"query": "開發一個完整登入系統"})
            assert started.status_code == 200
            body = started.json()
            assert body["status"] == "AUDITING"
            assert body["role"] == "requirement_auditor"
            sid = body["session_id"]
            failed = client.post(
                "/auditor/turn",
                json={"session_id": sid, "answer": "你是 AI 你應該比我懂"},
            )
            assert failed.json()["terminated"] is True
            status = client.get("/auditor/status")
            assert status.json()["role"] == "requirement_auditor"
            stream = client.post("/auditor/stream", json={"query": "打造完整成長策略"})
            assert stream.status_code == 200
            assert "event: question" in stream.text
            assert "event: done" in stream.text
