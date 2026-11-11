"""自定義角色快照與 overlay 套用（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import attach_raho_fields

from .constants import LEVEL_LABELS
from .normalize import (
    _as_str_list,
    _merge_runtime,
    _normalize_category,
    _normalize_level,
    _normalize_tier,
    _runtime_defaults,
    _sanitize_id,
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
