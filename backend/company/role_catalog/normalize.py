"""角色目錄的 id／欄位正規化與 runtime 合併（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .constants import (
    BUDGET_USD_FIELDS,
    CATEGORY_VALUES,
    DEFAULT_RUNTIME,
    LEVEL_LABELS,
    ROUTING_STRATEGIES,
    TIER_VALUES,
)


def _sanitize_id(raw: str) -> str:
    text = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    return text


def _normalize_tier(value: Any, fallback: str = "routine") -> str:
    text = str(value or fallback).strip().lower()
    return text if text in TIER_VALUES else fallback


def _normalize_category(value: Any, fallback: str = "management") -> str:
    text = str(value or fallback).strip().lower()
    return text if text in CATEGORY_VALUES else fallback


def _normalize_level(value: Any, fallback: int = 3) -> int:
    try:
        level = int(value)
    except (TypeError, ValueError):
        return fallback
    return level if level in LEVEL_LABELS else fallback


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _clamp_float(value: Any, fallback: float, lo: float, hi: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, number))


def _clamp_int(value: Any, fallback: int, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, number))


def _normalize_routing(value: Any, fallback: str = "quality_first") -> str:
    text = str(value or fallback).strip().lower()
    return text if text in ROUTING_STRATEGIES else fallback


def _runtime_defaults() -> dict[str, Any]:
    return deepcopy(DEFAULT_RUNTIME)


def _merge_runtime(target: dict[str, Any], source: dict[str, Any] | None) -> dict[str, Any]:
    if not source:
        return target
    if source.get("preferred_model") is not None:
        target["preferred_model"] = str(source.get("preferred_model") or "").strip()
    if source.get("preferred_provider") is not None:
        target["preferred_provider"] = str(source.get("preferred_provider") or "").strip().lower()
    for field in BUDGET_USD_FIELDS:
        if source.get(field) is not None:
            target[field] = max(0.0, float(source[field] or 0))
    if source.get("tools_allowed") is not None:
        target["tools_allowed"] = _as_str_list(source.get("tools_allowed"))
    if source.get("notes") is not None:
        target["notes"] = str(source.get("notes") or "")
    if "enabled" in source:
        target["enabled"] = bool(source["enabled"])
    if "alert_on_error" in source:
        target["alert_on_error"] = bool(source["alert_on_error"])
    if "alert_on_budget" in source:
        target["alert_on_budget"] = bool(source["alert_on_budget"])
    if "alert_on_sla" in source:
        target["alert_on_sla"] = bool(source["alert_on_sla"])
    if source.get("temperature") is not None:
        target["temperature"] = _clamp_float(source.get("temperature"), target.get("temperature", 0.7), 0.0, 2.0)
    if source.get("max_output_tokens") is not None:
        target["max_output_tokens"] = _clamp_int(source.get("max_output_tokens"), 4096, 256, 128000)
    if source.get("timeout_ms") is not None:
        target["timeout_ms"] = _clamp_int(source.get("timeout_ms"), 120000, 5000, 600000)
    if source.get("routing_strategy") is not None:
        target["routing_strategy"] = _normalize_routing(
            source.get("routing_strategy"), target.get("routing_strategy", "quality_first")
        )
    if source.get("failover_models") is not None:
        target["failover_models"] = _as_str_list(source.get("failover_models"))
    if source.get("sla_latency_ms") is not None:
        target["sla_latency_ms"] = _clamp_int(source.get("sla_latency_ms"), 0, 0, 600000)
    if source.get("max_retries") is not None:
        target["max_retries"] = _clamp_int(source.get("max_retries"), 3, 0, 8)
    if source.get("language") is not None:
        lang = str(source.get("language") or "zh-TW").strip() or "zh-TW"
        target["language"] = lang[:16]
    if "always_require_review" in source:
        target["always_require_review"] = bool(source["always_require_review"])
    if source.get("priority") is not None:
        target["priority"] = _clamp_int(source.get("priority"), 3, 1, 5)
    if source.get("description") is not None:
        target["description"] = str(source.get("description") or "")[:240]
    if source.get("max_daily_items") is not None:
        target["max_daily_items"] = _clamp_int(source.get("max_daily_items"), 0, 0, 500)
    for flag in (
        "require_human_approval",
        "stream_enabled",
        "cache_enabled",
        "pii_redact",
        "mainland_only",
        "on_call",
        "allow_tool_use",
        "auto_escalate",
    ):
        if flag in source:
            target[flag] = bool(source[flag])
    if source.get("heartbeat_sec") is not None:
        target["heartbeat_sec"] = _clamp_int(source.get("heartbeat_sec"), 0, 0, 3600)
    if source.get("tags") is not None:
        target["tags"] = _as_str_list(source.get("tags"))[:16]
    if source.get("notify_channel") is not None:
        target["notify_channel"] = str(source.get("notify_channel") or "")[:64]
    if source.get("quiet_hours") is not None:
        target["quiet_hours"] = str(source.get("quiet_hours") or "")[:32]
    if source.get("context_window") is not None:
        target["context_window"] = _clamp_int(source.get("context_window"), 0, 0, 2_000_000)
    return target
