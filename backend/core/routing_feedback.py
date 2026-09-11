"""路由自適應反饋（P2）。

記錄 simple / company 路由結果與最終品質分數，
動態調整複雜度判斷門檻，長期提升路由準確率。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

RouteChoice = Literal["simple", "company"]
QueryBucket = Literal["short", "medium", "long"]

_DEFAULT_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "routing_feedback.json"
)
_FEEDBACK_PATH = Path(os.getenv("EVOL_ROUTING_FEEDBACK_PATH", str(_DEFAULT_PATH)))
_MAX_RECORDS = int(os.getenv("EVOL_ROUTING_FEEDBACK_MAX", "200"))
_LENGTH_BIAS = float(os.getenv("EVOL_ROUTING_LENGTH_BIAS", "0"))  # 額外字數門檻偏移
_last_threshold_log: tuple[str, int, int] | None = None  # 節流：僅在門檻變動時記 INFO
_WEIGHT_MIN_SAMPLES = int(os.getenv("EVOL_ROUTING_WEIGHT_MIN", "5"))
_WEIGHT_MARGIN = float(os.getenv("EVOL_ROUTING_WEIGHT_MARGIN", "0.15"))


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
    if _FEEDBACK_PATH.exists():
        try:
            with open(_FEEDBACK_PATH, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                return data
        except Exception as exc:
            logger.warning("讀取路由反饋失敗：%s", exc)
    return {"records": [], "stats": {"simple": 0, "company": 0}}


def _save_store(data: dict[str, Any]) -> None:
    _FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_FEEDBACK_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def record_outcome(
    route: RouteChoice,
    query_length: int,
    score: float,
    success: bool,
    *,
    bucket: QueryBucket | str | None = None,
    complexity: str | None = None,
) -> None:
    """記錄一次路由結果（供後續自適應調整）。"""
    store = _ensure_store()
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
    _save_store(store)


def adaptive_length_threshold(base_length: int = 200) -> int:
    """依歷史反饋調整複雜度字數門檻。

    - simple 路由但低分（<6）→ 提高門檻（更早走 company）
    - company 路由但高分（>=8）且 query 短 → 略降門檻
    """
    store = _ensure_store()
    records = store.get("records", [])
    if len(records) < 10:
        return max(50, base_length + int(_LENGTH_BIAS))

    recent = records[-50:]
    simple_miss = [
        r for r in recent
        if r.get("route") == "simple" and float(r.get("score", 0)) < 6.0
    ]
    company_over = [
        r for r in recent
        if r.get("route") == "company"
        and float(r.get("score", 0)) >= 8.0
        and int(r.get("query_length", 0)) < base_length
    ]

    adjusted = base_length + int(_LENGTH_BIAS)
    global _last_threshold_log
    if len(simple_miss) >= 3:
        adjusted += 30
        if _last_threshold_log != ("simple", base_length, adjusted):
            logger.info(
                "路由自適應：simple 低分 %d 次，字數門檻 %d → %d",
                len(simple_miss), base_length, adjusted,
            )
            _last_threshold_log = ("simple", base_length, adjusted)
        else:
            logger.debug("路由自適應（重複）：simple 低分 %d 次，門檻維持 %d", len(simple_miss), adjusted)
    elif len(company_over) >= 5:
        adjusted = max(80, adjusted - 20)
        if _last_threshold_log != ("company", base_length, adjusted):
            logger.info(
                "路由自適應：company 過度路由 %d 次，字數門檻 %d → %d",
                len(company_over), base_length, adjusted,
            )
            _last_threshold_log = ("company", base_length, adjusted)
        else:
            logger.debug("路由自適應（重複）：company 過度路由 %d 次，門檻維持 %d", len(company_over), adjusted)

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

    return {
        "total": len(records),
        "simple_count": len(simple),
        "company_count": len(company),
        "simple_avg_score": _avg(simple, "score"),
        "company_avg_score": _avg(company, "score"),
        "adaptive_length_threshold": adaptive_length_threshold(),
        "stats": store.get("stats", {}),
    }
