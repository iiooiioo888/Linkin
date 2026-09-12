"""角色目錄：內建角色覆蓋設定 + 自定義角色持久化。

資料檔 `backend/data/role_catalog.json`（可用 EVOL_ROLE_CATALOG_PATH 覆蓋）。
監控中心與公司運行時共用此目錄，編輯角色設定後會套用到後續執行。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from backend.company.raho.protocol import attach_raho_fields
from backend.company.roles import BUILTIN_TEMPLATES, STANDARD_ROLES
from backend.company.state import (
    ROLE_CATEGORY_MAP,
    ROLE_LEVEL,
    BudgetTier,
    RoleCategory,
    RoleType,
)

logger = logging.getLogger(__name__)

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "role_catalog.json"
)

ROLE_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
RESERVED_IDS = {rt.value for rt in RoleType}

LEVEL_LABELS: dict[int, str] = {
    0: "最高決策層",
    1: "技術領導層",
    2: "領域領導層",
    3: "執行層",
    4: "支援角色",
}

CATEGORY_LABELS: dict[str, str] = {
    "ui": "UI 設計",
    "css": "樣式",
    "js": "前端邏輯",
    "backend": "後端",
    "test": "測試",
    "devops": "維運",
    "management": "管理",
    "review": "審查",
    "security": "資安",
    "data": "資料",
    "product": "產品",
    "docs": "文件",
    "mobile": "行動端",
    "research": "研究",
    "ai": "AI / Prompt",
    "legal": "合規",
    "finance": "金融／量化",
    "industrial": "工業／OPC",
    "creative": "創意／敘事",
    "crawler": "爬蟲／採集",
    "platform": "平台／GitHub",
    "hub": "AI Hub",
    "memory": "記憶／知識庫",
    "growth": "成長／客戶成功",
}

TIER_VALUES = {t.value for t in BudgetTier}
CATEGORY_VALUES = {c.value for c in RoleCategory}
ROUTING_STRATEGIES = {"cost_first", "speed_first", "quality_first", "manual"}

# AI 使用預算（LLM API）與雲服務預算（Docker + 阿里雲）分開，0=不限
AI_BUDGET_FIELDS = ("daily_budget_usd", "weekly_budget_usd", "monthly_budget_usd")
CLOUD_BUDGET_FIELDS = (
    "cloud_daily_budget_usd",
    "cloud_weekly_budget_usd",
    "cloud_monthly_budget_usd",
)
BUDGET_USD_FIELDS = AI_BUDGET_FIELDS + CLOUD_BUDGET_FIELDS

DEFAULT_RUNTIME: dict[str, Any] = {
    "preferred_model": "",
    "preferred_provider": "",
    "daily_budget_usd": 0.0,
    "weekly_budget_usd": 0.0,
    "monthly_budget_usd": 0.0,
    "cloud_daily_budget_usd": 0.0,
    "cloud_weekly_budget_usd": 0.0,
    "cloud_monthly_budget_usd": 0.0,
    "tools_allowed": [],
    "notes": "",
    "enabled": True,
    "alert_on_error": True,
    "alert_on_budget": True,
    "alert_on_sla": True,
    "temperature": 0.7,
    "max_output_tokens": 4096,
    "timeout_ms": 120000,
    "routing_strategy": "quality_first",
    "failover_models": [],
    "sla_latency_ms": 0,
    "max_retries": 3,
    "language": "zh-TW",
    "always_require_review": False,
    "priority": 3,
    "description": "",
    "max_daily_items": 0,
    "require_human_approval": False,
    "stream_enabled": True,
    "cache_enabled": True,
    "pii_redact": True,
    "mainland_only": False,
    "heartbeat_sec": 0,
    "on_call": False,
    "tags": [],
    "notify_channel": "",
    "quiet_hours": "",
    "context_window": 0,
    "allow_tool_use": True,
    "auto_escalate": True,
}

DEFAULT_MONITOR_PREFS: dict[str, Any] = {
    "poll_interval_ms": 5000,
    "show_disabled": True,
    "show_idle": True,
    "show_custom_only": False,
    "group_by": "level",
    "compact_cards": False,
    "default_desk_tab": "tasks",
    "sort_by": "level",
    "capacity_warn_pct": 80,
    "show_prompt_preview": True,
    "highlight_alerts": True,
    "auto_open_busy": False,
    "default_layout": "catalog",
    "sound_on_alert": False,
    "show_cost_in_cards": True,
    "pin_role_ids": [],
    "filter_min_level": 0,
    "filter_max_level": 4,
    "timezone": "Asia/Taipei",
    "show_on_call_only": False,
}

_lock = threading.RLock()
_cache: dict[str, Any] | None = None
_cache_mtime: float | None = None


def catalog_path() -> Path:
    return Path(os.getenv("EVOL_ROLE_CATALOG_PATH", str(DEFAULT_CATALOG_PATH)))


def reset_catalog_cache() -> None:
    global _cache, _cache_mtime
    with _lock:
        _cache = None
        _cache_mtime = None


def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "monitor": dict(DEFAULT_MONITOR_PREFS),
        "settings": {},
        "custom": [],
    }


def _load_store() -> dict[str, Any]:
    global _cache, _cache_mtime
    path = catalog_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    if _cache is not None and _cache_mtime == mtime:
        return _cache

    store = _empty_store()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                store["monitor"] = {
                    **DEFAULT_MONITOR_PREFS,
                    **(raw.get("monitor") or {}),
                }
                settings = raw.get("settings") or {}
                if isinstance(settings, dict):
                    store["settings"] = settings
                custom = raw.get("custom") or []
                if isinstance(custom, list):
                    store["custom"] = [c for c in custom if isinstance(c, dict)]
        except (OSError, json.JSONDecodeError):
            logger.warning("讀取角色目錄失敗，改用空白目錄：%s", path, extra={})
    _cache = store
    _cache_mtime = mtime
    return store


def _save_store(store: dict[str, Any]) -> dict[str, Any]:
    global _cache, _cache_mtime
    path = catalog_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "monitor": {**DEFAULT_MONITOR_PREFS, **(store.get("monitor") or {})},
        "settings": store.get("settings") or {},
        "custom": store.get("custom") or [],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    _cache = payload
    try:
        _cache_mtime = path.stat().st_mtime
    except OSError:
        _cache_mtime = None
    return payload


def _templates_for(role_id: str) -> list[str]:
    names: list[str] = []
    try:
        role = RoleType(role_id)
    except ValueError:
        return names
    for key, cfg in BUILTIN_TEMPLATES.items():
        if role in cfg.roles:
            names.append(key)
    return names


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


def _builtin_snapshot(role: RoleType) -> dict[str, Any]:
    definition = STANDARD_ROLES[role]
    level = definition.level if definition.level is not None else ROLE_LEVEL.get(role, 3)
    category = ROLE_CATEGORY_MAP.get(role)
    return attach_raho_fields(
        {
            "id": role.value,
            "name": definition.name,
            "level": level,
            "level_label": LEVEL_LABELS.get(level, "執行層"),
            "category": category.value if category else "management",
            "reporting_to": definition.reporting_to.value if definition.reporting_to else None,
            "can_delegate_to": [r.value for r in definition.can_delegate_to],
            "responsibilities": list(definition.responsibilities),
            "system_prompt": definition.system_prompt or "",
            "max_parallel_work": int(definition.max_parallel_work),
            "default_tier": definition.default_tier.value if definition.default_tier else "routine",
            **_runtime_defaults(),
            "is_custom": False,
            "is_builtin": True,
            "templates": _templates_for(role.value),
        }
    )


def _custom_snapshot(raw: dict[str, Any]) -> dict[str, Any]:
    role_id = _sanitize_id(str(raw.get("id") or ""))
    level = _normalize_level(raw.get("level"), 3)
    return attach_raho_fields(
        {
            "id": role_id,
            "name": str(raw.get("name") or role_id).strip() or role_id,
            "level": level,
            "level_label": LEVEL_LABELS.get(level, "執行層"),
            "category": _normalize_category(raw.get("category"), "management"),
            "reporting_to": (str(raw.get("reporting_to")).strip() if raw.get("reporting_to") else None) or None,
            "can_delegate_to": _as_str_list(raw.get("can_delegate_to")),
            "responsibilities": _as_str_list(raw.get("responsibilities")),
            "system_prompt": str(raw.get("system_prompt") or ""),
            "max_parallel_work": max(1, min(16, int(raw.get("max_parallel_work") or 2))),
            "default_tier": _normalize_tier(raw.get("default_tier"), "routine"),
            **_merge_runtime(_runtime_defaults(), raw),
            "is_custom": True,
            "is_builtin": False,
            "templates": _as_str_list(raw.get("templates")),
        }
    )


def _apply_overlay(base: dict[str, Any], overlay: dict[str, Any] | None) -> dict[str, Any]:
    if not overlay:
        return base
    merged = dict(base)
    if overlay.get("name"):
        merged["name"] = str(overlay["name"]).strip()
    if overlay.get("system_prompt") is not None and str(overlay.get("system_prompt", "")).strip():
        merged["system_prompt"] = str(overlay["system_prompt"])
    if overlay.get("responsibilities"):
        merged["responsibilities"] = _as_str_list(overlay["responsibilities"])
    if overlay.get("default_tier"):
        merged["default_tier"] = _normalize_tier(overlay["default_tier"], merged["default_tier"])
    if overlay.get("max_parallel_work") is not None:
        try:
            merged["max_parallel_work"] = max(1, min(16, int(overlay["max_parallel_work"])))
        except (TypeError, ValueError):
            pass
    if "reporting_to" in overlay:
        reporting = overlay.get("reporting_to")
        merged["reporting_to"] = str(reporting).strip() if reporting else None
    if overlay.get("can_delegate_to") is not None:
        merged["can_delegate_to"] = _as_str_list(overlay["can_delegate_to"])
    if overlay.get("level") is not None:
        merged["level"] = _normalize_level(overlay.get("level"), merged["level"])
        merged["level_label"] = LEVEL_LABELS.get(merged["level"], "執行層")
    if overlay.get("category"):
        merged["category"] = _normalize_category(overlay.get("category"), merged["category"])
    _merge_runtime(merged, overlay)
    return merged


def list_role_snapshots() -> list[dict[str, Any]]:
    """內建 + 自定義角色，套用設定覆蓋後依層級排序。"""
    with _lock:
        store = _load_store()
        settings = store.get("settings") or {}
        snapshots: list[dict[str, Any]] = []
        for role in STANDARD_ROLES:
            base = _builtin_snapshot(role)
            overlay = settings.get(role.value)
            snapshots.append(_apply_overlay(base, overlay if isinstance(overlay, dict) else None))
        for raw in store.get("custom") or []:
            snap = _custom_snapshot(raw)
            if not snap["id"]:
                continue
            overlay = settings.get(snap["id"])
            snapshots.append(_apply_overlay(snap, overlay if isinstance(overlay, dict) else None))

        by_id = {s["id"]: s for s in snapshots}
        for snap in snapshots:
            attach_raho_fields(snap)
            snap["direct_reports"] = [
                other["id"]
                for other in snapshots
                if other.get("reporting_to") == snap["id"]
            ]
            reporting = snap.get("reporting_to")
            if reporting and reporting not in by_id and reporting != "user":
                snap["reporting_to"] = None
        snapshots.sort(
            key=lambda s: (
                0 if s.get("raho_spine") else 1,
                -int(s.get("raho_layer") or 0) if s.get("raho_spine") else int(s.get("level") or 3),
                s["id"],
            )
        )
        return snapshots


def get_snapshot(role_id: str) -> dict[str, Any] | None:
    for snap in list_role_snapshots():
        if snap["id"] == role_id:
            return snap
    return None


def resolve_runtime(role_id: str) -> dict[str, Any]:
    """執行時覆蓋：system_prompt / preferred_model / enabled。"""
    snap = get_snapshot(role_id)
    if snap:
        out = dict(snap)
    else:
        out = {
            "id": role_id,
            "enabled": True,
            "system_prompt": "",
            "preferred_model": "",
            "preferred_provider": "",
            "name": role_id,
        }
    preferred = str(out.get("preferred_model") or "").strip()
    provider = str(out.get("preferred_provider") or "").strip()
    if preferred:
        from backend.core.provider_pool import clamp_model

        out["preferred_model"] = clamp_model(preferred, route_id=provider or None)
    return out


def get_monitor_prefs() -> dict[str, Any]:
    with _lock:
        store = _load_store()
        return {**DEFAULT_MONITOR_PREFS, **(store.get("monitor") or {})}


def update_monitor_prefs(patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        store = deepcopy(_load_store())
        current = {**DEFAULT_MONITOR_PREFS, **(store.get("monitor") or {})}
        if "poll_interval_ms" in patch:
            try:
                interval = int(patch["poll_interval_ms"])
            except (TypeError, ValueError) as exc:
                raise ValueError("poll_interval_ms 必須為整數") from exc
            current["poll_interval_ms"] = max(2000, min(60000, interval))
        for key in (
            "show_disabled",
            "show_idle",
            "show_custom_only",
            "compact_cards",
            "show_prompt_preview",
            "highlight_alerts",
            "auto_open_busy",
        ):
            if key in patch:
                current[key] = bool(patch[key])
        if "group_by" in patch:
            group = str(patch.get("group_by") or "level").strip().lower()
            current["group_by"] = group if group in {"level", "category"} else "level"
        if "default_desk_tab" in patch:
            tab = str(patch.get("default_desk_tab") or "tasks").strip().lower()
            current["default_desk_tab"] = tab if tab in {"tasks", "monitor", "settings", "org"} else "tasks"
        if "sort_by" in patch:
            sort_by = str(patch.get("sort_by") or "level").strip().lower()
            current["sort_by"] = sort_by if sort_by in {"level", "name", "status", "cost", "queue"} else "level"
        if "capacity_warn_pct" in patch:
            current["capacity_warn_pct"] = _clamp_int(patch.get("capacity_warn_pct"), 80, 10, 100)
        if "default_layout" in patch:
            layout = str(patch.get("default_layout") or "catalog").strip().lower()
            current["default_layout"] = layout if layout in {"catalog", "desk", "floor"} else "catalog"
        if "sound_on_alert" in patch:
            current["sound_on_alert"] = bool(patch["sound_on_alert"])
        if "show_cost_in_cards" in patch:
            current["show_cost_in_cards"] = bool(patch["show_cost_in_cards"])
        if "show_on_call_only" in patch:
            current["show_on_call_only"] = bool(patch["show_on_call_only"])
        if "pin_role_ids" in patch:
            current["pin_role_ids"] = _as_str_list(patch.get("pin_role_ids"))[:32]
        if "filter_min_level" in patch:
            current["filter_min_level"] = _clamp_int(patch.get("filter_min_level"), 0, 0, 4)
        if "filter_max_level" in patch:
            current["filter_max_level"] = _clamp_int(patch.get("filter_max_level"), 4, 0, 4)
        if "timezone" in patch:
            tz = str(patch.get("timezone") or "Asia/Taipei").strip() or "Asia/Taipei"
            current["timezone"] = tz[:64]
        store["monitor"] = current
        _save_store(store)
        return current


def _settings_payload(data: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if "enabled" in data:
        payload["enabled"] = bool(data["enabled"])
    if "name" in data:
        payload["name"] = str(data.get("name") or "").strip()
    if "system_prompt" in data:
        payload["system_prompt"] = str(data.get("system_prompt") or "")
    if "responsibilities" in data:
        payload["responsibilities"] = _as_str_list(data.get("responsibilities"))
    if "default_tier" in data:
        payload["default_tier"] = _normalize_tier(data.get("default_tier"), "routine")
    if "max_parallel_work" in data:
        payload["max_parallel_work"] = max(1, min(16, int(data.get("max_parallel_work") or 1)))
    if "preferred_model" in data:
        payload["preferred_model"] = str(data.get("preferred_model") or "").strip()
    if "preferred_provider" in data:
        payload["preferred_provider"] = str(data.get("preferred_provider") or "").strip().lower()
    for field in BUDGET_USD_FIELDS:
        if field in data:
            payload[field] = max(0.0, float(data.get(field) or 0))
    if "tools_allowed" in data:
        payload["tools_allowed"] = _as_str_list(data.get("tools_allowed"))
    if "notes" in data:
        payload["notes"] = str(data.get("notes") or "")
    if "reporting_to" in data:
        reporting = data.get("reporting_to")
        payload["reporting_to"] = str(reporting).strip() if reporting else None
    if "can_delegate_to" in data:
        payload["can_delegate_to"] = _as_str_list(data.get("can_delegate_to"))
    if "alert_on_error" in data:
        payload["alert_on_error"] = bool(data["alert_on_error"])
    if "alert_on_budget" in data:
        payload["alert_on_budget"] = bool(data["alert_on_budget"])
    if "alert_on_sla" in data:
        payload["alert_on_sla"] = bool(data["alert_on_sla"])
    if "temperature" in data:
        payload["temperature"] = _clamp_float(data.get("temperature"), 0.7, 0.0, 2.0)
    if "max_output_tokens" in data:
        payload["max_output_tokens"] = _clamp_int(data.get("max_output_tokens"), 4096, 256, 128000)
    if "timeout_ms" in data:
        payload["timeout_ms"] = _clamp_int(data.get("timeout_ms"), 120000, 5000, 600000)
    if "routing_strategy" in data:
        payload["routing_strategy"] = _normalize_routing(data.get("routing_strategy"))
    if "failover_models" in data:
        payload["failover_models"] = _as_str_list(data.get("failover_models"))
    if "sla_latency_ms" in data:
        payload["sla_latency_ms"] = _clamp_int(data.get("sla_latency_ms"), 0, 0, 600000)
    if "max_retries" in data:
        payload["max_retries"] = _clamp_int(data.get("max_retries"), 3, 0, 8)
    if "language" in data:
        payload["language"] = str(data.get("language") or "zh-TW").strip() or "zh-TW"
    if "always_require_review" in data:
        payload["always_require_review"] = bool(data["always_require_review"])
    if "priority" in data:
        payload["priority"] = _clamp_int(data.get("priority"), 3, 1, 5)
    if "description" in data:
        payload["description"] = str(data.get("description") or "")[:240]
    if "max_daily_items" in data:
        payload["max_daily_items"] = _clamp_int(data.get("max_daily_items"), 0, 0, 500)
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
        if flag in data:
            payload[flag] = bool(data[flag])
    if "heartbeat_sec" in data:
        payload["heartbeat_sec"] = _clamp_int(data.get("heartbeat_sec"), 0, 0, 3600)
    if "tags" in data:
        payload["tags"] = _as_str_list(data.get("tags"))[:16]
    if "notify_channel" in data:
        payload["notify_channel"] = str(data.get("notify_channel") or "")[:64]
    if "quiet_hours" in data:
        payload["quiet_hours"] = str(data.get("quiet_hours") or "")[:32]
    if "context_window" in data:
        payload["context_window"] = _clamp_int(data.get("context_window"), 0, 0, 2_000_000)
    if "level" in data:
        payload["level"] = _normalize_level(data.get("level"), 3)
    if "category" in data:
        payload["category"] = _normalize_category(data.get("category"), "management")
    return payload


def update_role_settings(role_id: str, data: dict[str, Any]) -> dict[str, Any]:
    role_id = _sanitize_id(role_id)
    snap = get_snapshot(role_id)
    if snap is None:
        raise KeyError(f"角色不存在：{role_id}")
    with _lock:
        store = deepcopy(_load_store())
        overlay = dict(store.get("settings") or {})
        merged = {**(overlay.get(role_id) or {}), **_settings_payload(data)}
        overlay[role_id] = merged
        if snap["is_custom"]:
            customs = []
            for item in store.get("custom") or []:
                if _sanitize_id(str(item.get("id") or "")) == role_id:
                    item = {**item, **merged}
                    if merged.get("name"):
                        item["name"] = merged["name"]
                customs.append(item)
            store["custom"] = customs
        store["settings"] = overlay
        _save_store(store)
    result = get_snapshot(role_id)
    assert result is not None
    return result


def reset_role_settings(role_id: str) -> dict[str, Any]:
    role_id = _sanitize_id(role_id)
    snap = get_snapshot(role_id)
    if snap is None:
        raise KeyError(f"角色不存在：{role_id}")
    if snap["is_custom"]:
        raise ValueError("自定義角色請直接編輯或刪除，無法還原內建預設")
    with _lock:
        store = deepcopy(_load_store())
        settings = dict(store.get("settings") or {})
        settings.pop(role_id, None)
        store["settings"] = settings
        _save_store(store)
    result = get_snapshot(role_id)
    assert result is not None
    return result


def create_custom_role(data: dict[str, Any]) -> dict[str, Any]:
    clone_from = _sanitize_id(str(data.get("clone_from") or ""))
    cloned: dict[str, Any] = {}
    if clone_from:
        src = get_snapshot(clone_from)
        if src is None:
            raise ValueError(f"無法複製：角色「{clone_from}」不存在")
        cloned = {
            "level": src.get("level"),
            "category": src.get("category"),
            "reporting_to": src.get("reporting_to"),
            "can_delegate_to": src.get("can_delegate_to"),
            "responsibilities": src.get("responsibilities"),
            "system_prompt": src.get("system_prompt"),
            "max_parallel_work": src.get("max_parallel_work"),
            "default_tier": src.get("default_tier"),
            "preferred_model": src.get("preferred_model"),
            "preferred_provider": src.get("preferred_provider"),
            "daily_budget_usd": src.get("daily_budget_usd"),
            "weekly_budget_usd": src.get("weekly_budget_usd"),
            "monthly_budget_usd": src.get("monthly_budget_usd"),
            "cloud_daily_budget_usd": src.get("cloud_daily_budget_usd"),
            "cloud_weekly_budget_usd": src.get("cloud_weekly_budget_usd"),
            "cloud_monthly_budget_usd": src.get("cloud_monthly_budget_usd"),
            "tools_allowed": src.get("tools_allowed"),
            "notes": src.get("notes"),
            "alert_on_error": src.get("alert_on_error"),
            "alert_on_budget": src.get("alert_on_budget"),
            "alert_on_sla": src.get("alert_on_sla"),
            "temperature": src.get("temperature"),
            "max_output_tokens": src.get("max_output_tokens"),
            "timeout_ms": src.get("timeout_ms"),
            "routing_strategy": src.get("routing_strategy"),
            "failover_models": src.get("failover_models"),
            "sla_latency_ms": src.get("sla_latency_ms"),
            "max_retries": src.get("max_retries"),
            "language": src.get("language"),
            "always_require_review": src.get("always_require_review"),
            "priority": src.get("priority"),
            "description": src.get("description"),
            "max_daily_items": src.get("max_daily_items"),
            "require_human_approval": src.get("require_human_approval"),
            "stream_enabled": src.get("stream_enabled"),
            "cache_enabled": src.get("cache_enabled"),
            "pii_redact": src.get("pii_redact"),
            "mainland_only": src.get("mainland_only"),
            "heartbeat_sec": src.get("heartbeat_sec"),
            "on_call": src.get("on_call"),
            "tags": src.get("tags"),
            "notify_channel": src.get("notify_channel"),
            "quiet_hours": src.get("quiet_hours"),
            "context_window": src.get("context_window"),
            "allow_tool_use": src.get("allow_tool_use"),
            "auto_escalate": src.get("auto_escalate"),
            "templates": src.get("templates"),
        }
        data = {**cloned, **{k: v for k, v in data.items() if v not in (None, "", [])}}

    slug = _sanitize_id(str(data.get("id") or data.get("name") or ""))
    if not slug:
        raise ValueError("請提供角色 id 或名稱")
    if not slug.startswith("custom_"):
        slug = f"custom_{slug}"
    if not ROLE_ID_RE.match(slug):
        raise ValueError("角色 id 僅允許小寫英數與底線，長度 2-41")
    if slug in RESERVED_IDS:
        raise ValueError(f"id「{slug}」與內建角色衝突")
    if get_snapshot(slug) is not None:
        raise ValueError(f"角色 id「{slug}」已存在")

    name = str(data.get("name") or slug.replace("custom_", "").replace("_", " ")).strip()
    record = {
        "id": slug,
        "name": name,
        "level": _normalize_level(data.get("level"), 3),
        "category": _normalize_category(data.get("category"), "management"),
        "reporting_to": (str(data.get("reporting_to")).strip() if data.get("reporting_to") else None) or None,
        "can_delegate_to": _as_str_list(data.get("can_delegate_to")),
        "responsibilities": _as_str_list(data.get("responsibilities"))
        or ["執行被指派的工作項", "產出可交付成果並提交審查"],
        "system_prompt": str(data.get("system_prompt") or f"你是「{name}」，請依職責產出高品質交付物。"),
        "max_parallel_work": max(1, min(16, int(data.get("max_parallel_work") or 2))),
        "default_tier": _normalize_tier(data.get("default_tier"), "routine"),
        "templates": _as_str_list(data.get("templates")),
        "enabled": bool(data.get("enabled", True)),
    }
    _merge_runtime(record, {**_runtime_defaults(), **data})
    with _lock:
        store = deepcopy(_load_store())
        store.setdefault("custom", []).append(record)
        _save_store(store)
    result = get_snapshot(slug)
    assert result is not None
    return result


def backfill_custom_role_budgets(role_id: str, budgets: dict[str, Any]) -> bool:
    """僅在 custom 記錄與 settings 覆蓋層皆未自訂預算時，寫入預設預算到 custom[]。

    不回寫 settings 覆蓋層，保留使用者日後透過監控中心單獨覆蓋的能力。
    回傳 True 表示已更新。
    """
    role_id = _sanitize_id(role_id)
    with _lock:
        store = deepcopy(_load_store())
        overlay = (store.get("settings") or {}).get(role_id) or {}
        customs = store.get("custom") or []
        updated = False
        for item in customs:
            if _sanitize_id(str(item.get("id") or "")) != role_id:
                continue
            from backend.linkin.budget_defaults import role_budgets_uncustomized

            if not role_budgets_uncustomized(item, overlay if isinstance(overlay, dict) else None):
                return False
            for field in BUDGET_USD_FIELDS:
                if field in budgets:
                    item[field] = max(0.0, float(budgets[field] or 0))
            updated = True
            break
        if updated:
            store["custom"] = customs
            _save_store(store)
        return updated


def delete_custom_role(role_id: str) -> None:
    role_id = _sanitize_id(role_id)
    snap = get_snapshot(role_id)
    if snap is None:
        raise KeyError(f"角色不存在：{role_id}")
    if not snap["is_custom"]:
        raise ValueError("內建角色不可刪除，請改為停用")
    with _lock:
        store = deepcopy(_load_store())
        store["custom"] = [
            item
            for item in store.get("custom") or []
            if _sanitize_id(str(item.get("id") or "")) != role_id
        ]
        settings = dict(store.get("settings") or {})
        settings.pop(role_id, None)
        store["settings"] = settings
        _save_store(store)


def _allowed_models() -> list[str]:
    try:
        from backend.core.provider_pool import public_pool

        return list(public_pool().get("allowed_models") or [])
    except Exception:
        return []


def _models_by_provider() -> list[dict[str, Any]]:
    try:
        from backend.core.api_router import public_router_state

        return list(public_router_state().get("models_by_provider") or [])
    except Exception:
        return []


def _api_routes_meta() -> list[dict[str, Any]]:
    try:
        from backend.core.api_router import public_router_state

        routes = public_router_state().get("api_routes") or []
        return [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "provider": r.get("provider"),
                "provider_label": r.get("provider_label"),
                "model": r.get("model"),
                "allowed_models": r.get("allowed_models") or [],
                "enabled": r.get("enabled", True),
                "configured": r.get("configured"),
                "is_default": r.get("is_default"),
            }
            for r in routes
        ]
    except Exception:
        return []


def _model_token_hints() -> dict[str, dict[str, int]]:
    try:
        from backend.core.api_router import MODEL_TOKEN_HINTS

        return dict(MODEL_TOKEN_HINTS)
    except Exception:
        return {}


def _model_rate_cards() -> dict[str, Any]:
    try:
        from backend.company.rate_card import public_rate_cards

        return public_rate_cards()
    except Exception:
        return {"models": [], "by_id": {}, "fields": []}


def catalog_meta() -> dict[str, Any]:
    tool_names: list[str] = []
    try:
        from backend.company.tools import tool_registry

        tool_names = [t.name for t in tool_registry.list_tools()]
    except Exception:
        tool_names = []
    return {
        "categories": [{"id": k, "label": v} for k, v in CATEGORY_LABELS.items()],
        "tiers": [
            {"id": "critical", "label": "關鍵模型"},
            {"id": "reasoning", "label": "推理模型"},
            {"id": "routine", "label": "日常模型"},
            {"id": "summary", "label": "摘要模型"},
        ],
        "levels": [{"level": k, "label": v} for k, v in LEVEL_LABELS.items()],
        "tool_names": tool_names,
        "builtin_ids": sorted(RESERVED_IDS),
        "allowed_models": _allowed_models(),
        "api_routes": _api_routes_meta(),
        "models_by_provider": _models_by_provider(),
        "model_token_hints": _model_token_hints(),
        "model_rate_cards": _model_rate_cards(),
        "routing_strategies": [
            {"id": "quality_first", "label": "品質優先"},
            {"id": "cost_first", "label": "成本優先"},
            {"id": "speed_first", "label": "速度優先"},
            {"id": "manual", "label": "指定模型"},
        ],
        "role_presets": _role_presets(),
        "org_templates": [
            {"id": key, "name": cfg.name, "description": cfg.description, "role_count": len(cfg.roles)}
            for key, cfg in BUILTIN_TEMPLATES.items()
        ],
    }


def _role_presets() -> list[dict[str, Any]]:
    """自定義角色快速模板：複製內建領域角色或建立額外實例。"""
    presets: list[dict[str, Any]] = []
    for role in (
        RoleType.QUANT_ANALYST,
        RoleType.CRAWLER,
        RoleType.OPC_ENGINEER,
        RoleType.STORY_WRITER,
        RoleType.UX_RESEARCHER,
        RoleType.PERF_ENG,
        RoleType.TRANSLATOR,
        RoleType.SUPPORT,
        RoleType.PROMPT_ENGINEER,
        RoleType.LEGAL,
        RoleType.GITHUB_OPS,
        RoleType.HUB_OPERATOR,
        RoleType.MEMORY_CURATOR,
        RoleType.RISK_ANALYST,
        RoleType.API_ENGINEER,
        RoleType.ML_ENGINEER,
        RoleType.RAG_ENGINEER,
        RoleType.EVAL_ENGINEER,
        RoleType.QA_AUTOMATION,
        RoleType.PEN_TESTER,
        RoleType.PLC_ENGINEER,
        RoleType.PORTFOLIO_MGR,
        RoleType.ROUTER_ENG,
        RoleType.CUSTOMER_SUCCESS,
        RoleType.REQUIREMENT_AUDITOR,
        RoleType.TACTICAL_COMMANDER,
        RoleType.CONSTITUTIONAL_INSPECTOR,
        RoleType.ATOMIC_EXECUTOR,
        RoleType.ENVIRONMENT_KERNEL,
    ):
        snap = _builtin_snapshot(role)
        presets.append(
            {
                "id": snap["id"],
                "name": snap["name"],
                "level": snap["level"],
                "category": snap["category"],
                "reporting_to": snap["reporting_to"],
                "system_prompt": snap["system_prompt"],
                "responsibilities": snap["responsibilities"],
                "default_tier": snap["default_tier"],
                "hint": "複製此內建角色為自定義實例（可改名、獨立預算）",
            }
        )
    extras = [
        {
            "id": "night_trader",
            "name": "夜盤交易員",
            "level": 3,
            "category": "finance",
            "reporting_to": "finance_lead",
            "system_prompt": "你是夜盤交易員，追蹤美股／期貨盤後行情，標明時區、缺口風險與倉位上限。",
            "responsibilities": ["盤後行情摘要", "缺口與隔夜風險", "標明倉位上限"],
            "default_tier": "reasoning",
            "hint": "StocksX 夜盤額外席位",
        },
        {
            "id": "news_crawler",
            "name": "新聞爬蟲",
            "level": 3,
            "category": "crawler",
            "reporting_to": "data_lead",
            "system_prompt": "你是新聞爬蟲專員，採集公告與新聞標題，去重並標明來源與時間。",
            "responsibilities": ["公告／新聞採集", "去重與來源追溯", "輸出結構化摘要"],
            "default_tier": "routine",
            "hint": "LittleCrawler 新聞線",
        },
        {
            "id": "line_operator",
            "name": "產線值班",
            "level": 3,
            "category": "industrial",
            "reporting_to": "industrial_lead",
            "system_prompt": "你是產線值班員，監控 OPC 告警並依 runbook 升級，禁止未授權寫入。",
            "responsibilities": ["告警值班", "runbook 升級", "交接紀錄"],
            "default_tier": "routine",
            "hint": "PysdnOPC 值班席",
        },
        {
            "id": "visual_novel",
            "name": "視覺小說編劇",
            "level": 3,
            "category": "creative",
            "reporting_to": "creative_lead",
            "system_prompt": "你是視覺小說編劇，產出分支選項、立繪提示與章節節奏。",
            "responsibilities": ["分支對白", "立繪／場景提示", "章節節奏"],
            "default_tier": "reasoning",
            "hint": "StoryForge 分支敘事",
        },
        {
            "id": "release_watcher",
            "name": "發布看守",
            "level": 3,
            "category": "platform",
            "reporting_to": "platform_lead",
            "system_prompt": "你看守 GitHub 發布與 CI 檢查，標明失敗步驟與回滾點。",
            "responsibilities": ["CI 失敗摘要", "發布清單", "回滾建議"],
            "default_tier": "routine",
            "hint": "自定義發布席",
        },
        {
            "id": "hub_budget_guard",
            "name": "Hub 預算守衛",
            "level": 3,
            "category": "hub",
            "reporting_to": "platform_lead",
            "system_prompt": "你在每次推理前檢查日預算與熔斷，超支則建議降級模型。",
            "responsibilities": ["預算攔截", "熔斷狀態", "降級建議"],
            "default_tier": "routine",
            "hint": "自定義 Hub 監控席",
        },
        {
            "id": "memory_janitor",
            "name": "記憶清理員",
            "level": 4,
            "category": "memory",
            "reporting_to": "tech_lead",
            "system_prompt": "你清理重複與過期向量記憶，並標明敏感內容不得寫入。",
            "responsibilities": ["去重", "過期策略", "敏感過濾"],
            "default_tier": "summary",
            "hint": "自定義記憶庫席",
        },
        {
            "id": "desk_night_risk",
            "name": "夜盤風控",
            "level": 3,
            "category": "finance",
            "reporting_to": "finance_lead",
            "system_prompt": "你是夜盤風控，檢查隔夜敞口、缺口與強制減倉條件。",
            "responsibilities": ["隔夜敞口", "缺口檢查", "減倉條件"],
            "default_tier": "reasoning",
            "hint": "量化桌夜盤風控席",
        },
        {
            "id": "opc_historian",
            "name": "製程歷史員",
            "level": 3,
            "category": "industrial",
            "reporting_to": "industrial_lead",
            "system_prompt": "你整理 OPC 歷史曲線與越界事件，標明時間窗與品質碼。",
            "responsibilities": ["歷史曲線", "越界事件", "品質碼"],
            "default_tier": "routine",
            "hint": "PysdnOPC 歷史席",
        },
        {
            "id": "rag_librarian",
            "name": "RAG 館員",
            "level": 3,
            "category": "ai",
            "reporting_to": "ai_lead",
            "system_prompt": "你維護切片、引用與未命中降級，禁止把機密寫進索引。",
            "responsibilities": ["切片品質", "引用檢查", "未命中降級"],
            "default_tier": "reasoning",
            "hint": "自定義 RAG 席",
        },
        {
            "id": "growth_onboard",
            "name": "啟用教練",
            "level": 3,
            "category": "growth",
            "reporting_to": "growth_lead",
            "system_prompt": "你設計新用戶啟用路徑與卡點，把流失轉成可指派缺陷。",
            "responsibilities": ["啟用路徑", "卡點分析", "流失轉缺陷"],
            "default_tier": "routine",
            "hint": "成長漏斗席",
        },
        {
            "id": "server_admin",
            "name": "服務器運維",
            "level": 4,
            "category": "devops",
            "reporting_to": "tech_lead",
            "system_prompt": (
                "你是 Linux 服務器運維智能體（AIOps），只能透過具名運維工具診斷與修復，"
                "絕不執行自由 shell。破壞性操作必須走人工批准隊列。"
            ),
            "responsibilities": ["巡檢與健康快照", "磁盤／日誌清理提案", "服務重啟批准"],
            "default_tier": "routine",
            "preferred_model": "qwen-max",
            "temperature": 0.2,
            "tools_allowed": [
                "server_disk_usage",
                "server_system_load",
                "server_memory_usage",
                "server_docker_status",
                "server_service_status",
                "server_disk_growth",
                "server_tail_log",
                "server_clean_packages",
                "server_clean_temp",
                "server_rotate_logs",
                "server_restart_service",
                "server_backup",
            ],
            "hint": "server_admin AIOps 席（寫操作需批准）",
        },
    ]
    presets.extend(extras)
    return presets
