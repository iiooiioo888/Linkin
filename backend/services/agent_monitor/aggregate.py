"""角色監控主聚合：collect_agent_monitor 與審計／帳戶預算彙整。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import grill_edges, raho_directory
from backend.company.role_catalog import (
    LEVEL_LABELS,
    catalog_meta,
    get_monitor_prefs,
    list_role_snapshots,
)
from backend.company.state import WorkItemStatus
from backend.services.task_manager import task_manager

from . import costs
from .common import _now_iso, logger
from .events import _append_event
from .items import (
    _coerce_terminal_task_work_items,
    _ingest_live_task,
    _ingest_run_logs,
    _upsert_item,
)
from .roster import _blank_agent


def _ingest_auditor_sessions(agents: dict[str, dict[str, Any]]) -> None:
    """把進行中的需求審計會話掛到 L4 需求審計官工作台。"""
    bucket = agents.get("requirement_auditor")
    if not bucket:
        return
    try:
        from backend.company.raho.store import STORE
    except Exception:
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


def _collect_account_budget_summary(tenant_id: str | None = None) -> dict[str, Any]:
    """帳戶級預算摘要：Hub 日限額（USD）與靈境積分（credits）分開標示，不混算。"""
    from backend.tenant.context import current_tenant_user

    uid = (tenant_id or current_tenant_user()).strip()
    summary: dict[str, Any] = {"tenant_user_id": uid}
    try:
        from backend.hub.runtime import runtime

        hub_user = runtime.store.seed_dev_user()
        hub_uid = str(hub_user.id)
        if uid and uid not in {hub_uid, "dev", "seed_dev_user"}:
            summary["hub_daily"] = None
        else:
            spent = float(runtime.budget.spent_today(hub_uid))
            limit = float(hub_user.daily_budget_limit_usd or 0)
            summary["hub_daily"] = {
                "label": "Hub API 日預算",
                "unit": "usd",
                "spent_today_usd": round(spent, 4),
                "daily_limit_usd": limit,
                "remaining_today_usd": round(max(0.0, limit - spent), 4) if limit > 0 else None,
            }
    except Exception:
        logger.debug("Hub 帳戶預算摘要讀取失敗（已忽略）", exc_info=True)
        summary["hub_daily"] = None
    try:
        from backend.billing.quota import get_billing_service

        acct = get_billing_service().get_account(uid)
        summary["linkin_credits"] = {
            "label": "用量額度",
            "unit": "credits",
            "balance_credits": round(float(acct.get("balance_credits") or 0), 2),
            "monthly_quota_credits": round(float(acct.get("monthly_quota_credits") or 0), 2),
            "monthly_used_credits": round(float(acct.get("monthly_used_credits") or 0), 2),
        }
    except Exception:
        logger.debug("靈境積分摘要讀取失敗（已忽略）", exc_info=True)
        summary["linkin_credits"] = None
    return summary


def collect_agent_monitor(tenant_id: str | None = None) -> dict[str, Any]:
    """聚合每位角色的 Agent 工作台；目錄永遠完整，缺資料時全部待命。"""
    from backend.tenant.context import current_tenant_user
    from backend.tenant.tasks import task_visible_for_tenant

    uid = (tenant_id or current_tenant_user()).strip()
    snapshots = list_role_snapshots()
    agents = {snap["id"]: _blank_agent(snap) for snap in snapshots}

    try:
        records = [
            rec
            for rec in task_manager.tasks.values()
            if task_visible_for_tenant(rec, uid)
        ]
    except Exception:
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
            _coerce_terminal_task_work_items(agents, rec)
        except Exception:
            logger.warning("聚合任務 %s 的角色資料失敗（已跳過）", rec.task_id, exc_info=True)

    try:
        _ingest_run_logs(agents)
    except Exception:
        logger.warning("讀取公司 run log 失敗（已忽略）", exc_info=True)

    try:
        _ingest_auditor_sessions(agents)
    except Exception:
        logger.warning("讀取需求審計會話失敗（已忽略）", exc_info=True)

    finalized = [costs._finalize_agent(agent) for agent in agents.values()]
    cost_breakdown = costs._allocate_cloud_costs(finalized)
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
        "grill_chain": grill_edges(),
        "catalog_meta": catalog_meta(),
        "monitor_prefs": get_monitor_prefs(),
        "account_budget": _collect_account_budget_summary(uid),
        "tenant_user_id": uid,
        "agents": finalized,
    }
