"""敘事、席位目錄與現場寫入同一里程碑。"""

from __future__ import annotations

import pytest

from backend.company.milestone_actions import (
    absorb_analysis,
    commit_field_writes,
    commit_narrative_entity,
    resolve_assignee,
)
from backend.company.state import RoleType


@pytest.fixture()
def catalog(tmp_path, monkeypatch):
    monkeypatch.setenv("EVOL_ROLE_CATALOG_PATH", str(tmp_path / "roles.json"))
    monkeypatch.setenv("EVOL_LINKIN_DATA_DIR", str(tmp_path / "linkin"))
    from backend.company.role_catalog import reset_catalog_cache

    reset_catalog_cache()
    return tmp_path


def test_custom_seat_keeps_its_id(catalog):
    from backend.company.role_catalog import create_custom_role

    created = create_custom_role({"name": "現場紀錄", "id": "seat_field", "system_prompt": "記讀數"})
    assert resolve_assignee(created["id"]) == created["id"]
    assert resolve_assignee("not_a_role") == RoleType.DEVELOPER


def test_analysis_writes_existing_seat_and_holds_the_rest(catalog):
    from backend.company.role_catalog import get_snapshot

    plan = absorb_analysis(
        {"status": "pending_user"},
        {
            "seat_overrides": [{"role_id": "manager", "system_prompt": "先看現場讀數"}],
            "new_seats": [{"name": "現場紀錄", "system_prompt": "只記讀數", "tools_allowed": ["read"]}],
            "field_writes": [{"tag": "ns=2;s=FlowRate", "value": 10}],
            "constitution": {"world_name": "不該寫入"},
        },
    )
    assert get_snapshot("manager")["system_prompt"] == "先看現場讀數"
    assert plan["seat_overrides"][0]["applied"] is True
    assert plan["new_seats"][0]["name"] == "現場紀錄"
    assert plan["field_writes"][0]["tag"] == "ns=2;s=FlowRate"
    assert "constitution" not in plan


def test_reject_keeps_catalog_and_skips_new_seat(catalog):
    from backend.company.role_catalog import get_snapshot
    from backend.services.task_manager import TaskManager

    manager = TaskManager()
    manager._redis_failed = True
    record = manager.create_task("看現場", "company", "quick_task")
    record.status = "awaiting_confirmation"
    record.budget_plan = absorb_analysis(
        {"status": "pending_user", "ledger": {}, "lines": []},
        {
            "seat_overrides": [{"role_id": "manager", "system_prompt": "留在目錄"}],
            "new_seats": [{"name": "不該誕生", "id": "seat_nope"}],
        },
    )
    ok, message = manager.decide_budget(record.task_id, "reject")
    assert ok is True
    assert "不會執行" in message
    assert get_snapshot("manager")["system_prompt"] == "留在目錄"
    assert get_snapshot("custom_seat_nope") is None
    assert record.status == "rejected"


def test_approve_creates_seat_and_blocks_bad_field_write(catalog, monkeypatch):
    from backend.company.role_catalog import get_snapshot
    from backend.services.task_manager import TaskManager

    manager = TaskManager()
    manager._redis_failed = True
    started: list[str] = []
    monkeypatch.setattr(manager, "start_task", lambda rec: started.append(rec.task_id))
    record = manager.create_task("寫現場", "company", "quick_task")
    record.status = "awaiting_confirmation"
    record.budget_plan = {
        "status": "pending_user",
        "ledger": {},
        "lines": [],
        "new_seats": [{"name": "現場紀錄", "id": "seat_field", "system_prompt": "記讀數", "tools_allowed": ["read"]}],
        "field_writes": [
            {"tag": "ns=2;s=FlowRate", "value": 10},
            {"tag": "ns=2;s=Temperature", "value": 999},
        ],
    }
    ok, message = manager.decide_budget(record.task_id, "approve")
    assert ok is True
    assert started == [record.task_id]
    assert "現場寫入未執行" in message
    assert get_snapshot("custom_seat_field")["name"] == "現場紀錄"
    assert get_snapshot("custom_seat_field")["system_prompt"] == "記讀數"
    assert record.budget_plan["field_writes_result"]["status"] == "blocked"
    assert record.budget_plan["field_writes_result"]["written"] == []
    assert record.status == "pending"


def test_field_writes_are_all_or_nothing():
    blocked = commit_field_writes([
        {"tag": "ns=2;s=FlowRate", "value": 10},
        {"tag": "ns=2;s=Temperature", "value": 999},
    ])
    assert blocked["status"] == "blocked"
    assert blocked["written"] == []

    seen: list[dict] = []

    def _writer(rows):
        seen.extend(rows)
        return [{"tag_name": row["tag_name"], "status": "written"} for row in rows]

    accepted = commit_field_writes([{"tag": "ns=2;s=FlowRate", "value": 10}], writer=_writer)
    assert accepted["status"] == "accepted"
    assert seen[0]["tag_name"] == "ns=2;s=FlowRate"


def test_narrative_commit_rejects_world_and_stores_entity(catalog):
    with pytest.raises(ValueError, match="只讀"):
        commit_narrative_entity("constitution", {"name": "新世界"})
    stored = commit_narrative_entity("quest", {"name": "第一章"})
    assert stored["collection"] == "quests"
    assert stored["entity"]["name"] == "第一章"


def test_confirmation_draft_edits_new_seat_before_lock(catalog):
    from backend.services.task_manager import TaskManager

    manager = TaskManager()
    manager._redis_failed = True
    record = manager.create_task("草稿", "company", "quick_task")
    record.status = "awaiting_confirmation"
    record.budget_plan = {
        "status": "pending_user",
        "version": 1,
        "new_seats": [{"name": "舊名", "system_prompt": "舊"}],
        "field_writes": [],
    }
    ok, _message = manager.update_confirmation_draft(
        record.task_id,
        new_seats=[{"name": "新名", "system_prompt": "新提示"}],
    )
    assert ok is True
    assert record.budget_plan["new_seats"][0]["system_prompt"] == "新提示"
    assert "constitution" not in record.budget_plan
