"""角色目錄查詢：快照清單、runtime、監控偏好（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import attach_raho_fields
from backend.company.roles import STANDARD_ROLES

from .builtins import _builtin_snapshot
from .constants import DEFAULT_MONITOR_PREFS
from .snapshots import _apply_overlay, _custom_snapshot
from .store import _load_store, _lock


def list_custom_role_ids() -> set[str]:
    """已啟用的自定義角色 id。

    與 :func:`list_role_snapshots` 不同，這裡**不含**內建角色——任務拆解時
    內建角色以 ``CompanyConfig.roles`` 為準，只有自訂席需要從目錄補進來，
    否則小團隊模板的席位限制會被整個 80 席目錄蓋掉。
    """
    found: set[str] = set()
    for snap in list_role_snapshots():
        if not snap.get("is_custom"):
            continue
        if not snap.get("enabled", True):
            continue
        role_id = str(snap.get("id") or "")
        if role_id:
            found.add(role_id)
    return found


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
