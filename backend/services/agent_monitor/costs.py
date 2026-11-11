"""成本彙整：token／成本統計、預算拆分、雲成本分配與最終化。"""

from __future__ import annotations

import json
from typing import Any

from backend.company.state import WorkItemStatus
from backend.services.task_manager import task_manager

from .common import (
    MAX_EVENTS_PER_ROLE,
    MAX_ITEMS_PER_ROLE,
    OPEN_STATUSES,
    _empty_inbox,
    _p95,
    _status_key,
    logger,
)

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


def _count_budget_alerts(agent: dict[str, Any]) -> int:
    """事件型 budget_warning/degrade 與監控快照型預算告警合計。"""
    event_count = sum(
        1
        for e in agent.get("events") or []
        if e.get("event") in {"budget_warning", "budget_degrade"}
    )
    alert_count = sum(
        1
        for item in agent.get("alerts") or []
        if any(marker in (item.get("message") or "") for marker in _BUDGET_ALERT_MARKERS)
    )
    return max(event_count, alert_count)


def _strip_budget_alerts(alerts: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in alerts:
        message = item.get("message") or ""
        if any(marker in message for marker in _BUDGET_ALERT_MARKERS):
            continue
        cleaned.append(item)
    return cleaned


_ARCHIVE_QUERY_CACHE: dict[str, str] = {}
_ARCHIVE_QUERY_CACHE_LOADED = False


def _archive_query(task_id: str) -> str:
    """從 JSONL 對話存檔回填已淘汰任務的原始查詢（程序內快取）。"""
    global _ARCHIVE_QUERY_CACHE_LOADED
    if not _ARCHIVE_QUERY_CACHE_LOADED:
        _ARCHIVE_QUERY_CACHE_LOADED = True
        try:
            from backend.services.archiver import _archive_dir

            for path in sorted(_archive_dir().glob("*.jsonl")):
                try:
                    with open(path, encoding="utf-8") as f:
                        for line in f:
                            try:
                                row = json.loads(line)
                            except json.JSONDecodeError:
                                continue
                            sid = str(row.get("session_id") or "")
                            q = str(row.get("user_query") or row.get("query") or "")
                            if sid and q:
                                _ARCHIVE_QUERY_CACHE.setdefault(sid, q)
                except OSError:
                    continue
        except Exception:
            logger.debug("存檔查詢回填載入失敗", exc_info=True)
    return _ARCHIVE_QUERY_CACHE.get(task_id, "")


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
    except Exception:
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
    agent["metrics"]["budget_alerts"] = _count_budget_alerts(agent)
    seen_tasks: dict[str, dict[str, Any]] = {}
    for item in agent["work_items"]:
        tid = str(item.get("task_id") or "")
        if not tid or tid in seen_tasks:
            continue
        # run_log 來源的工作項可能缺 query/status：從 task_manager 回填
        query = item.get("task_query") or ""
        status = item.get("task_status") or ""
        phase = item.get("phase") or ""
        if not query or not status:
            rec = task_manager.get_task(tid)
            if rec is not None:
                query = query or rec.query or tid
                status = status or rec.status
                phase = phase or rec.phase
        if not query or query == tid:
            query = _archive_query(tid) or query or tid
        seen_tasks[tid] = {
            "task_id": tid,
            "query": query or tid,
            "status": status or "unknown",
            "phase": phase,
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
    except Exception:
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
