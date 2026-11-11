"""角色目錄的更新／建立／刪除與 catalog_meta（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from backend.company.roles import BUILTIN_TEMPLATES

from .builtins import _role_presets
from .constants import (
    BUDGET_USD_FIELDS,
    CATEGORY_LABELS,
    DEFAULT_MONITOR_PREFS,
    LEVEL_LABELS,
    RESERVED_IDS,
    ROLE_ID_RE,
)
from .normalize import (
    _as_str_list,
    _clamp_float,
    _clamp_int,
    _merge_runtime,
    _normalize_category,
    _normalize_level,
    _normalize_routing,
    _normalize_tier,
    _runtime_defaults,
    _sanitize_id,
)
from .query import get_snapshot
from .store import _load_store, _lock, _save_store


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
