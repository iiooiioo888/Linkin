"""多 API / 多模型路由器。

在單一 llm_config 之上允許同時保存多組供應商憑證（千問、DeepSeek、
Kimi、OpenRouter…），依策略或角色偏好把請求分發到對應端點與模型。

向後相容：未設定 api_routes 時，把頂層 api_key / api_base / model
合成一條 id=primary 的路由，既有單一廠商鎖定行為不變。

套件化：本模組已拆為 backend/core/api_router/ 套件，公開 import 路徑不變。
models／presets／routes／selection／state 各自持有領域函式，本 __init__.py 只做 re-export。
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from backend.core.llm_config import get_runtime_config, masked_key, merge_runtime_config
from backend.core.provider_pool import (
    KIND_LABELS,
    MODEL_FAMILY_LABELS,
    TOKEN_PLAN_LABEL,
    classify_provider,
    infer_model_family,
    is_forbidden_model,
    is_token_plan_url,
    normalize_catalog_models,
    static_catalog,
)

from .models import (
    MODEL_TOKEN_HINTS,
    PRIMARY_ROUTE_ID,
    PROVIDER_PRESETS,
    ROUTE_ID_RE,
    ROUTE_STRATEGIES,
    _bare,
    _default_models_for,
    _model_in_list,
    _normalize_provider_routing,
    _sanitize_route_id,
    _token_plan_route_name,
    get_route_strategy,
    normalize_route,
    normalize_strategy,
)
from .presets import (
    _build_models_by_provider,
    _public_rate_cards,
    _route_provider_label,
    provider_presets_public,
    public_route,
    public_router_state,
    token_hint_for,
)
from .routes import (
    _alias_provider,
    _persist_routes,
    _raw_routes,
    delete_route,
    find_route_for_model,
    get_default_route,
    get_route,
    list_enabled_routes,
    list_routes,
    resolve_route_ref,
    route_as_cfg,
    save_routes,
    set_route_strategy,
    sync_primary_into_routes,
    synthesize_primary_route,
    union_allowed_models,
    upsert_route,
)
from .selection import (
    _least_loaded,
    _random_select,
    _weighted_round_robin,
    list_failover_chain,
    mark_route_end,
    mark_route_start,
    resolve_target,
    route_inflight_snapshot,
    select_route,
)
from .state import (
    _inflight,
    _lock,
    _wrr_current,
    logger,
    reset_router_state,
)

__all__ = [
    "KIND_LABELS",
    "MODEL_FAMILY_LABELS",
    "MODEL_TOKEN_HINTS",
    "PRIMARY_ROUTE_ID",
    "PROVIDER_PRESETS",
    "ROUTE_ID_RE",
    "ROUTE_STRATEGIES",
    "TOKEN_PLAN_LABEL",
    "Any",
    "_alias_provider",
    "_bare",
    "_build_models_by_provider",
    "_default_models_for",
    "_inflight",
    "_least_loaded",
    "_lock",
    "_model_in_list",
    "_normalize_provider_routing",
    "_persist_routes",
    "_public_rate_cards",
    "_random_select",
    "_raw_routes",
    "_route_provider_label",
    "_sanitize_route_id",
    "_token_plan_route_name",
    "_weighted_round_robin",
    "_wrr_current",
    "classify_provider",
    "delete_route",
    "find_route_for_model",
    "get_default_route",
    "get_route",
    "get_route_strategy",
    "get_runtime_config",
    "infer_model_family",
    "is_forbidden_model",
    "is_token_plan_url",
    "list_enabled_routes",
    "list_failover_chain",
    "list_routes",
    "logger",
    "logging",
    "mark_route_end",
    "mark_route_start",
    "masked_key",
    "merge_runtime_config",
    "normalize_catalog_models",
    "normalize_route",
    "normalize_strategy",
    "provider_presets_public",
    "public_route",
    "public_router_state",
    "re",
    "reset_router_state",
    "resolve_route_ref",
    "resolve_target",
    "route_as_cfg",
    "route_inflight_snapshot",
    "save_routes",
    "select_route",
    "set_route_strategy",
    "static_catalog",
    "sync_primary_into_routes",
    "synthesize_primary_route",
    "threading",
    "token_hint_for",
    "union_allowed_models",
    "upsert_route",
]

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.core.api_router) 的公開名稱與原模組一致（51 個）。
for _submodule in (
    "models",
    "presets",
    "routes",
    "selection",
    "state",
):
    globals().pop(_submodule, None)
del _submodule

