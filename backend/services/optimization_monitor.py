"""性能優化與系統指標監控聚合（P0–P3 路線圖可觀測性）。

供 GET /monitor/optimization 使用，彙總各優化模組的運行時狀態與指標。
此處「指標」指 EvoLoop 自身系統狀態（快取、反思、路由、Trace 等），
非 OPC UA 工業現場感測。
"""

from __future__ import annotations

import os
from typing import Any

from backend.core.cost_speed_router import cost_speed_status
from backend.core.dynamic_threshold import resolve_pass_threshold, threshold_config
from backend.core.graph import MAX_ITERATIONS, MIN_SCORE_IMPROVEMENT, PASS_THRESHOLD
from backend.core.llm_cache import get_llm_cache
from backend.core.provider_pool import (
    pool_failover_enabled,
    pool_failover_timeout_s,
    pool_health_snapshot,
    pool_probe_snapshot,
)
from backend.core.routing_feedback import routing_stats
from backend.core.stage_router import resolve_stage_model, stage_tier
from backend.core.user_feedback import feedback_analysis
from backend.core.user_feedback import feedback_stats as user_feedback_stats
from backend.services.task_manager import task_manager
from backend.services.trace_logger import (
    aggregate_llm_call_stats,
    aggregate_reflection_stats,
    list_traces,
)


def _cache_hit_rate(stats: dict[str, int]) -> float:
    total = stats.get("hits", 0) + stats.get("misses", 0)
    if total <= 0:
        return 0.0
    return round(stats["hits"] / total, 4)


def _system_task_stats() -> dict[str, Any]:
    """從任務管理器彙總運行時指標（唯讀、降級安全）。"""
    try:
        tasks = list(task_manager.tasks.values())
    except Exception:
        return {
            "tasks_total": 0,
            "tasks_running": 0,
            "tasks_completed": 0,
            "tasks_failed": 0,
            "success_rate": 0.0,
            "avg_score": None,
            "total_iterations": 0,
        }
    completed = [t for t in tasks if t.status == "completed"]
    failed = [t for t in tasks if t.status == "failed"]
    running = [t for t in tasks if t.status in ("running", "pending")]
    scored = [t.score for t in completed if isinstance(t.score, (int, float))]
    return {
        "tasks_total": len(tasks),
        "tasks_running": len(running),
        "tasks_completed": len(completed),
        "tasks_failed": len(failed),
        "success_rate": round(len(completed) / len(tasks) * 100, 1) if tasks else 0.0,
        "avg_score": round(sum(scored) / len(scored), 2) if scored else None,
        "total_iterations": sum(int(t.iteration or 0) for t in tasks),
    }


def _layered_cache_status() -> dict[str, Any]:
    """系統分層快取狀態（LLM 精確 + 語義），非 OPC UA 工業感測。"""
    cache = get_llm_cache()
    stats = cache.stats
    max_size = int(os.getenv("EVOL_LLM_CACHE_SIZE", "512"))
    ttl = int(os.getenv("EVOL_LLM_CACHE_TTL", "3600"))
    semantic_on = os.getenv("EVOL_SEMANTIC_CACHE", "true").lower() == "true"
    entry_count = cache.size
    hit_rate = _cache_hit_rate(stats)
    active = entry_count > 0 or stats.get("hits", 0) > 0
    return {
        "source": "llm_cache",
        "tier": "semantic+exact" if semantic_on else "exact",
        "edge_ttl_sec": ttl,
        "max_size": max_size,
        "cache_age_sec": None,
        "cache_fresh": active,
        "entry_count": entry_count,
        "hit_rate": hit_rate,
        "reading_count": entry_count,  # 向後相容舊前端欄位
    }


def _trace_summary() -> dict[str, Any]:
    try:
        traces = list_traces(limit=200)
        return {"trace_count": len(traces), "recent": traces[:5]}
    except Exception:
        return {"trace_count": 0, "recent": []}


