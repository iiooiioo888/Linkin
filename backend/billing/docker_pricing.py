"""方案分級 Docker 定價：基準費率 × 方案倍率，含每月免費運行時數。"""

from __future__ import annotations

import os
from typing import Any

from backend.billing.plans import get_plan, normalize_plan_id
from backend.company.docker_tools import DOCKER_SERVICE_HOURLY_RATES, DEFAULT_HOURLY_RATE, get_service_hourly_rate


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def get_plan_docker_terms(plan_id: str | None = None) -> dict[str, Any]:
    """解析方案 Docker 條款（支援環境變數覆寫）。

    環境變數（可選）：
    - LINKIN_DOCKER_MULT_<PLAN> — 費率倍率（1.0 = 牌價）
    - LINKIN_DOCKER_INCLUDED_<PLAN> — 每月含 Docker 運行小時
    """
    plan = get_plan(normalize_plan_id(plan_id or "free"))
    pid = str(plan["id"])
    default_mult = float(plan.get("docker_rate_multiplier", 1.0))
    default_included = float(plan.get("docker_included_hours_per_month", 0))
    mult = _env_float(f"LINKIN_DOCKER_MULT_{pid.upper()}", default_mult)
    included = _env_float(f"LINKIN_DOCKER_INCLUDED_{pid.upper()}", default_included)
    return {
        "plan_id": pid,
        "plan_name_zh": plan.get("name_zh", pid),
        "rate_multiplier": round(max(0.0, mult), 4),
        "included_hours_per_month": round(max(0.0, included), 4),
        "description_zh": plan.get("docker_description_zh", ""),
    }


def get_effective_hourly_rate(service: str, plan_id: str | None = None) -> float:
    """方案調整後的小時費率（USD/小時）。"""
    base = get_service_hourly_rate(service)
    terms = get_plan_docker_terms(plan_id)
    return round(base * terms["rate_multiplier"], 6)


def base_hourly_rates() -> dict[str, float]:
    """基準牌價（未套用方案倍率）。"""
    return dict(DOCKER_SERVICE_HOURLY_RATES)


def split_docker_runtime(
    delta_hours: float,
    plan_id: str | None,
    included_used_hours: float,
) -> dict[str, Any]:
    """將運行時長拆成含額內（免費）與超額（計費）。"""
    delta = max(0.0, float(delta_hours))
    terms = get_plan_docker_terms(plan_id)
    allowance = terms["included_hours_per_month"]
    used = max(0.0, float(included_used_hours))
    remaining = max(0.0, allowance - used)
    free_hours = min(delta, remaining)
    billable_hours = max(0.0, delta - free_hours)
    return {
        "free_hours": round(free_hours, 6),
        "billable_hours": round(billable_hours, 6),
        "included_used_before": round(used, 6),
        "included_remaining_before": round(remaining, 6),
        "included_used_after": round(used + free_hours, 6),
        "included_remaining_after": round(max(0.0, allowance - used - free_hours), 6),
        **terms,
    }


def compute_docker_charge_usd(
    service: str,
    delta_hours: float,
    plan_id: str | None,
    included_used_hours: float,
) -> dict[str, Any]:
    """計算單次結算 USD 成本與用量拆分。"""
    split = split_docker_runtime(delta_hours, plan_id, included_used_hours)
    rate = get_effective_hourly_rate(service, plan_id)
    base_rate = get_service_hourly_rate(service)
    billable = split["billable_hours"]
    cost_usd = round(rate * billable, 6)
    return {
        **split,
        "service": service,
        "delta_hours": round(max(0.0, float(delta_hours)), 6),
        "base_rate_per_hour_usd": base_rate,
        "effective_rate_per_hour_usd": rate,
        "cost_usd": cost_usd,
    }
