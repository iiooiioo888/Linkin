"""角色工作項彙整：看板／spine／即時任務與 run log ingest。"""

from __future__ import annotations

import json
from typing import Any

from backend.company.raho.protocol import canonical_role_id, role_to_raho_layer
from backend.company.state import WorkItemStatus
from backend.services.task_manager import TaskRecord

from .common import (
    MAX_RUN_FILES,
    OPEN_STATUSES,
    _now_iso,
    _role_id,
    _run_log_dir,
    _status_key,
)
from .events import _append_event, _event_name, _event_payload, _roles_for_event


def _item_key(item_id: Any, task_id: Any) -> tuple[str, str]:
    return (str(item_id or ""), str(task_id or ""))


def _upsert_item(bucket: dict[str, Any], item: dict[str, Any]) -> None:
    seen: dict[tuple[str, str], int] = {
        _item_key(existing.get("id"), existing.get("task_id")): idx
        for idx, existing in enumerate(bucket["work_items"])
    }
    key = _item_key(item.get("id"), item.get("task_id"))
    if key in seen and key != ("", ""):
        current = bucket["work_items"][seen[key]]
        # 即時看板優先於歷史 run log
        if item.get("source") == "live" or current.get("source") != "live":
            bucket["work_items"][seen[key]] = {**current, **item}
        return
    bucket["work_items"].append(item)


def _from_kanban_item(
    status: str,
    item: dict[str, Any],
    task: TaskRecord,
    kind: str,
) -> dict[str, Any]:
    updated = item.get("updated_at") or item.get("created_at")
    depends = item.get("depends_on") or []
    if not isinstance(depends, list):
        depends = []
    feedback = item.get("feedback") or []
    if not isinstance(feedback, list):
        feedback = []
    return {
        "id": item.get("id") or "",
        "title": item.get("title") or "(未命名工作項)",
        "description": (item.get("description") or "")[:240],
        "status": status,
        "kind": kind,
        "assignee": _role_id(item.get("assignee")),
        "task_id": task.task_id,
        "task_query": task.query,
        "task_status": task.status,
        "phase": task.phase,
        "cost_usd": float(item.get("actual_cost") or item.get("cost") or 0),
        "estimated_cost": float(item.get("estimated_cost") or 0),
        "output_preview": str(item.get("output") or "")[:280],
        "updated_at": updated,
        "source": "live",
        "depends_on": [str(d) for d in depends],
        "tier": str(item.get("tier") or ""),
        "feedback": feedback[-3:],
    }


def _mirror_spine_item(
    agents: dict[str, dict[str, Any]],
    assignee: str,
    row: dict[str, Any],
    *,
    live_running: bool = False,
    task_id: str = "",
) -> None:
    """把專職角色的工作項鏡像到 RAHO 脊柱席（L2 池／L1 憲兵），與質詢樹同一套身分。"""
    try:
        spine = canonical_role_id(role_to_raho_layer(assignee))
    except Exception:
        return
    if not spine or spine == assignee or spine not in agents:
        return
    mirrored = {**row, "kind": f"spine:{row.get('kind') or 'assigned'}"}
    _upsert_item(agents[spine], mirrored)
    tid = task_id or str(row.get("task_id") or "")
    if live_running and tid and tid not in agents[spine]["active_task_ids"]:
        agents[spine]["active_task_ids"].append(tid)