def _stage_routing() -> dict[str, Any]:
    stages = ["generate", "evaluate", "reflect", "improve", "cross_eval", "decompose"]
    mapping: dict[str, dict[str, str]] = {}
    for stage in stages:
        tier = stage_tier(stage)  # type: ignore[arg-type]
        try:
            model = resolve_stage_model(stage)  # type: ignore[arg-type]
        except Exception:
            model = "—"
        mapping[stage] = {"tier": tier.value, "model": model}
    return mapping


def collect_optimization_monitor() -> dict[str, Any]:
    """聚合性能優化路線圖各項指標（唯讀、降級安全）。"""
    cache_stats = get_llm_cache().stats
    routing = routing_stats()
    hit_rate = _cache_hit_rate(cache_stats)

    merge_enabled = os.getenv("EVOL_MERGE_REVIEW_SYNTH", "true").lower() == "true"
    semantic_on = os.getenv("EVOL_SEMANTIC_CACHE", "true").lower() == "true"

    stage_mapping = _stage_routing()
    trace_summary = _trace_summary()
    edge_cache = _layered_cache_status()
    system_stats = _system_task_stats()
    reflection_cfg = {
        "pass_threshold": PASS_THRESHOLD,
        "dynamic_threshold": threshold_config(),
        "sample_threshold_simple": resolve_pass_threshold("你好"),
        "sample_threshold_complex": resolve_pass_threshold("請設計並實現一個完整的微服務系統架構"),
        "max_iterations": MAX_ITERATIONS,
        "min_score_improvement": MIN_SCORE_IMPROVEMENT,
    }
    user_fb = user_feedback_stats()
    fb_analysis = feedback_analysis()
    pool_health = pool_health_snapshot()
    probe = pool_probe_snapshot()
    model_calls = aggregate_llm_call_stats()
    reflection_trace = aggregate_reflection_stats()
    open_models = sum(1 for h in pool_health.values() if h.get("open"))
    cost_speed = cost_speed_status()

    roadmap = [
        {
            "priority": "P0",
            "id": "stage_router",
            "label": "任務-模型匹配",
            "benefit": "成本降低 40–60%",
            "enabled": True,
            "status": "active",
            "metric": f"{len(stage_mapping)} 環節已路由",
        },
        {
            "priority": "P0",
            "id": "dynamic_threshold",
            "label": "動態反思閾值",
            "benefit": "簡單任務減少不必要反思",
            "enabled": True,
            "status": "active",
            "metric": (
                f"簡單 {reflection_cfg['sample_threshold_simple']} · "
                f"複雜 {reflection_cfg['sample_threshold_complex']}"
            ),
        },
        {
            "priority": "P0",
            "id": "reflection_early_stop",
            "label": "反思早停機制",
            "benefit": "避免無效呼叫、降低延遲",
            "enabled": True,
            "status": "active",
            "metric": (
                f"門檻 {reflection_cfg['pass_threshold']} · "
                f"Δ{reflection_cfg['min_score_improvement']} · "
                f"≤{reflection_cfg['max_iterations']} 輪"
            ),
        },
        {
            "priority": "P1",
            "id": "merge_review_synth",
            "label": "Reviewer + Synthesizer 合併",
            "benefit": "延遲降低 ~25%",
            "enabled": merge_enabled,
            "status": "active" if merge_enabled else "disabled",
            "metric": "合併模式" if merge_enabled else "分離模式",
        },
        {
            "priority": "P1",
            "id": "layered_cache",
            "label": "分層快取",
            "benefit": "命中率提升",
            "enabled": True,
            "status": "active",
            "metric": f"命中 {hit_rate * 100:.0f}% · {cache_stats.get('hits', 0)} 次",
        },
        {
            "priority": "P1",
            "id": "pool_failover",
            "label": "模型池健康檢查 + 自動降級",
            "benefit": "主模型逾時/限流自動切換備援；定時主動探活預判切換",
            "enabled": pool_failover_enabled(),
            "status": "active" if pool_failover_enabled() else "disabled",
            "metric": (
                f"逾時 {pool_failover_timeout_s():.0f}s · 熔斷 {open_models} 個 · "
                f"探活{'開' if probe.get('enabled') else '關'}"
                + (f"/{probe.get('mode')}" if probe.get("at") else "")
            ),
        },
        {
            "priority": "P1",
            "id": "cost_speed_router",
            "label": "成本感知路由",
            "benefit": "簡單任務走便宜模型、複雜推理走深度模型",
            "enabled": cost_speed.get("enabled", False),
            "status": "active" if cost_speed.get("enabled") else "disabled",
            "metric": (
                f"simple→{cost_speed.get('routing_preview', {}).get('simple', {}).get('generate_model', '—')} · "
                f"complex→{cost_speed.get('routing_preview', {}).get('complex', {}).get('path', '—')}"
            ),
        },
        {
            "priority": "P2",
            "id": "routing_feedback",
            "label": "路由自適應反饋",
            "benefit": "長期品質提升",
            "enabled": routing.get("total", 0) >= 0,
            "status": "learning" if routing.get("total", 0) < 10 else "active",
            "metric": (
                f"門檻 {routing.get('adaptive_length_threshold', '—')} · "
                f"n={routing.get('total', 0)}"
            ),
        },
        {
            "priority": "P2",
            "id": "edge_cache",
            "label": "分層快取（系統）",
            "benefit": "相似 prompt 本地復用",
            "enabled": True,
            "status": "active",
            "metric": (
                f"命中 {edge_cache.get('hit_rate', 0) * 100:.0f}% · "
                f"{edge_cache.get('entry_count', 0)}/{edge_cache.get('max_size', 512)} 項"
            ),
        },
        {
            "priority": "P3",
            "id": "user_feedback",
            "label": "用戶反饋閉環",
            "benefit": "驅動策略自適應",
            "enabled": True,
            "status": "active" if user_fb.get("total", 0) >= 1 else "idle",
            "metric": (
                f"滿意度 {user_fb.get('satisfaction_rate', 0) * 100:.0f}% · "
                f"n={user_fb.get('total', 0)}"
            ),
        },
        {
            "priority": "P3",
            "id": "pipeline_trace",
            "label": "全鏈路 trace",
            "benefit": "為後續優化提供數據基礎",
            "enabled": True,
            "status": "active",
            "metric": f"{trace_summary.get('trace_count', 0)} 筆軌跡",
        },
        {
            "priority": "P3",
            "id": "reflection_trace",
            "label": "反思鏈路追蹤",
            "benefit": "定位慢反思與低改進幅度瓶頸",
            "enabled": True,
            "status": "active" if reflection_trace.get("tasks_analyzed", 0) >= 1 else "idle",
            "metric": (
                f"均 {reflection_trace.get('avg_iterations') or '—'} 輪 · "
                f"Δ{reflection_trace.get('avg_score_delta') if reflection_trace.get('avg_score_delta') is not None else '—'}"
            ),
        },
    ]

    return {
        "roadmap": roadmap,
        "stage_router": stage_mapping,
        "reflection": reflection_cfg,
        "merge_review_synth": {"enabled": merge_enabled},
        "llm_cache": {
            **cache_stats,
            "hit_rate": hit_rate,
            "semantic_enabled": semantic_on,
            "max_size": int(os.getenv("EVOL_LLM_CACHE_SIZE", "512")),
        },
        "routing_feedback": routing,
        "cost_speed": cost_speed,
        "user_feedback": user_fb,
        "feedback_analysis": fb_analysis,
        "model_calls": model_calls,
        "reflection_trace": reflection_trace,
        "edge_cache": edge_cache,
        "opc_edge": edge_cache,  # 向後相容舊前端欄位
        "system_stats": system_stats,
        "trace": trace_summary,
    }
