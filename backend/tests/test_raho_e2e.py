"""RAHO 黃金三角 E2E：L5 門票 → L4 審計 JSON → L3 作戰手冊 → L2 戰前檢查 → L1 簽核。"""

from __future__ import annotations

import pytest

from backend.company.raho.atomic_executor import (
    BLOCKER_INPUT,
    AtomicExecutorFactory,
    has_constitution,
    run_preflight,
)
from backend.company.raho.blackboard import result_uri
from backend.company.raho.commander import command_from_ticket
from backend.company.raho.inspector import (
    GRILL_TARGET_L3,
    TEST_FACTUAL,
    VERDICT_APPROVED,
    VERDICT_ESCALATE,
    InspectorGate,
    read_signed_memory,
)
from backend.company.raho.store import STORE
from backend.services.commander import STATUS_PLAN_READY


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("EVOL_RAHO_ENABLED", "true")
    monkeypatch.setenv("EVOL_RAHO_COMMANDER_LLM", "false")
    monkeypatch.setenv("EVOL_RAHO_L1_LLM", "false")
    STORE.user_sessions.clear()
    STORE.battle_plans.clear()
    STORE.shared_memory.clear()
    yield
    STORE.user_sessions.clear()
    STORE.battle_plans.clear()
    STORE.shared_memory.clear()


TICKET = {
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


def _first_instance(pack: dict) -> dict:
    plan = pack["battle_plan"]
    instances = plan["atomic_role_instances"]
    assert instances
    return instances[0]


class TestRahoChain:
    def test_l4_ticket_to_l3_plan_to_l2_constitution(self):
        pack = command_from_ticket(TICKET, use_llm=False)
        assert pack["status"] == STATUS_PLAN_READY
        instance = _first_instance(pack)
        prompt = AtomicExecutorFactory.spawn(instance)
        assert has_constitution(prompt)
        assert instance.get("input_ref")
        assert instance.get("output_schema")
        assert instance.get("allowed_tools") is not None

    def test_l2_grills_empty_input_then_l1_blocks_unsigned(self):
        defective = {
            "task_description": "分析 sales.csv 中的營收趨勢",
            "input_ref": None,
            "allowed_tools": ["csv_reader", "trend_analyzer"],
            "success_criteria": "產出至少 3 個可驗證趨勢點",
            "output_schema": "Plain Text",
            "max_iterations": 2,
            "token_budget": 2000,
        }
        grills = run_preflight(defective)
        assert grills
        assert grills[0].blocker_type == BLOCKER_INPUT
        assert grills[0].suggested_fix

        gate = InspectorGate()
        verdict = gate.inspect(
            defective,
            "上個月營收成長 20%",
            source_data="",
            node_id="e2e-halluc",
        )
        assert verdict.verdict == VERDICT_ESCALATE
        assert verdict.grill is not None
        assert verdict.grill.target == GRILL_TARGET_L3
        assert verdict.grill.failed_test == TEST_FACTUAL
        assert read_signed_memory("e2e-halluc") is None

    def test_l2_output_approved_writes_blackboard(self):
        pack = command_from_ticket(TICKET, use_llm=False)
        instance = _first_instance(pack)
        instance["output_schema"] = "Plain Text"
        instance["task_description"] = "摘錄競品價格"
        output = "競品價格 149 美元"
        gate = InspectorGate()
        node_id = str(instance.get("node_id") or "N1")
        verdict = gate.inspect(
            instance,
            output,
            source_data="競品價格 149 美元",
            node_id=node_id,
            title=str(instance.get("name") or "原子"),
        )
        assert verdict.verdict == VERDICT_APPROVED
        record = read_signed_memory(node_id)
        assert record is not None
        assert record["signed"] is True
        assert record["uri"] == result_uri(node_id)
        assert record["data"] == output
        assert record["verdict"] == VERDICT_APPROVED
