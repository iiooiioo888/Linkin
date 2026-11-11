"""角色目錄：內建角色覆蓋設定 + 自定義角色持久化（多租戶）。

每帳戶一檔 `backend/data/role_catalog/<user_id>.json`（`EVOL_ROLE_CATALOG_DIR`）。
測試可用 `EVOL_ROLE_CATALOG_PATH` 指向單一 JSON（共用檔，非生產路徑）。
監控中心與公司運行時共用當前租戶目錄，編輯後僅影響該帳戶。

套件化：本模組已拆為 backend/company/role_catalog/ 套件，公開 import 路徑不變。
store／normalize／builtins／snapshots／query／service 各自持有領域函式，本 __init__.py 只做 re-export。
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

from .builtins import (
    _builtin_snapshot,
    _role_presets,
    _templates_for,
)
from .constants import (
    AI_BUDGET_FIELDS,
    BUDGET_USD_FIELDS,
    CATEGORY_LABELS,
    CATEGORY_VALUES,
    CLOUD_BUDGET_FIELDS,
    DEFAULT_CATALOG_DIR,
    DEFAULT_CATALOG_PATH,
    DEFAULT_MONITOR_PREFS,
    DEFAULT_RUNTIME,
    LEVEL_LABELS,
    RESERVED_IDS,
    ROLE_ID_RE,
    ROUTING_STRATEGIES,
    TIER_VALUES,
    logger,
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
from .query import (
    get_monitor_prefs,
    get_snapshot,
    list_custom_role_ids,
    list_role_snapshots,
    resolve_runtime,
)
from .service import (
    _allowed_models,
    _api_routes_meta,
    _model_rate_cards,
    _model_token_hints,
    _models_by_provider,
    _settings_payload,
    backfill_custom_role_budgets,
    catalog_meta,
    create_custom_role,
    delete_custom_role,
    reset_role_settings,
    update_monitor_prefs,
    update_role_settings,
)
from .snapshots import (
    _apply_overlay,
    _custom_snapshot,
)
from .store import (
    _cache_by_path,
    _catalog_user_key,
    _empty_store,
    _legacy_catalog_migrated,
    _load_store,
    _lock,
    _maybe_migrate_legacy_shared_catalog,
    _save_store,
    catalog_dir,
    catalog_path,
    reset_catalog_cache,
)

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.company.role_catalog) 的公開名稱與原模組一致（47 個）。
for _submodule in (
    "builtins",
    "constants",
    "normalize",
    "query",
    "service",
    "snapshots",
    "store",
):
    globals().pop(_submodule, None)
del _submodule


__all__ = [
    "AI_BUDGET_FIELDS",
    "BUDGET_USD_FIELDS",
    "BUILTIN_TEMPLATES",
    "CATEGORY_LABELS",
    "CATEGORY_VALUES",
    "CLOUD_BUDGET_FIELDS",
    "DEFAULT_CATALOG_DIR",
    "DEFAULT_CATALOG_PATH",
    "DEFAULT_MONITOR_PREFS",
    "DEFAULT_RUNTIME",
    "LEVEL_LABELS",
    "RESERVED_IDS",
    "ROLE_CATEGORY_MAP",
    "ROLE_ID_RE",
    "ROLE_LEVEL",
    "ROUTING_STRATEGIES",
    "STANDARD_ROLES",
    "TIER_VALUES",
    "Any",
    "BudgetTier",
    "Path",
    "RoleCategory",
    "RoleType",
    "_allowed_models",
    "_api_routes_meta",
    "_apply_overlay",
    "_as_str_list",
    "_builtin_snapshot",
    "_cache_by_path",
    "_catalog_user_key",
    "_clamp_float",
    "_clamp_int",
    "_custom_snapshot",
    "_empty_store",
    "_legacy_catalog_migrated",
    "_load_store",
    "_lock",
    "_maybe_migrate_legacy_shared_catalog",
    "_merge_runtime",
    "_model_rate_cards",
    "_model_token_hints",
    "_models_by_provider",
    "_normalize_category",
    "_normalize_level",
    "_normalize_routing",
    "_normalize_tier",
    "_role_presets",
    "_runtime_defaults",
    "_sanitize_id",
    "_save_store",
    "_settings_payload",
    "_templates_for",
    "attach_raho_fields",
    "backfill_custom_role_budgets",
    "catalog_dir",
    "catalog_meta",
    "catalog_path",
    "create_custom_role",
    "deepcopy",
    "delete_custom_role",
    "get_monitor_prefs",
    "get_snapshot",
    "json",
    "list_custom_role_ids",
    "list_role_snapshots",
    "logger",
    "logging",
    "os",
    "re",
    "reset_catalog_cache",
    "reset_role_settings",
    "resolve_runtime",
    "threading",
    "update_monitor_prefs",
    "update_role_settings",
]
