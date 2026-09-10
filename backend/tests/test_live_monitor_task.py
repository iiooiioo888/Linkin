"""C-UI：右側監控欄 eligibility 契約（鏡像前端 ``isLiveMonitorTask`` / ``activeTaskMessage``）。

前端實作在 ``frontend/src/lib/chatWorkspace.ts``；此處以同等規則驗證：
- running / pending → 分裂
- completed / failed / cancelled → 不收欄
- Grill 未鎖、Battle 等待裁決、RAHO 待決 → 仍分裂
- 僅 taskId 且終態 → 不收欄（除非仍互動中）
"""

from __future__ import annotations


TERMINAL = frozenset({"completed", "failed", "cancelled", "interrupted"})


def _has_unresolved_decision(message: dict) -> bool:
    pending = (message.get("taskState") or {}).get("raho", {}).get("pending_decisions") or []
    return any(not p.get("resolved") and (p.get("choices") or []) for p in pending)


def _is_grill_interactive(message: dict) -> bool:
    g = message.get("grill") or {}
    return bool(g and not g.get("locked") and not g.get("terminated"))


def _is_battle_waiting(message: dict) -> bool:
    b = message.get("battle") or {}
    return b.get("status") == "ESCALATE_TO_USER" and bool(b.get("waiting_for_user_decision"))


def is_live_monitor_task(message: dict) -> bool:
    if _is_grill_interactive(message) or _is_battle_waiting(message):
        return True
    if _has_unresolved_decision(message):
        return True

    task = message.get("taskState") or {}
    status = task.get("status")
    if task:
        if status in ("running", "pending"):
            return True
        if status in TERMINAL:
            return False

    task_id = (message.get("taskId") or task.get("task_id") or "").strip()
    if task_id and not task:
        return bool(message.get("streaming"))

    return False


def active_task_message(messages: list[dict]) -> dict | None:
    for m in reversed(messages):
        if is_live_monitor_task(m):
            return m
    return None


def _msg(**kwargs) -> dict:
    return kwargs


def test_running_task_opens_split():
    m = _msg(
        taskId="t1",
        taskState={
            "task_id": "t1",
            "status": "running",
            "resolved_path": "company",
            "kanban": {"executing": [{"id": "n1", "title": "步驟"}]},
        },
    )
    assert is_live_monitor_task(m) is True
    assert active_task_message([m]) == m


def test_completed_task_closes_split():
    m = _msg(
        taskId="t1",
        taskState={
            "task_id": "t1",
            "status": "completed",
            "resolved_path": "company",
            "kanban": {"done": [{"id": "n1", "title": "步驟"}]},
        },
    )
    assert is_live_monitor_task(m) is False
    assert active_task_message([m]) is None


def test_pending_task_still_splits():
    m = _msg(taskId="t1", taskState={"task_id": "t1", "status": "pending", "resolved_path": "opc"})
    assert is_live_monitor_task(m) is True


def test_task_id_only_terminal_no_split():
    m = _msg(taskId="t-done", streaming=False)
    assert is_live_monitor_task(m) is False


def test_task_id_only_streaming_splits_while_hydrating():
    m = _msg(taskId="t-new", streaming=True)
    assert is_live_monitor_task(m) is True


def test_grill_waiting_splits_without_task():
    m = _msg(
        grill={"session_id": "g1", "locked": False, "terminated": False, "confidence": 0.5},
    )
    assert is_live_monitor_task(m) is True
    assert active_task_message([m]) == m


def test_grill_locked_does_not_split():
    m = _msg(grill={"session_id": "g1", "locked": True, "terminated": False, "confidence": 0.9})
    assert is_live_monitor_task(m) is False


def test_battle_waiting_splits():
    m = _msg(
        battle={"status": "ESCALATE_TO_USER", "waiting_for_user_decision": True},
    )
    assert is_live_monitor_task(m) is True


def test_pending_decision_on_completed_task_still_splits():
    m = _msg(
        taskId="t1",
        taskState={
            "task_id": "t1",
            "status": "completed",
            "raho": {
                "pending_decisions": [
                    {
                        "decision_id": "d1",
                        "question": "選哪個？",
                        "choices": [{"key": "a", "label": "A"}],
                        "resolved": False,
                    }
                ]
            },
        },
    )
    assert is_live_monitor_task(m) is True


def test_chitchat_never_splits():
    m = _msg(role="assistant", content="你好！")
    assert is_live_monitor_task(m) is False


def test_newer_chitchat_after_completed_closes_split():
    completed = _msg(
        taskId="old",
        taskState={"task_id": "old", "status": "completed", "resolved_path": "company"},
    )
    chitchat = _msg(content="謝謝")
    assert active_task_message([completed, chitchat]) is None


def test_newer_running_wins_over_older_completed():
    completed = _msg(
        taskId="old",
        taskState={"task_id": "old", "status": "completed", "resolved_path": "company"},
    )
    running = _msg(
        taskId="live",
        taskState={"task_id": "live", "status": "running", "resolved_path": "company"},
    )
    assert active_task_message([completed, running]) == running
