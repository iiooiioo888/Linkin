"""角色 Agent 監控聚合：每位公司角色一張獨立工作台。

資料來源（唯讀、降級安全）：
- role_catalog：內建角色 + 自定義角色 + 設定覆蓋
- task_manager：即時公司任務看板與事件
- company_runs JSONL：歷史工作項與角色事件

每位角色視為一個 Agent：inbox 計數、指派任務列表、審查隊列、
事件時間軸。Manager / Reviewer / Synthesizer 除看板指派外，
另納入分解 / 審查 / 整合等協調型工作。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.company.raho.protocol import raho_directory, canonical_role_id, role_to_raho_layer
from backend.company.role_catalog import (
    LEVEL_LABELS,
    catalog_meta,
    get_monitor_prefs,
    list_role_snapshots,
)
from backend.company.run_log import DEFAULT_RUN_LOG_DIR
from backend.company.state import WorkItemStatus
from backend.services.task_manager import TaskRecord, task_manager

logger = logging.getLogger(__name__)

MAX_RUN_FILES = 40
MAX_ITEMS_PER_ROLE = 80
MAX_EVENTS_PER_ROLE = 60

OPEN_STATUSES = frozenset(
    {
        WorkItemStatus.PLANNING.value,
        WorkItemStatus.READY.value,
        WorkItemStatus.EXECUTING.value,
        WorkItemStatus.IN_REVIEW.value,
        WorkItemStatus.REWORK.value,
        WorkItemStatus.BLOCKED.value,
    }
)

ROLE_EVENT_HINTS: dict[str, frozenset[str]] = {
    "manager": frozenset(
        {
            "company_start",
            "decompose_done",
            "final_review_done",
            "company_done",
            "budget_warning",
            "budget_degrade",
            "grill_raised",
            "grill_resolved",
            "user_decision_needed",
            "raho_timeout",
        }
    ),
    "reviewer": frozenset(
        {"review_pass", "review_rework", "review_force_done", "review_approved"}
    ),
    "synthesizer": frozenset({"synthesize_done"}),
    "hub_operator": frozenset({"budget_warning", "budget_degrade", "tool_call"}),
    "github_ops": frozenset({"tool_call", "tool_result"}),
    "requirement_auditor": frozenset({"user_grill", "auditor_start", "auditor_lock", "auditor_fail"}),
    "tactical_commander": frozenset(
        {"decompose_done", "grill_raised", "grill_resolved", "user_decision_needed", "raho_timeout"}
    ),
    "constitutional_inspector": frozenset(
        {"review_pass", "review_rework", "review_force_done", "review_approved", "inspect"}
    ),
    "atomic_executor": frozenset(
        {"work_item_retry", "work_item_escalate", "execute_done", "grill_raised"}
    ),
}

PHASE_ROLE: dict[str, str] = {
    "decompose": "manager",
    "final_review": "manager",
    "synthesize": "synthesizer",
}


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(0.95 * (len(ordered) - 1)))))
    return round(ordered[idx], 1)


def _run_log_dir() -> Path:
    return Path(os.getenv("EVOL_COMPANY_RUN_LOG_DIR", str(DEFAULT_RUN_LOG_DIR)))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _status_key(raw: Any) -> str:
    if hasattr(raw, "value"):
        return str(raw.value)
    text = str(raw or "").strip()
    return text or WorkItemStatus.PLANNING.value


def _role_id(raw: Any) -> str | None:
    if raw is None:
        return None
    if hasattr(raw, "value"):
        return str(raw.value)
    text = str(raw).strip()
    return text or None


def _empty_inbox() -> dict[str, int]:
    return {s.value: 0 for s in WorkItemStatus}


def _blank_agent(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": snapshot["id"],
        "name": snapshot["name"],
        "level": snapshot["level"],
        "level_label": snapshot["level_label"],
        "raho_layer": snapshot.get("raho_layer"),
        "raho_label": snapshot.get("raho_label") or "",
        "raho_short": snapshot.get("raho_short") or "",
        "raho_title": snapshot.get("raho_title") or "",
        "raho_spine": bool(snapshot.get("raho_spine")),
        "grill_targets": list(snapshot.get("grill_targets") or []),
        "category": snapshot["category"],
        "reporting_to": snapshot.get("reporting_to"),
        "can_delegate_to": list(snapshot.get("can_delegate_to") or []),
        "direct_reports": list(snapshot.get("direct_reports") or []),
        "responsibilities": list(snapshot.get("responsibilities") or []),
        "system_prompt": snapshot.get("system_prompt") or "",
        "max_parallel_work": int(snapshot.get("max_parallel_work") or 2),
        "default_tier": snapshot.get("default_tier") or "routine",
        "preferred_model": snapshot.get("preferred_model") or "",
        "preferred_provider": snapshot.get("preferred_provider") or "",
        "daily_budget_usd": float(snapshot.get("daily_budget_usd") or 0),
        "weekly_budget_usd": float(snapshot.get("weekly_budget_usd") or 0),
        "monthly_budget_usd": float(snapshot.get("monthly_budget_usd") or 0),
        "cloud_daily_budget_usd": float(snapshot.get("cloud_daily_budget_usd") or 0),
        "cloud_weekly_budget_usd": float(snapshot.get("cloud_weekly_budget_usd") or 0),
        "cloud_monthly_budget_usd": float(snapshot.get("cloud_monthly_budget_usd") or 0),
        "tools_allowed": list(snapshot.get("tools_allowed") or []),
        "notes": snapshot.get("notes") or "",
        "enabled": bool(snapshot.get("enabled", True)),
        "is_custom": bool(snapshot.get("is_custom", False)),
        "is_builtin": bool(snapshot.get("is_builtin", True)),
        "alert_on_error": bool(snapshot.get("alert_on_error", True)),
        "alert_on_budget": bool(snapshot.get("alert_on_budget", True)),
        "alert_on_sla": bool(snapshot.get("alert_on_sla", True)),
        "temperature": float(snapshot.get("temperature") or 0.7),
        "max_output_tokens": int(snapshot.get("max_output_tokens") or 4096),
        "timeout_ms": int(snapshot.get("timeout_ms") or 120000),
        "routing_strategy": snapshot.get("routing_strategy") or "quality_first",
        "failover_models": list(snapshot.get("failover_models") or []),
        "sla_latency_ms": int(snapshot.get("sla_latency_ms") or 0),
        "max_retries": int(snapshot.get("max_retries") or 3),
        "language": snapshot.get("language") or "zh-TW",
        "always_require_review": bool(snapshot.get("always_require_review", False)),
        "priority": int(snapshot.get("priority") or 3),
        "description": snapshot.get("description") or "",
        "max_daily_items": int(snapshot.get("max_daily_items") or 0),
        "require_human_approval": bool(snapshot.get("require_human_approval", False)),
        "stream_enabled": bool(snapshot.get("stream_enabled", True)),
        "cache_enabled": bool(snapshot.get("cache_enabled", True)),
        "pii_redact": bool(snapshot.get("pii_redact", True)),
        "mainland_only": bool(snapshot.get("mainland_only", False)),
        "heartbeat_sec": int(snapshot.get("heartbeat_sec") or 0),
        "on_call": bool(snapshot.get("on_call", False)),
        "tags": list(snapshot.get("tags") or []),
        "notify_channel": snapshot.get("notify_channel") or "",
        "quiet_hours": snapshot.get("quiet_hours") or "",
        "context_window": int(snapshot.get("context_window") or 0),
        "allow_tool_use": bool(snapshot.get("allow_tool_use", True)),
        "auto_escalate": bool(snapshot.get("auto_escalate", True)),
        "templates": list(snapshot.get("templates") or []),
        "status": "idle" if snapshot.get("enabled", True) else "disabled",
        "inbox": _empty_inbox(),
        "queue": 0,
        "executing": 0,
        "done": 0,
        "blocked": 0,
        "cost_usd": 0.0,
        "api_cost_usd": 0.0,
        "cloud_cost_usd": 0.0,
        "docker_cost_usd": 0.0,
        "aliyun_cost_usd": 0.0,
        "last_activity_at": None,
        "work_items": [],
        "events": [],
        "active_task_ids": [],
        "current_item": None,
        "company_tasks": [],
        "capacity_used": 0,
        "metrics": {
            "review_pass": 0,
            "review_rework": 0,
            "review_force": 0,
            "errors": 0,
            "tool_calls": 0,
            "budget_alerts": 0,
            "items_total": 0,
            "success_rate": 0.0,
            "avg_cost_usd": 0.0,
            "capacity_pct": 0.0,
            "daily_spent_usd": 0.0,
            "api_spent_usd": 0.0,
            "cloud_spent_usd": 0.0,
            "avg_latency_ms": 0.0,
            "tokens_in": 0,
            "tokens_out": 0,
            "last_model": "",
            "sla_breaches": 0,
            "retries": 0,
            "failovers": 0,
            "cache_hits": 0,
            "human_escalations": 0,
            "p95_latency_ms": 0.0,
            "weekly_spent_usd": 0.0,
            "grill_count": 0,
            "grill_rate": 0.0,
            "decision_clarity": 1.0,
        },
        "alerts": [],
    }


def build_idle_roster() -> list[dict[str, Any]]:
    """匯出／降級用：內建 + 自定義角色，全部以 idle 工作台快照呈現。"""
    return [_blank_agent(snapshot) for snapshot in list_role_snapshots()]


def _event_payload(event: Any) -> dict[str, Any]:
    if isinstance(event, dict):
        data = event.get("data")
        if isinstance(data, dict):
            merged = {**event, **data}
            merged.pop("data", None)
            return merged
        return dict(event)
    return {}


def _event_name(payload: dict[str, Any]) -> str:
    return str(payload.get("event") or "")


def _event_ts(payload: dict[str, Any], fallback: float | str | None = None) -> str | None:
    ts = payload.get("ts") or payload.get("timestamp") or fallback
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
    text = str(ts)
    return text or None


def _roles_for_event(payload: dict[str, Any]) -> set[str]:
    roles: set[str] = set()
    assignee = _role_id(payload.get("assignee"))
    if assignee:
        roles.add(assignee)
    name = _event_name(payload)
    for role, events in ROLE_EVENT_HINTS.items():
        if name in events:
            roles.add(role)
    phase = str(payload.get("phase") or "")
    if name in {"phase", "phase_change"} and phase in PHASE_ROLE:
        roles.add(PHASE_ROLE[phase])
    return roles


def _compact_event(payload: dict[str, Any], task: TaskRecord | None = None) -> dict[str, Any]:
    return {
        "ts": _event_ts(payload, task.created_at if task else None),
        "event": _event_name(payload),
        "item_id": payload.get("item_id"),
        "title": payload.get("title") or payload.get("goal") or payload.get("phase") or "",
        "assignee": _role_id(payload.get("assignee")),
        "task_id": (task.task_id if task else None) or payload.get("run_id") or payload.get("task_id"),
        "cost_usd": float(payload.get("cost") or payload.get("cost_usd") or 0),
        "score": payload.get("score"),
        "degraded": bool(payload.get("degraded")),
        "duration_ms": payload.get("duration_ms") or payload.get("latency_ms"),
        "model": payload.get("model") or payload.get("model_name") or "",
        "tokens_in": payload.get("prompt_tokens") or payload.get("tokens_in") or 0,
        "tokens_out": payload.get("completion_tokens") or payload.get("tokens_out") or 0,
    }


def _append_event(bucket: dict[str, Any], payload: dict[str, Any], task: TaskRecord | None = None) -> None:
    compact = _compact_event(payload, task)
    key = (
        compact["ts"],
        compact["event"],
        compact["item_id"],
        compact["task_id"],
    )
    existing = {(e.get("ts"), e.get("event"), e.get("item_id"), e.get("task_id")) for e in bucket["events"]}
    if key in existing:
        return
    bucket["events"].append(compact)
    ts = compact["ts"]
    if ts and (not bucket["last_activity_at"] or str(ts) > str(bucket["last_activity_at"])):
        bucket["last_activity_at"] = ts
    cost = float(compact.get("cost_usd") or 0)
    if cost:
        bucket["cost_usd"] = round(float(bucket["cost_usd"]) + cost, 6)


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
    except Exception:  # noqa: BLE001
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

    for raw_status, items in kanban.items():
        status = _status_key(raw_status)
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
            hist = {
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


_BUDGET_ALERT_MARKERS = (
    "AI 日預算",
    "AI 週預算",
    "AI 月預算",
    "雲服務日預算",
    "雲服務週預算",
    "雲服務月預算",
    "日預算",
    "週預算",
    "月預算",
)


def _limit_remaining(limit: float, spent: float) -> float | None:
    if limit <= 0:
        return None
    return round(max(limit - spent, 0.0), 4)


def _limit_over(limit: float, spent: float) -> bool:
    return bool(limit > 0 and spent > limit)


def _strip_budget_alerts(alerts: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in alerts:
        message = item.get("message") or ""
        if any(marker in message for marker in _BUDGET_ALERT_MARKERS):
            continue
        cleaned.append(item)
    return cleaned


def _apply_split_budgets(agent: dict[str, Any]) -> None:
    """AI 使用預算對 API，雲服務預算對 Docker＋阿里雲；互不混算。"""
    api_spent = round(float(agent.get("api_cost_usd") or 0), 4)
    cloud_spent = round(float(agent.get("cloud_cost_usd") or 0), 4)
    ai_daily = float(agent.get("daily_budget_usd") or 0)
    ai_weekly = float(agent.get("weekly_budget_usd") or 0)
    ai_monthly = float(agent.get("monthly_budget_usd") or 0)
    cloud_daily = float(agent.get("cloud_daily_budget_usd") or 0)
    cloud_weekly = float(agent.get("cloud_weekly_budget_usd") or 0)
    cloud_monthly = float(agent.get("cloud_monthly_budget_usd") or 0)

    ai_over = (
        _limit_over(ai_daily, api_spent)
        or _limit_over(ai_weekly, api_spent)
        or _limit_over(ai_monthly, api_spent)
    )
    cloud_over = (
        _limit_over(cloud_daily, cloud_spent)
        or _limit_over(cloud_weekly, cloud_spent)
        or _limit_over(cloud_monthly, cloud_spent)
    )
    agent["ai_budget_remaining_usd"] = _limit_remaining(ai_daily, api_spent)
    agent["cloud_budget_remaining_usd"] = _limit_remaining(cloud_daily, cloud_spent)
    agent["ai_budget_over"] = ai_over
    agent["cloud_budget_over"] = cloud_over
    agent["budget_remaining_usd"] = agent["ai_budget_remaining_usd"]
    agent["budget_over"] = bool(ai_over or cloud_over)

    alerts = _strip_budget_alerts(list(agent.get("alerts") or []))
    if agent.get("alert_on_budget", True):
        if _limit_over(ai_daily, api_spent):
            alerts.append({"level": "critical", "message": "今日 AI 使用已超過日預算"})
        if _limit_over(ai_weekly, api_spent):
            alerts.append({"level": "critical", "message": "已超過 AI 週預算"})
        if _limit_over(ai_monthly, api_spent):
            alerts.append({"level": "critical", "message": "已超過 AI 月預算"})
        if _limit_over(cloud_daily, cloud_spent):
            alerts.append({"level": "critical", "message": "今日雲服務已超過日預算"})
        if _limit_over(cloud_weekly, cloud_spent):
            alerts.append({"level": "critical", "message": "已超過雲服務週預算"})
        if _limit_over(cloud_monthly, cloud_spent):
            alerts.append({"level": "critical", "message": "已超過雲服務月預算"})
    agent["alerts"] = alerts


def _finalize_agent(agent: dict[str, Any]) -> dict[str, Any]:
    inbox = _empty_inbox()
    for item in agent["work_items"]:
        status = _status_key(item.get("status"))
        if status in inbox:
            inbox[status] += 1
    agent["inbox"] = inbox
    agent["queue"] = inbox[WorkItemStatus.PLANNING.value] + inbox[WorkItemStatus.READY.value]
    agent["executing"] = inbox[WorkItemStatus.EXECUTING.value]
    agent["done"] = inbox[WorkItemStatus.DONE.value]
    agent["blocked"] = inbox[WorkItemStatus.BLOCKED.value] + inbox[WorkItemStatus.REWORK.value]

    live_busy = bool(agent["active_task_ids"]) or any(
        item.get("source") == "live" and item.get("status") == WorkItemStatus.EXECUTING.value
        for item in agent["work_items"]
    )
    if live_busy:
        agent["status"] = "busy"
    elif inbox[WorkItemStatus.BLOCKED.value] > 0:
        agent["status"] = "error"
    elif (
        agent["queue"] > 0
        or inbox[WorkItemStatus.IN_REVIEW.value] > 0
        or inbox[WorkItemStatus.REWORK.value] > 0
        or agent["executing"] > 0
    ):
        agent["status"] = "waiting"
    else:
        agent["status"] = "idle"

    items = sorted(
        agent["work_items"],
        key=lambda item: str(item.get("updated_at") or ""),
        reverse=True,
    )
    items.sort(key=lambda item: 0 if item.get("status") in OPEN_STATUSES else 1)
    agent["work_items"] = items[:MAX_ITEMS_PER_ROLE]
    agent["events"] = sorted(
        agent["events"],
        key=lambda ev: str(ev.get("ts") or ""),
        reverse=True,
    )[:MAX_EVENTS_PER_ROLE]
    CURRENT_STATUSES = frozenset(
        {
            WorkItemStatus.PLANNING.value,
            WorkItemStatus.READY.value,
            WorkItemStatus.EXECUTING.value,
            WorkItemStatus.IN_REVIEW.value,
            WorkItemStatus.REWORK.value,
        }
    )
    current = next(
        (item for item in agent["work_items"] if item.get("status") == WorkItemStatus.EXECUTING.value),
        None,
    )
    if current is None:
        current = next(
            (item for item in agent["work_items"] if item.get("status") in CURRENT_STATUSES),
            None,
        )
    agent["current_item"] = current
    # 工作項累計先視為 API（LLM）用量；雲資源稍後由 collect 分攤
    api_cost = round(float(agent["cost_usd"] or 0), 4)
    agent["api_cost_usd"] = api_cost
    agent["cloud_cost_usd"] = round(float(agent.get("cloud_cost_usd") or 0), 4)
    agent["docker_cost_usd"] = round(float(agent.get("docker_cost_usd") or 0), 4)
    agent["aliyun_cost_usd"] = round(float(agent.get("aliyun_cost_usd") or 0), 4)
    agent["cost_usd"] = round(api_cost + float(agent["cloud_cost_usd"]), 4)
    events = agent["events"]
    items_total = len(agent["work_items"])
    done = int(agent["done"])
    failed = int(agent["blocked"])
    decided = done + failed
    daily_spent = round(float(agent["cost_usd"] or 0), 4)
    api_spent = round(float(agent.get("api_cost_usd") or 0), 4)
    cloud_spent = round(float(agent.get("cloud_cost_usd") or 0), 4)
    cap = max(int(agent["max_parallel_work"] or 1), 1)
    sla_ms = int(agent.get("sla_latency_ms") or 0)
    sla_breaches = 0
    if sla_ms > 0:
        sla_breaches = sum(
            1
            for e in events
            if float(e.get("duration_ms") or 0) > sla_ms
        )
    agent["metrics"] = {
        "review_pass": sum(
            1 for e in events if e.get("event") in {"review_pass", "review_approved"}
        ),
        "review_rework": sum(1 for e in events if e.get("event") == "review_rework"),
        "review_force": sum(1 for e in events if e.get("event") == "review_force_done"),
        "errors": sum(
            1 for e in events if e.get("event") in {"work_item_error", "budget_degrade"}
        ),
        "tool_calls": sum(
            1 for e in events if e.get("event") in {"tool_call", "tool_result"}
        ),
        "budget_alerts": sum(
            1 for e in events if e.get("event") in {"budget_warning", "budget_degrade"}
        ),
        "items_total": items_total,
        "success_rate": round((done / decided) * 100, 1) if decided else 0.0,
        "avg_cost_usd": round(daily_spent / items_total, 4) if items_total else 0.0,
        "capacity_pct": round(min(int(agent["executing"]), cap) / cap * 100, 1),
        "daily_spent_usd": daily_spent,
        "api_spent_usd": api_spent,
        "cloud_spent_usd": cloud_spent,
        "avg_latency_ms": round(
            sum(float(e.get("duration_ms") or 0) for e in events if e.get("duration_ms"))
            / max(sum(1 for e in events if e.get("duration_ms")), 1),
            1,
        )
        if any(e.get("duration_ms") for e in events)
        else 0.0,
        "tokens_in": int(sum(int(e.get("tokens_in") or 0) for e in events)),
        "tokens_out": int(sum(int(e.get("tokens_out") or 0) for e in events)),
        "last_model": next((str(e.get("model") or "") for e in events if e.get("model")), "")
        or str(agent.get("preferred_model") or ""),
        "sla_breaches": sla_breaches,
        "retries": sum(1 for e in events if e.get("event") in {"retry", "work_item_retry"}),
        "failovers": sum(1 for e in events if e.get("event") in {"failover", "budget_degrade"}),
        "cache_hits": sum(1 for e in events if e.get("event") in {"cache_hit", "semantic_cache_hit"}),
        "human_escalations": sum(
            1
            for e in events
            if e.get("event")
            in {
                "human_approval",
                "escalation",
                "user_decision_needed",
                "work_item_escalate",
            }
        ),
        "grill_count": sum(
            1 for e in events if e.get("event") in {"grill_raised", "grill_resolved"}
        ),
        "p95_latency_ms": _p95([float(e.get("duration_ms") or 0) for e in events if e.get("duration_ms")]),
        "weekly_spent_usd": api_spent,
        "weekly_cloud_spent_usd": cloud_spent,
        "grill_rate": 0.0,
        "decision_clarity": 1.0,
    }
    try:
        from backend.company.raho.scorecard import metrics_for

        card = metrics_for(str(agent.get("id") or ""))
        agent["metrics"]["grill_count"] = max(
            int(agent["metrics"]["grill_count"]), int(card.get("grill_count") or 0)
        )
        agent["metrics"]["grill_rate"] = card.get("grill_rate", 0.0)
        agent["metrics"]["decision_clarity"] = card.get("decision_clarity", 1.0)
        agent["metrics"]["human_escalations"] = max(
            int(agent["metrics"]["human_escalations"]),
            int(card.get("user_escalations") or 0),
        )
        agent["metrics"]["demoted"] = bool(card.get("demoted"))
        agent["metrics"]["raho_rank"] = card.get("rank") or "ok"
        agent["demoted"] = bool(card.get("demoted"))
        agent["raho_rank"] = card.get("rank") or "ok"
    except Exception:  # noqa: BLE001
        pass
    alerts: list[dict[str, str]] = []
    if not agent.get("enabled", True):
        alerts.append({"level": "info", "message": "角色已停用，分解時不會被指派"})
    if int(agent["metrics"]["errors"]) > 0 and agent.get("alert_on_error", True):
        alerts.append({"level": "warning", "message": f"最近 {agent['metrics']['errors']} 次錯誤／降級"})
    if sla_breaches and agent.get("alert_on_sla", True):
        alerts.append({"level": "warning", "message": f"SLA 逾時 {sla_breaches} 次（>{agent.get('sla_latency_ms')}ms）"})
    if agent["status"] == "error":
        alerts.append({"level": "critical", "message": f"{agent['blocked']} 項阻塞／返工待處理"})
    cap_pct = float(agent["metrics"].get("capacity_pct") or 0)
    if cap_pct >= 80:
        alerts.append({"level": "warning", "message": f"並行容量已用 {cap_pct:.0f}%"})
    grill_rate = float(agent["metrics"].get("grill_rate") or 0)
    if agent.get("demoted") or agent["metrics"].get("demoted"):
        alerts.append(
            {
                "level": "critical",
                "message": f"規劃能力已降級：被質詢率 {grill_rate:.0%}，改走規則骨架",
            }
        )
    elif grill_rate >= 0.4:
        alerts.append(
            {"level": "warning", "message": f"被質詢率 {grill_rate:.0%}，規劃清晰度偏低"}
        )
    if agent.get("always_require_review"):
        alerts.append({"level": "info", "message": "此角色產出一律送審查"})
    if agent.get("require_human_approval"):
        alerts.append({"level": "info", "message": "執行前需人工核准"})
    if agent.get("on_call"):
        alerts.append({"level": "info", "message": "目前值班中"})
    if agent.get("mainland_only"):
        alerts.append({"level": "info", "message": "僅國內模型（避免資料出境）"})
    if not agent.get("allow_tool_use", True):
        alerts.append({"level": "warning", "message": "已關閉工具呼叫"})
    max_items = int(agent.get("max_daily_items") or 0)
    if max_items > 0 and items_total >= max_items:
        alerts.append({"level": "warning", "message": f"今日工作項已達上限 {max_items}"})
    agent["alerts"] = alerts
    _apply_split_budgets(agent)
    seen_tasks: dict[str, dict[str, Any]] = {}
    for item in agent["work_items"]:
        tid = str(item.get("task_id") or "")
        if not tid or tid in seen_tasks:
            continue
        seen_tasks[tid] = {
            "task_id": tid,
            "query": item.get("task_query") or tid,
            "status": item.get("task_status") or "",
            "phase": item.get("phase") or "",
        }
    agent["company_tasks"] = list(seen_tasks.values())[:12]
    agent["capacity_used"] = min(int(agent["executing"]), int(agent["max_parallel_work"]))
    if not agent.get("enabled", True):
        agent["status"] = "disabled"
    return agent


def _allocate_cloud_costs(agents: list[dict[str, Any]]) -> dict[str, float]:
    """將 Docker + 阿里雲雲資源費用按 API 用量比例分攤到各 Agent。

    花費仍分開記：api_cost_usd 對 AI 預算，cloud_cost_usd 對雲服務預算。
    無 API 花費的活躍角色均分；全無活動時只回報彙總、不強行分攤。
    """
    docker_usd = 0.0
    aliyun_usd = 0.0
    try:
        from backend.services.cloud_console import get_cloud_billing

        summary = get_cloud_billing().get_billing_summary()
        breakdown = summary.get("breakdown") or {}
        docker_usd = float(breakdown.get("docker_usd") or 0)
        aliyun_usd = float(breakdown.get("aliyun_usd") or 0)
    except Exception:  # noqa: BLE001
        logger.debug("雲資源費用讀取失敗，Agent 雲成本視為 0", exc_info=True)

    cloud_total = docker_usd + aliyun_usd
    if cloud_total <= 0:
        return {
            "docker_usd": 0.0,
            "aliyun_usd": 0.0,
            "cloud_total_usd": 0.0,
            "api_total_usd": round(sum(float(a.get("api_cost_usd") or 0) for a in agents), 4),
        }

    active = [
        a
        for a in agents
        if float(a.get("api_cost_usd") or 0) > 0
        or a.get("status") in {"busy", "waiting", "error"}
        or int(a.get("queue") or 0) + int(a.get("executing") or 0) > 0
    ]
    if not active:
        active = [a for a in agents if a.get("enabled", True)]

    api_sum = sum(float(a.get("api_cost_usd") or 0) for a in active)
    for a in agents:
        a["docker_cost_usd"] = 0.0
        a["aliyun_cost_usd"] = 0.0
        a["cloud_cost_usd"] = 0.0

    if not active:
        return {
            "docker_usd": round(docker_usd, 4),
            "aliyun_usd": round(aliyun_usd, 4),
            "cloud_total_usd": round(cloud_total, 4),
            "api_total_usd": round(sum(float(a.get("api_cost_usd") or 0) for a in agents), 4),
        }

    for a in active:
        if api_sum > 0:
            share = float(a.get("api_cost_usd") or 0) / api_sum
        else:
            share = 1.0 / len(active)
        docker_share = round(docker_usd * share, 4)
        aliyun_share = round(aliyun_usd * share, 4)
        cloud_share = round(docker_share + aliyun_share, 4)
        a["docker_cost_usd"] = docker_share
        a["aliyun_cost_usd"] = aliyun_share
        a["cloud_cost_usd"] = cloud_share
        a["cost_usd"] = round(float(a.get("api_cost_usd") or 0) + cloud_share, 4)
        metrics = a.get("metrics") or {}
        metrics["daily_spent_usd"] = a["cost_usd"]
        metrics["api_spent_usd"] = round(float(a.get("api_cost_usd") or 0), 4)
        metrics["cloud_spent_usd"] = cloud_share
        metrics["weekly_spent_usd"] = metrics["api_spent_usd"]
        metrics["weekly_cloud_spent_usd"] = cloud_share
        a["metrics"] = metrics
        _apply_split_budgets(a)

    return {
        "docker_usd": round(docker_usd, 4),
        "aliyun_usd": round(aliyun_usd, 4),
        "cloud_total_usd": round(cloud_total, 4),
        "api_total_usd": round(sum(float(a.get("api_cost_usd") or 0) for a in agents), 4),
    }


def _ingest_auditor_sessions(agents: dict[str, dict[str, Any]]) -> None:
    """把進行中的需求審計會話掛到 L4 需求審計官工作台。"""
    bucket = agents.get("requirement_auditor")
    if not bucket:
        return
    try:
        from backend.company.raho.store import STORE
    except Exception:  # noqa: BLE001
        logger.debug("讀取審計會話失敗（已忽略）", exc_info=True)
        return

    for sess in list(STORE.user_sessions.values()):
        if sess.locked:
            status = WorkItemStatus.DONE.value
            title = "需求審計門票已核發"
            task_status = "completed"
        elif sess.terminated:
            status = WorkItemStatus.BLOCKED.value
            title = "需求審計失敗"
            task_status = "failed"
        else:
            status = WorkItemStatus.EXECUTING.value
            title = f"Phase {int(sess.phase or 1)} 需求審計"
            task_status = "running"
        last = ""
        for turn in reversed(sess.turns or []):
            if turn.get("role") == "assistant":
                last = str(turn.get("content") or "")
                break
        item = {
            "id": f"auditor:{sess.session_id}",
            "title": title,
            "description": (sess.query or "")[:240],
            "status": status,
            "kind": "requirement_audit",
            "assignee": "requirement_auditor",
            "task_id": f"grill:{sess.session_id}",
            "task_query": sess.query,
            "task_status": task_status,
            "phase": f"phase_{int(sess.phase or 1)}",
            "cost_usd": 0.0,
            "estimated_cost": 0.0,
            "output_preview": last[:280],
            "updated_at": _now_iso(),
            "source": "live",
            "depends_on": [],
            "tier": "reasoning",
            "feedback": [],
        }
        _upsert_item(bucket, item)
        _append_event(
            bucket,
            {
                "ts": sess.created_at,
                "event": "user_grill",
                "item_id": sess.session_id,
                "title": title,
                "assignee": "requirement_auditor",
                "run_id": f"grill:{sess.session_id}",
            },
        )


def collect_agent_monitor() -> dict[str, Any]:
    """聚合每位角色的 Agent 工作台；目錄永遠完整，缺資料時全部待命。"""
    snapshots = list_role_snapshots()
    agents = {snap["id"]: _blank_agent(snap) for snap in snapshots}

    try:
        records = list(task_manager.tasks.values())
    except Exception:  # noqa: BLE001
        logger.warning("讀取任務列表失敗，角色監控降級為目錄", exc_info=True)
        records = []

    company_tasks = 0
    running_company = 0
    for rec in records:
        is_company = rec.resolved_path == "company" or bool(rec.kanban)
        if not is_company:
            continue
        company_tasks += 1
        if rec.status in {"running", "pending"}:
            running_company += 1
        try:
            _ingest_live_task(agents, rec)
        except Exception:  # noqa: BLE001
            logger.warning("聚合任務 %s 的角色資料失敗（已跳過）", rec.task_id, exc_info=True)

    try:
        _ingest_run_logs(agents)
    except Exception:  # noqa: BLE001
        logger.warning("讀取公司 run log 失敗（已忽略）", exc_info=True)

    try:
        _ingest_auditor_sessions(agents)
    except Exception:  # noqa: BLE001
        logger.warning("讀取需求審計會話失敗（已忽略）", exc_info=True)

    finalized = [_finalize_agent(agent) for agent in agents.values()]
    cost_breakdown = _allocate_cloud_costs(finalized)
    finalized.sort(key=lambda a: (a["level"], a["id"]))

    roles_busy = sum(1 for a in finalized if a["status"] == "busy")
    roles_waiting = sum(1 for a in finalized if a["status"] == "waiting")
    open_items = sum(a["queue"] + a["executing"] + a["inbox"][WorkItemStatus.IN_REVIEW.value] for a in finalized)
    done_items = sum(a["done"] for a in finalized)

    return {
        "generated_at": _now_iso(),
        "summary": {
            "roles_total": len(finalized),
            "roles_busy": roles_busy,
            "roles_waiting": roles_waiting,
            "roles_idle": sum(1 for a in finalized if a["status"] == "idle"),
            "roles_custom": sum(1 for a in finalized if a.get("is_custom")),
            "roles_disabled": sum(1 for a in finalized if not a.get("enabled", True)),
            "roles_enabled": sum(1 for a in finalized if a.get("enabled", True)),
            "alerts_open": sum(len(a.get("alerts") or []) for a in finalized),
            "work_items_open": open_items,
            "work_items_done": done_items,
            "company_tasks": company_tasks,
            "running_company_tasks": running_company,
            "total_cost_usd": round(sum(float(a.get("cost_usd") or 0) for a in finalized), 4),
            "total_api_cost_usd": cost_breakdown["api_total_usd"],
            "total_cloud_cost_usd": cost_breakdown["cloud_total_usd"],
            "total_docker_cost_usd": cost_breakdown["docker_usd"],
            "total_aliyun_cost_usd": cost_breakdown["aliyun_usd"],
            "roles_on_call": sum(1 for a in finalized if a.get("on_call")),
            "roles_need_approval": sum(1 for a in finalized if a.get("require_human_approval")),
            "roles_mainland_only": sum(1 for a in finalized if a.get("mainland_only")),
        },
        "levels": [
            {"level": level, "label": label}
            for level, label in LEVEL_LABELS.items()
        ],
        "raho_layers": raho_directory(),
        "catalog_meta": catalog_meta(),
        "monitor_prefs": get_monitor_prefs(),
        "agents": finalized,
    }