def _ingest_live_task(agents: dict[str, dict[str, Any]], task: TaskRecord) -> None:
    if task.resolved_path and task.resolved_path != "company":
        return
    if task.resolved_path != "company" and not task.kanban and not any(
        _event_name(_event_payload(e)).startswith(("company_", "work_item_", "decompose", "review_", "synthesize"))
        for e in task.events
    ):
        return

    live_running = task.status in {"running", "pending"}
    kanban = task.kanban or {}

    def _effective_item_status(raw: str) -> str:
        status = _status_key(raw)
        if live_running:
            return status
        if task.status == "completed":
            if status in OPEN_STATUSES:
                return WorkItemStatus.DONE.value
            return status
        if task.status in {"cancelled", "interrupted"}:
            if status in OPEN_STATUSES:
                return WorkItemStatus.CANCELLED.value
            return status
        if task.status == "failed" and status in OPEN_STATUSES:
            return WorkItemStatus.BLOCKED.value
        return status

    for raw_status, items in kanban.items():
        status = _effective_item_status(raw_status)
        for item in items or []:
            if not isinstance(item, dict):
                continue
            assignee = _role_id(item.get("assignee")) or "developer"
            if assignee in agents:
                row = _from_kanban_item(status, item, task, "assigned")
                _upsert_item(agents[assignee], row)
                if task.task_id not in agents[assignee]["active_task_ids"] and live_running:
                    agents[assignee]["active_task_ids"].append(task.task_id)
                _mirror_spine_item(agents, assignee, row, live_running=live_running, task_id=task.task_id)
            if status == WorkItemStatus.IN_REVIEW.value:
                review_row = _from_kanban_item(status, item, task, "review")
                if "reviewer" in agents:
                    _upsert_item(agents["reviewer"], review_row)
                    if live_running and task.task_id not in agents["reviewer"]["active_task_ids"]:
                        agents["reviewer"]["active_task_ids"].append(task.task_id)
                if "constitutional_inspector" in agents:
                    _upsert_item(agents["constitutional_inspector"], review_row)
                    if live_running and task.task_id not in agents["constitutional_inspector"]["active_task_ids"]:
                        agents["constitutional_inspector"]["active_task_ids"].append(task.task_id)

    phase = task.phase or ""
    if "manager" in agents:
        if live_running and phase in {"decompose", "final_review"}:
            title = "分解目標" if phase == "decompose" else "最終審查"
            _upsert_item(
                agents["manager"],
                {
                    "id": f"{task.task_id}:{phase}",
                    "title": f"{title}：{task.query[:80]}",
                    "description": task.query[:240],
                    "status": WorkItemStatus.EXECUTING.value,
                    "kind": "coordinate",
                    "assignee": "manager",
                    "task_id": task.task_id,
                    "task_query": task.query,
                    "task_status": task.status,
                    "phase": phase,
                    "cost_usd": 0.0,
                    "output_preview": "",
                    "updated_at": _now_iso(),
                    "source": "live",
                },
            )
            if task.task_id not in agents["manager"]["active_task_ids"]:
                agents["manager"]["active_task_ids"].append(task.task_id)
        elif not live_running and task.plan:
            _upsert_item(
                agents["manager"],
                {
                    "id": f"{task.task_id}:decompose",
                    "title": f"分解完成：{task.query[:80]}",
                    "description": f"子任務 {task.plan.get('subtask_count', '?')} · 策略 {task.plan.get('strategy', 'auto')}",
                    "status": WorkItemStatus.DONE.value,
                    "kind": "coordinate",
                    "assignee": "manager",
                    "task_id": task.task_id,
                    "task_query": task.query,
                    "task_status": task.status,
                    "phase": "decompose",
                    "cost_usd": 0.0,
                    "output_preview": "",
                    "updated_at": None,
                    "source": "live",
                },
            )
        if task.review:
            approved = bool(task.review.get("approved", True))
            _upsert_item(
                agents["manager"],
                {
                    "id": f"{task.task_id}:final_review",
                    "title": f"最終審查：{task.query[:80]}",
                    "description": str(task.review.get("feedback") or task.review.get("strengths") or "")[:240],
                    "status": WorkItemStatus.DONE.value if approved else WorkItemStatus.REWORK.value,
                    "kind": "coordinate",
                    "assignee": "manager",
                    "task_id": task.task_id,
                    "task_query": task.query,
                    "task_status": task.status,
                    "phase": "final_review",
                    "cost_usd": 0.0,
                    "output_preview": str(task.review.get("score") or ""),
                    "updated_at": None,
                    "source": "live",
                },
            )

    if "synthesizer" in agents and (phase == "synthesize" or task.status == "completed"):
        synth_status = (
            WorkItemStatus.EXECUTING.value
            if live_running and phase == "synthesize"
            else WorkItemStatus.DONE.value
            if task.status == "completed"
            else None
        )
        if synth_status:
            _upsert_item(
                agents["synthesizer"],
                {
                    "id": f"{task.task_id}:synthesize",
                    "title": f"整合交付：{task.query[:80]}",
                    "description": (task.answer or "")[:240],
                    "status": synth_status,
                    "kind": "synthesize",
                    "assignee": "synthesizer",
                    "task_id": task.task_id,
                    "task_query": task.query,
                    "task_status": task.status,
                    "phase": "synthesize",
                    "cost_usd": 0.0,
                    "output_preview": (task.answer or "")[:280],
                    "updated_at": None,
                    "source": "live",
                },
            )
            if live_running and task.task_id not in agents["synthesizer"]["active_task_ids"]:
                agents["synthesizer"]["active_task_ids"].append(task.task_id)

    for event in task.events:
        payload = _event_payload(event)
        if not _event_name(payload):
            continue
        for role in _roles_for_event(payload):
            if role in agents:
                _append_event(agents[role], payload, task)


