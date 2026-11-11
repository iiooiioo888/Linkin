"""角色目錄的檔案位置、快取、載入與儲存（自 backend.company.role_catalog 抽出）。"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from .constants import DEFAULT_CATALOG_DIR, DEFAULT_CATALOG_PATH, DEFAULT_MONITOR_PREFS, logger

_lock = threading.RLock()
_cache_by_path: dict[str, tuple[dict[str, Any], float | None]] = {}
_legacy_catalog_migrated = False


def catalog_dir() -> Path:
    return Path(os.getenv("EVOL_ROLE_CATALOG_DIR", str(DEFAULT_CATALOG_DIR)))


def _catalog_user_key(user_id: str | None = None) -> str:
    from backend.tenant.context import current_tenant_user

    raw = user_id if user_id is not None else current_tenant_user()
    text = re.sub(r"[^a-zA-Z0-9._@-]+", "_", (raw or "").strip())[:96]
    return text or "anonymous"


def catalog_path(user_id: str | None = None) -> Path:
    legacy_single = os.getenv("EVOL_ROLE_CATALOG_PATH", "").strip()
    if legacy_single:
        return Path(legacy_single)
    return catalog_dir() / f"{_catalog_user_key(user_id)}.json"


def reset_catalog_cache() -> None:
    global _cache_by_path
    with _lock:
        _cache_by_path = {}


def _maybe_migrate_legacy_shared_catalog() -> None:
    global _legacy_catalog_migrated
    if _legacy_catalog_migrated or os.getenv("EVOL_ROLE_CATALOG_PATH", "").strip():
        _legacy_catalog_migrated = True
        return
    with _lock:
        if _legacy_catalog_migrated:
            return
        from backend.tenant.ids import LEGACY_CATALOG_OWNER

        legacy = DEFAULT_CATALOG_PATH
        target_dir = catalog_dir()
        target = target_dir / f"{LEGACY_CATALOG_OWNER}.json"
        if legacy.is_file() and not target.is_file():
            target_dir.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(legacy.read_bytes())
                logger.info("已將共用 role_catalog.json 遷移至 %s", target)
            except OSError as exc:
                logger.warning("角色目錄遷移失敗：%s", exc)
        _legacy_catalog_migrated = True


def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "monitor": dict(DEFAULT_MONITOR_PREFS),
        "settings": {},
        "custom": [],
    }


def _load_store(user_id: str | None = None) -> dict[str, Any]:
    _maybe_migrate_legacy_shared_catalog()
    path = catalog_path(user_id)
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None

    cached = _cache_by_path.get(path_key)
    if cached is not None and cached[1] == mtime:
        return cached[0]

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
    _cache_by_path[path_key] = (store, mtime)
    return store


def _save_store(store: dict[str, Any], user_id: str | None = None) -> dict[str, Any]:
    path = catalog_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "owner_user_id": _catalog_user_key(user_id),
        "monitor": {**DEFAULT_MONITOR_PREFS, **(store.get("monitor") or {})},
        "settings": store.get("settings") or {},
        "custom": store.get("custom") or [],
    }
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    path_key = str(path.resolve())
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    _cache_by_path[path_key] = (payload, mtime)
    return payload
