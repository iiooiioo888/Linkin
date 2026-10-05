"""路由自適應反饋（P2）。

記錄 simple / company 路由結果與最終品質分數，
依 cost_speed 配置在「升 tier／多加反思」與「推向 company」之間分級，
並以今日 company 占比護欄避免過度升級路徑。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger(__name__)

RouteChoice = Literal["simple", "company"]
QueryBucket = Literal["short", "medium", "long"]

_EXCLUDED_EXECUTION_PATHS = frozenset({"minecraft_ops", "opc"})


def routing_feedback_applies(
    *,
    execution_path: str | None = None,
    route: RouteChoice | None = None,
) -> bool:
    """routing_feedback 僅作用於 simple／company 閉環，不影響輕量 minecraft_ops 等路徑。"""
    path = str(execution_path or "").strip().lower()
    if path in _EXCLUDED_EXECUTION_PATHS:
        return False
    return route is None or route in ("simple", "company")

_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "routing_feedback.json"
)


def _feedback_path() -> Path:
    return Path(os.getenv("EVOL_ROUTING_FEEDBACK_PATH", str(_DEFAULT_PATH)))
_MAX_RECORDS = int(os.getenv("EVOL_ROUTING_FEEDBACK_MAX", "200"))
_LENGTH_BIAS = float(os.getenv("EVOL_ROUTING_LENGTH_BIAS", "0"))  # 額外字數門檻偏移
_last_threshold_log: tuple[str, int, int] | None = None  # 節流：僅在門檻變動時記 INFO
_WEIGHT_MIN_SAMPLES = int(os.getenv("EVOL_ROUTING_WEIGHT_MIN", "5"))
_WEIGHT_MARGIN = float(os.getenv("EVOL_ROUTING_WEIGHT_MARGIN", "0.15"))

_DEFAULT_FEEDBACK_TIMEZONE = "Asia/Taipei"

_DEFAULT_FEEDBACK_CFG: dict[str, Any] = {
    "feedback_enabled": True,
    "timezone": _DEFAULT_FEEDBACK_TIMEZONE,
    "max_company_ratio": 0.35,
    "consecutive_low_scores_for_company": 3,
    "low_score_threshold": 6.0,
    "simple_miss_window": 50,
    "simple_miss_count_for_escalate": 3,
    "length_threshold_step": 30,
    "length_threshold_relax_step": 20,
    "min_length_threshold": 80,
    "company_ratio_min_samples": 10,
}


def _feedback_config() -> dict[str, Any]:
    try:
        from backend.core.cost_speed_router import routing_feedback_settings

        return routing_feedback_settings()
    except Exception:
        return dict(_DEFAULT_FEEDBACK_CFG)


def _feedback_timezone() -> ZoneInfo:
    """今日 company 占比護欄的日界（IANA）。環境變數優先於 cost_speed.json。"""
    cfg = _feedback_config()
    tz_name = os.getenv("EVOL_ROUTING_FEEDBACK_TIMEZONE", "").strip()
    if not tz_name:
        tz_name = str(cfg.get("timezone") or _DEFAULT_FEEDBACK_TIMEZONE).strip()
    if not tz_name:
        tz_name = _DEFAULT_FEEDBACK_TIMEZONE
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        logger.warning(
            "無效的 routing_feedback timezone：%s，改用 %s",
            tz_name,
            _DEFAULT_FEEDBACK_TIMEZONE,
        )
        return ZoneInfo(_DEFAULT_FEEDBACK_TIMEZONE)


def feedback_today() -> date:
    """routing_feedback 統計用的「今日」日期（依配置時區，預設 Asia/Taipei）。"""
    return datetime.now(_feedback_timezone()).date()


def query_bucket(query_length: int) -> QueryBucket:
    """依查詢長度分桶，供加權路由統計。"""
    if query_length < 80:
        return "short"
    if query_length < 200:
        return "medium"
    return "long"


def weighted_routing_enabled() -> bool:
    return os.getenv("EVOL_ROUTING_WEIGHT_ENABLED", "true").lower() not in {"0", "false", "no"}


def _ensure_store() -> dict[str, Any]:
    path = _feedback_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                return data
        except Exception as exc:
            logger.warning("讀取路由反饋失敗：%s", exc)
    return {"records": [], "stats": {"simple": 0, "company": 0}, "meta": {}}


def _save_store(data: dict[str, Any]) -> None:
    path = _feedback_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _meta(store: dict[str, Any]) -> dict[str, Any]:
    meta = store.setdefault("meta", {})
    if not isinstance(meta, dict):
        meta = {}
        store["meta"] = meta
    today = feedback_today().isoformat()
    if meta.get("today_date") != today:
        meta["today_date"] = today
        meta["today_simple"] = 0
        meta["today_company"] = 0
    return meta


def _is_low_simple_score(score: float, cfg: dict[str, Any]) -> bool:
    threshold = float(cfg.get("low_score_threshold") or 6.0)
    return score < threshold


def _today_company_ratio(meta: dict[str, Any]) -> float:
    simple = int(meta.get("today_simple") or 0)
    company = int(meta.get("today_company") or 0)
    total = simple + company
    if total <= 0:
        return 0.0
    return round(company / total, 4)


def _today_route_sample_count(meta: dict[str, Any]) -> int:
    return int(meta.get("today_simple") or 0) + int(meta.get("today_company") or 0)


def _company_ratio_cap_reached(meta: dict[str, Any], cfg: dict[str, Any]) -> bool:
    min_samples = int(cfg.get("company_ratio_min_samples") or 10)
    if _today_route_sample_count(meta) < min_samples:
        return False
    max_ratio = float(cfg.get("max_company_ratio") or 1.0)
    return _today_company_ratio(meta) >= max_ratio


def feedback_upgrade_state(store: dict[str, Any] | None = None) -> dict[str, Any]:
    """目前回饋驅動的升級狀態（供監控與路由附掛）。"""
    cfg = _feedback_config()
    data = store if store is not None else _ensure_store()
    meta = _meta(data)
    consecutive = int(meta.get("consecutive_simple_low") or 0)
    need_for_company = int(cfg.get("consecutive_low_scores_for_company") or 3)
    ratio = _today_company_ratio(meta)
    sample_count = _today_route_sample_count(meta)
    min_samples = int(cfg.get("company_ratio_min_samples") or 10)
    max_ratio = float(cfg.get("max_company_ratio") or 1.0)
    samples_sufficient = sample_count >= min_samples
    cap_hit = _company_ratio_cap_reached(meta, cfg)
    tier_bump = bool(cfg.get("feedback_enabled")) and consecutive >= 1
    extra_reflection = bool(cfg.get("feedback_enabled")) and consecutive >= 2
    company_escalation_allowed = (
        bool(cfg.get("feedback_enabled"))
        and consecutive >= need_for_company
        and not cap_hit
    )
    return {
        "feedback_enabled": bool(cfg.get("feedback_enabled", True)),
        "consecutive_simple_low": consecutive,
        "consecutive_low_scores_for_company": need_for_company,
        "tier_bump_active": tier_bump,
        "extra_reflection_active": extra_reflection,
        "company_escalation_allowed": company_escalation_allowed,
        "today_company_ratio": ratio,
        "today_route_sample_count": sample_count,
        "company_ratio_min_samples": min_samples,
        "company_ratio_samples_sufficient": samples_sufficient,
        "max_company_ratio": max_ratio,
        "company_ratio_cap_hit": cap_hit,
        "low_score_threshold": float(cfg.get("low_score_threshold") or 6.0),
    }


def cost_speed_complexity_boost(
    complexity: str | None,
    *,
    execution_path: str | None = None,
) -> str | None:
    """simple 路徑低分時先升 cost_speed 複雜度桶（對應更高 tier 模型）。"""
    if not routing_feedback_applies(execution_path=execution_path):
        return complexity
    if complexity != "simple":
        return complexity
    state = feedback_upgrade_state()
    if not state.get("tier_bump_active"):
        return complexity
    return "medium"


def extra_reflection_rounds(*, execution_path: str | None = None) -> int:
    """低分回饋時為簡單路徑多加一輪反思（在 EVOL_SIMPLE_MAX_ITERATIONS 之上）。"""
    if not routing_feedback_applies(execution_path=execution_path):
        return 0
    state = feedback_upgrade_state()
    return 1 if state.get("extra_reflection_active") else 0


def record_outcome(
    route: RouteChoice,
    query_length: int,
    score: float,
    success: bool,
    *,
    bucket: QueryBucket | str | None = None,
    complexity: str | None = None,
    execution_path: str | None = None,
) -> None:
    """記錄一次路由結果（供後續自適應調整）。"""
    if not routing_feedback_applies(execution_path=execution_path, route=route):
        return
    cfg = _feedback_config()
    store = _ensure_store()
    meta = _meta(store)
    records: list[dict[str, Any]] = store.setdefault("records", [])
    records.append({
        "route": route,
        "query_length": query_length,
        "bucket": bucket or query_bucket(query_length),
        "complexity": complexity or "",
        "score": round(score, 2),
        "success": success,
    })
    if len(records) > _MAX_RECORDS:
        store["records"] = records[-_MAX_RECORDS:]
    stats = store.setdefault("stats", {"simple": 0, "company": 0})
    stats[route] = int(stats.get(route, 0)) + 1
    if route == "simple":
        meta["today_simple"] = int(meta.get("today_simple") or 0) + 1
    else:
        meta["today_company"] = int(meta.get("today_company") or 0) + 1

    if bool(cfg.get("feedback_enabled", True)) and route == "simple":
        if _is_low_simple_score(float(score), cfg):
            meta["consecutive_simple_low"] = int(meta.get("consecutive_simple_low") or 0) + 1
        else:
            meta["consecutive_simple_low"] = 0
    elif route == "simple" and success:
        meta["consecutive_simple_low"] = 0

    _save_store(store)


def adaptive_length_threshold(base_length: int = 200) -> int:
    """依歷史反饋調整複雜度字數門檻（僅在允許推向 company 時提高門檻）。

    升級順序（由 record_outcome 累計 consecutive_simple_low）：
      1+ → cost_speed 複雜度／模型 tier 上調
      2+ → 簡單路徑多加 1 輪反思
      N+ 且未達今日 company 占比上限 → 才提高字數門檻（更早走 company）
    """
    cfg = _feedback_config()
    base = max(50, base_length + int(_LENGTH_BIAS))
    if not bool(cfg.get("feedback_enabled", True)):
        return base

    store = _ensure_store()
    upgrade = feedback_upgrade_state(store)
    if not upgrade.get("company_escalation_allowed"):
        return base

    records = store.get("records", [])
    if len(records) < 10:
        return base

    window = int(cfg.get("simple_miss_window") or 50)
    recent = records[-window:]
    simple_miss = [
        r for r in recent
        if r.get("route") == "simple"
        and float(r.get("score", 0)) < float(cfg.get("low_score_threshold") or 6.0)
    ]
    company_over = [
        r for r in recent
        if r.get("route") == "company"
        and float(r.get("score", 0)) >= 8.0
        and int(r.get("query_length", 0)) < base_length
    ]

    step_up = int(cfg.get("length_threshold_step") or 30)
    step_down = int(cfg.get("length_threshold_relax_step") or 20)
    min_len = int(cfg.get("min_length_threshold") or 80)
    miss_need = int(cfg.get("simple_miss_count_for_escalate") or 3)

    adjusted = base
    global _last_threshold_log
    if len(simple_miss) >= miss_need:
        adjusted += step_up
        if _last_threshold_log != ("simple", base_length, adjusted):
            logger.info(
                "路由自適應：simple 低分 %d 次且連續低分達標，字數門檻 %d → %d",
                len(simple_miss), base_length, adjusted,
            )
            _last_threshold_log = ("simple", base_length, adjusted)
    elif len(company_over) >= 5 and not _company_ratio_cap_reached(_meta(store), cfg):
        adjusted = max(min_len, adjusted - step_down)
        if _last_threshold_log != ("company", base_length, adjusted):
            logger.info(
                "路由自適應：company 過度路由 %d 次，字數門檻 %d → %d",
                len(company_over), base_length, adjusted,
            )
            _last_threshold_log = ("company", base_length, adjusted)

    return adjusted


def routing_stats() -> dict[str, Any]:
    """回傳路由統計摘要（供監控 / API）。"""
    store = _ensure_store()
    records = store.get("records", [])
    simple = [r for r in records if r.get("route") == "simple"]
    company = [r for r in records if r.get("route") == "company"]

    def _avg(items: list[dict], key: str) -> float:
        if not items:
            return 0.0
        return round(sum(float(r.get(key, 0)) for r in items) / len(items), 2)

    upgrade = feedback_upgrade_state(store)
    threshold = adaptive_length_threshold()
    return {
        "total": len(records),
        "simple_count": len(simple),
        "company_count": len(company),
        "simple_avg_score": _avg(simple, "score"),
        "company_avg_score": _avg(company, "score"),
        "adaptive_length_threshold": threshold,
        "stats": store.get("stats", {}),
        "feedback": upgrade,
        "config": _feedback_config(),
    }