_TERMINAL_TASK_STATUSES = frozenset({"completed", "failed", "cancelled", "interrupted"})


def _coerce_terminal_task_work_items(agents: dict[str, dict[str, Any]], task: TaskRecord) -> None:
    """終態任務：清掉 live 工作項上的 executing／審查中等殘值。"""
    if task.status not in _TERMINAL_TASK_STATUSES:
        return
    if task.status == "completed":
        target = WorkItemStatus.DONE.value
    elif task.status == "failed":
        target = WorkItemStatus.BLOCKED.value
    else:
        target = WorkItemStatus.CANCELLED.value
    tid = task.task_id
    for agent in agents.values():
        active_ids = agent.get("active_task_ids") or []
        if tid in active_ids:
            agent["active_task_ids"] = [x for x in active_ids if x != tid]
        for item in agent.get("work_items") or []:
            if item.get("task_id") != tid or item.get("source") != "live":
                continue
            st = _status_key(item.get("status"))
            if st in OPEN_STATUSES:
                item["status"] = target
                item["task_status"] = task.status
                item["updated_at"] = _now_iso()


def _ingest_run_logs(agents: dict[str, dict[str, Any]]) -> None:
    directory = _run_log_dir()
    try:
        files = sorted(directory.glob("run_*.jsonl"), reverse=True)[:MAX_RUN_FILES]
    except OSError:
        return

    live_item_ids = {
        (item.get("id"), item.get("task_id"))
        for agent in agents.values()
        for item in agent["work_items"]
        if item.get("source") == "live"
    }

    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        run_id = path.stem.replace("run_", "", 1)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            payload = _event_payload(record)
            name = _event_name(payload)
            if not name:
                continue
            for role in _roles_for_event(payload):
                if role in agents:
                    _append_event(agents[role], payload)

            if name not in {"work_item_start", "work_item_done", "work_item_error", "execute_done"}:
                continue
            assignee = _role_id(payload.get("assignee")) or "developer"
            if assignee not in agents:
                continue
            item_id = str(payload.get("item_id") or "")
            task_id = str(payload.get("run_id") or run_id)
            if (item_id, task_id) in live_item_ids:
                continue
            if name in {"work_item_done", "execute_done"}:
                status = WorkItemStatus.DONE.value
            elif name == "work_item_error":
                status = WorkItemStatus.BLOCKED.value
            else:
                status = WorkItemStatus.EXECUTING.value
            hist: dict[str, Any] = {
                "id": item_id or f"{task_id}:{payload.get('title', '')}",
                "title": payload.get("title") or "(歷史工作項)",
                "description": "",
                "status": status,
                "kind": "assigned",
                "assignee": assignee,
                "task_id": task_id,
                "task_query": payload.get("goal") or "",
                "task_status": "completed" if status == WorkItemStatus.DONE.value else "unknown",
                "phase": "",
                "cost_usd": float(payload.get("cost") or payload.get("cost_usd") or 0),
                "estimated_cost": 0.0,
                "output_preview": "",
                "updated_at": payload.get("ts") or payload.get("timestamp"),
                "source": "run_log",
                "depends_on": [],
                "tier": "",
                "feedback": [],
            }
            _upsert_item(agents[assignee], hist)
            _mirror_spine_item(agents, assignee, hist)
