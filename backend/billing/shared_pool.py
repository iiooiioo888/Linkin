"""共享池 v6.0 Phase 2 — 貢獻者 Key 清單、健康檢查、配額與 ToS 護欄。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

from backend.billing.pool_store import get_pool_store
from backend.billing.pool_types import VENDOR_TIER_WEIGHTS
from backend.billing.vendor_configs import detect_vendor

TosClass = Literal["self_host", "resale_allowed"]
HealthStatus = Literal["healthy", "degraded", "offline", "unhealthy"]

ALLOWED_TOS: frozenset[str] = frozenset({"self_host", "resale_allowed"})
OFFLINE_HEALTH_THRESHOLD = 0.3
DEGRADED_HEALTH_THRESHOLD = 0.5
QUOTA_BUFFER_RATIO = 1.3


def _utc_hour() -> int:
    return datetime.now(timezone.utc).hour


def _parse_limits(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _vendor_weight(vendor_id: str, vendor_configs: dict[str, Any]) -> float:
    vc = vendor_configs.get(vendor_id) or vendor_configs.get("self_host") or {}
    tier = str(vc.get("tier", "标准"))
    return float(vc.get("routing_weight", VENDOR_TIER_WEIGHTS.get(tier, 1.0)))


def _is_within_active_hours(limits: dict[str, Any], hour: int | None = None) -> bool:
    h = _utc_hour() if hour is None else hour
    active = limits.get("active_hours")
    if isinstance(active, list) and len(active) >= 2:
        start, end = int(active[0]), int(active[1])
        if start <= end:
            return start <= h <= end
        return h >= start or h <= end
    hours_str = limits.get("hours")
    if isinstance(hours_str, str) and "-" in hours_str:
        start_s, end_s = hours_str.split("-", 1)
        start, end = int(start_s), int(end_s)
        return start <= h <= end
    return True


def _tos_allowed(limits: dict[str, Any]) -> bool:
    tos = str(limits.get("tos_class", limits.get("tos", "self_host"))).lower()
    if tos in ALLOWED_TOS:
        return True
    vendor = str(limits.get("vendor_id", "self_host"))
    return vendor == "self_host"


def _health_status_from_row(health: dict[str, Any] | None) -> HealthStatus:
    if not health:
        return "healthy"
    score = float(health.get("health_score", 1.0))
    status = str(health.get("status", "healthy"))
    if status == "offline" or score < OFFLINE_HEALTH_THRESHOLD:
        return "offline"
    if status in {"unhealthy", "degraded"} or score < DEGRADED_HEALTH_THRESHOLD:
        return "degraded" if score >= OFFLINE_HEALTH_THRESHOLD else "unhealthy"
    return "healthy"


def evaluate_key_health(key_id: str, *, force_offline: bool = False) -> dict[str, Any]:
    """健康檢查：成功率、延遲、限流 → healthy / degraded / offline。"""
    store = get_pool_store()
    with store._conn() as conn:
        row = conn.execute("SELECT * FROM key_health WHERE key_id=?", (key_id,)).fetchone()
        latency_ms = conn.execute(
            """SELECT AVG(CAST(json_extract(meta_json, '$.latency_ms') AS REAL)) AS avg_ms
               FROM pool_usage_events WHERE key_id=? AND created_at > datetime('now', '-1 day')""",
            (key_id,),
        ).fetchone()
        rate_limits = conn.execute(
            """SELECT COUNT(*) AS c FROM pool_usage_events
               WHERE key_id=? AND json_extract(meta_json, '$.rate_limited') = 1
               AND created_at > datetime('now', '-1 hour')""",
            (key_id,),
        ).fetchone()
    health = dict(row) if row else {}
    failure_count = int(health.get("failure_count") or 0)
    balance_exhausted = int(health.get("balance_exhausted_count") or 0)
    total_events = max(1, failure_count + balance_exhausted + 10)
    success_rate = round(1.0 - failure_count / total_events, 4)
    avg_latency = float(latency_ms["avg_ms"] or 0) if latency_ms else 0.0
    rate_limit_hits = int(rate_limits["c"] or 0) if rate_limits else 0

    status = _health_status_from_row(health)
    if force_offline or rate_limit_hits >= 5:
        status = "offline"
    elif avg_latency > 5000 or success_rate < 0.85:
        status = "degraded" if status == "healthy" else status

    score = float(health.get("health_score", 1.0))
    if status == "offline":
        score = min(score, OFFLINE_HEALTH_THRESHOLD - 0.01)
    elif status == "degraded":
        score = min(score, DEGRADED_HEALTH_THRESHOLD)

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with store._conn() as conn:
        conn.execute(
            """INSERT INTO key_health(key_id, contributor_id, health_score, failure_count,
               last_failure_at, last_failure_reason, balance_exhausted_count, status, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(key_id) DO UPDATE SET
               health_score=excluded.health_score, status=excluded.status, updated_at=excluded.updated_at""",
            (
                key_id,
                health.get("contributor_id"),
                score,
                failure_count,
                health.get("last_failure_at"),
                health.get("last_failure_reason"),
                balance_exhausted,
                status,
                now,
            ),
        )
    return {
        "key_id": key_id,
        "status": status,
        "health_score": score,
        "success_rate": success_rate,
        "avg_latency_ms": round(avg_latency, 2),
        "rate_limit_hits_1h": rate_limit_hits,
        "offline": status == "offline",
    }


def list_shared_pool_keys(
    *,
    model: str,
    estimate_credits: float,
    account_id: str | None = None,
    org_id: str | None = None,
    include_platform_default: bool = True,
) -> list[dict[str, Any]]:
    """列出符合模型／配額／ToS／時段的可路由 Key。"""
    store = get_pool_store()
    vendor_configs = store.active_vendor_config().get("config", {})
    target_vendor = detect_vendor(model)
    min_quota = estimate_credits * QUOTA_BUFFER_RATIO
    resolved_org = org_id
    if account_id and not resolved_org:
        with store._conn() as conn:
            urow = conn.execute("SELECT kyc_meta_json FROM users WHERE user_id=?", (account_id.strip(),)).fetchone()
            if urow and urow["kyc_meta_json"]:
                meta = _parse_limits(urow["kyc_meta_json"])
                resolved_org = meta.get("org_id") or resolved_org

    candidates: list[dict[str, Any]] = []
    with store._conn() as conn:
        rows = conn.execute(
            """SELECT ak.key_id, ak.contributor_id, ak.org_id, ak.limits_json, ak.status,
                      c.account_id AS contributor_account,
                      kh.health_score, kh.status AS health_status, kh.failure_count,
                      kcp.affinity_score
               FROM api_keys ak
               JOIN contributors c ON c.contributor_id = ak.contributor_id
               LEFT JOIN key_health kh ON kh.key_id = ak.key_id
               LEFT JOIN key_cache_profile kcp ON kcp.key_id = ak.key_id
               WHERE ak.status='active' AND c.status='active'"""
        ).fetchall()

    for row in rows:
        limits = _parse_limits(row["limits_json"])
        if not _tos_allowed(limits):
            continue
        if not _is_within_active_hours(limits):
            continue
        vendor_id = str(limits.get("vendor_id", "self_host"))
        if vendor_id != target_vendor and target_vendor != "self_host":
            models = limits.get("models") or []
            if models and model not in models and "default" not in models:
                continue
        health = evaluate_key_health(str(row["key_id"]))
        if health["offline"]:
            continue
        daily_cap = float(limits.get("daily_token_cap", limits.get("daily_cap", 0)) or 0)
        used_today = store.get_key_daily_usage(str(row["key_id"]))
        quota_remaining = daily_cap - used_today if daily_cap > 0 else estimate_credits * 10
        if daily_cap > 0 and quota_remaining < min_quota:
            continue
        key_org = row["org_id"] or limits.get("org_id")
        candidates.append(
            {
                "key_id": str(row["key_id"]),
                "contributor_id": str(row["contributor_id"]),
                "contributor_account": str(row["contributor_account"]),
                "org_id": key_org,
                "same_org": bool(resolved_org and key_org and resolved_org == key_org),
                "vendor_id": vendor_id,
                "vendor_tier": (vendor_configs.get(vendor_id) or {}).get("tier", "标准"),
                "routing_weight": _vendor_weight(vendor_id, vendor_configs),
                "models": limits.get("models") or [],
                "min_price": float(limits.get("min_price", 0) or 0),
                "concurrency_limit": int(limits.get("concurrency", limits.get("concurrency_limit", 1)) or 1),
                "concurrency_in_use": store.get_key_concurrency(str(row["key_id"])),
                "quota_remaining": quota_remaining,
                "daily_token_cap": daily_cap,
                "cache_affinity": float(row["affinity_score"] or 0),
                "health_score": float(health["health_score"]),
                "health_status": health["status"],
                "success_rate": health["success_rate"],
                "avg_latency_ms": health["avg_latency_ms"],
            }
        )

    if include_platform_default:
        default_id = os.environ.get("LINKIN_DEFAULT_API_KEY_ID", "platform_default")
        vc = vendor_configs.get(target_vendor, vendor_configs.get("self_host", {}))
        tier = str(vc.get("tier", "标准"))
        candidates.append(
            {
                "key_id": default_id,
                "contributor_id": None,
                "contributor_account": None,
                "org_id": resolved_org,
                "same_org": True,
                "vendor_id": target_vendor,
                "vendor_tier": tier,
                "routing_weight": float(vc.get("routing_weight", VENDOR_TIER_WEIGHTS.get(tier, 1.0))),
                "models": ["default"],
                "min_price": 0.0,
                "concurrency_limit": 999,
                "concurrency_in_use": 0,
                "quota_remaining": estimate_credits * 100,
                "daily_token_cap": 0,
                "cache_affinity": 0.0,
                "health_score": 1.0,
                "health_status": "healthy",
                "success_rate": 1.0,
                "avg_latency_ms": 0.0,
                "is_platform_default": True,
            }
        )
    return candidates


def sort_keys_for_routing(keys: list[dict[str, Any]], *, model: str, estimate_credits: float) -> list[dict[str, Any]]:
    """排序：quota≥est×1.3 → model → cache → price → quality → concurrency → vendor weight。"""

    def sort_key(k: dict[str, Any]) -> tuple:
        models = k.get("models") or []
        model_match = model in models or "default" in models or not models
        quota_ok = float(k.get("quota_remaining", 0)) >= estimate_credits * QUOTA_BUFFER_RATIO
        concurrency_avail = int(k.get("concurrency_limit", 1)) - int(k.get("concurrency_in_use", 0))
        return (
            -int(quota_ok),
            -int(model_match),
            -int(k.get("same_org", False)),
            -float(k.get("cache_affinity", 0)),
            float(k.get("min_price", 0)),
            -float(k.get("health_score", 0)),
            -max(0, concurrency_avail),
            -float(k.get("routing_weight", 1.0)),
        )

    return sorted(keys, key=sort_key)
