"""Hub 監控快照：探針、熔斷、呼叫日誌、預算、Agent 任務。"""

from __future__ import annotations

from typing import Any

from backend.hub.catalog import (
    CN_CHAIN,
    DEFAULT_CHAIN,
    HUB_CATALOG,
    INTEL,
    PROVIDER_OF,
    RACE_PAIR,
    public_pool_lock,
    runtime_hub_whitelist,
)
from backend.hub.runtime import runtime
from backend.hub.store import AgentTask


def _task_row(task: AgentTask) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "status": task.status,
        "input": (task.input or "")[:240],
        "tools": task.tools,
        "cost_usd": round(float(task.cost_usd or 0), 6),
        "chosen_provider": task.chosen_provider,
        "latency_ms": task.latency_ms,
        "progress_pct": task.progress_pct,
        "error_code": task.error_code,
        "trace_id": task.trace_id,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def collect_hub_monitor() -> dict[str, Any]:
    """供 GET /monitor/hub 使用；目錄外不含任何 Claude ID。"""
    for model in HUB_CATALOG:
        runtime.circuits.get(model)

    logs = list(runtime.store.call_logs[-80:])
    logs.reverse()
    tasks = sorted(
        runtime.store.tasks.values(),
        key=lambda t: t.created_at,
        reverse=True,
    )[:20]

    budgets = []
    for user in runtime.store.users_by_id.values():
        spent = runtime.budget.spent_today(str(user.id))
        budgets.append(
            {
                "name": user.name,
                "spent_today_usd": round(spent, 6),
                "daily_limit_usd": user.daily_budget_limit_usd,
                "monthly_limit_usd": user.monthly_budget_limit_usd,
                "remaining_today_usd": round(
                    max(0.0, user.daily_budget_limit_usd - spent), 6
                ),
            }
        )

    models = []
    metrics = runtime.store.provider_metrics
    circuits = runtime.circuits.snapshot()
    available = set(runtime_hub_whitelist() or HUB_CATALOG)
    from backend.core.provider_pool import clamp_model

    for model in sorted(HUB_CATALOG):
        row = dict(metrics.get(model) or {})
        try:
            from backend.company.rate_card import rate_card_for

            extra = rate_card_for(model)
        except Exception:
            extra = {}
        models.append(
            {
                "id": model,
                "provider": PROVIDER_OF[model],
                "intelligence": INTEL[model],
                "latency_ewma_ms": row.get("latency_ewma_ms"),
                "ttfb_ms": row.get("ttfb_ms"),
                "price_in_per_1m": row.get("price_in_per_1m"),
                "price_out_per_1m": row.get("price_out_per_1m"),
                "price_cached_in_per_1m": extra.get("cached_input") or None,
                "price_cache_write_per_1m": extra.get("cache_write") or None,
                "price_reasoning_per_1m": extra.get("reasoning") or None,
                "price_image_per_1m": extra.get("image") or None,
                "price_audio_per_1m": extra.get("audio") or None,
                "consecutive_fail": int(row.get("consecutive_fail") or 0),
                "ts": row.get("ts"),
                "circuit": circuits.get(model) or {"state": "CLOSED"},
                "available_in_pool": model in available,
                "mapped_model": clamp_model(model) if model in available else "",
            }
        )

    return {
        "cache": {
            "hits": runtime.cache.hits,
            "misses": runtime.cache.misses,
            "hit_rate": runtime.cache.hit_rate(),
            "target_hit_rate": 0.40,
        },
        "upstream_calls": len(runtime.upstream_calls),
        "call_log_count": len(runtime.store.call_logs),
        "call_logs": logs,
        "models": models,
        "circuits": circuits,
        "budgets": budgets,
        "agent_tasks": [_task_row(t) for t in tasks],
        "routing": {
            "default_chain": list(DEFAULT_CHAIN),
            "cn_chain": list(CN_CHAIN),
            "race_pair": list(RACE_PAIR),
            "forbidden_vendor": "anthropic",
            "pool_lock": public_pool_lock(),
        },
    }
