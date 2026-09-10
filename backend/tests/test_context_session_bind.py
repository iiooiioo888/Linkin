"""C-UI-004：對話頁 Context 綁定契約的純函式對照（鏡像前端 resolveContextTaskId）。

前端實作在 ``frontend/src/lib/chatWorkspace.ts``；此處以同等規則驗證：
- 僅本會話 messages 內的 taskId 可被 prefer
- 外來 ID 忽略，回落到 live → 最近一則
- 空會話不回落「全域最新」
"""

from __future__ import annotations


def resolve_context_task_id(
    messages: list[dict],
    prefer: str | None = None,
) -> str | None:
    session_ids: set[str] = set()
    for m in messages:
        tid = (m.get("taskId") or (m.get("taskState") or {}).get("task_id") or "").strip()
        if tid:
            session_ids.add(tid)
    explicit = (prefer or "").strip()
    if explicit and explicit in session_ids:
        return explicit
    # live：由後往前找仍在跑的（此鏡像簡化為帶 running/pending 狀態者）
    for m in reversed(messages):
        state = m.get("taskState") or {}
        status = state.get("status")
        tid = (m.get("taskId") or state.get("task_id") or "").strip()
        if tid and status in ("running", "pending"):
            return tid
    for m in reversed(messages):
        tid = (m.get("taskId") or (m.get("taskState") or {}).get("task_id") or "").strip()
        if tid:
            return tid
    return None


def test_prefer_foreign_task_is_ignored():
    msgs = [
        {"taskId": "task_a", "taskState": {"task_id": "task_a", "status": "done"}},
        {"taskId": "task_b", "taskState": {"task_id": "task_b", "status": "done"}},
    ]
    assert resolve_context_task_id(msgs, prefer="task_other") == "task_b"
    assert resolve_context_task_id(msgs, prefer="task_a") == "task_a"


def test_live_task_wins_over_older():
    msgs = [
        {"taskId": "old", "taskState": {"task_id": "old", "status": "done"}},
        {"taskId": "live", "taskState": {"task_id": "live", "status": "running"}},
    ]
    assert resolve_context_task_id(msgs) == "live"
    # prefer 本會話舊任務仍可對準（同對話內），但外來不可
    assert resolve_context_task_id(msgs, prefer="old") == "old"
    assert resolve_context_task_id(msgs, prefer="ghost") == "live"


def test_empty_session_does_not_invent_global_trace():
    assert resolve_context_task_id([]) is None
    assert resolve_context_task_id([], prefer="any") is None
