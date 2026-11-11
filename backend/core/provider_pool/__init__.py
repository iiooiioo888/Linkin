"""依已儲存的 API 鎖定可用模型池。

規則：
- 單一廠商端點（如 DeepSeek）：Agent 只能用該廠商模型，禁止落到 gpt-4o 預設。
- 通用 OpenAI 相容端點（OpenRouter / Ollama / vLLM）：GET /models 爬取目錄並寫入配置。
- 禁止 Claude / Anthropic 進入可用池。

自單檔模組拆為套件，對外 import 路徑不變；子模組分工：
- constants：禁止模型／廠商目錄／標籤等常數
- helpers：名稱正規化、廠商分類、端點、clamp、failover 開關
- catalog：模型目錄抓取、解析、正規化與 refresh 系列
- health：熔斷狀態、主動探活、reset、池健康快照
- registry：public_pool、refresh 間隔設定、failover 鏈
"""

from __future__ import annotations

from .catalog import (
    _is_auth_catalog_error,
    fetch_catalog,
    normalize_catalog_model,
    normalize_catalog_models,
    parse_models_payload,
    refresh_interval_sec,
    refresh_model_catalog,
    refresh_route_catalog,
)
from .constants import (
    CRAWL_KINDS,
    DEFAULT_REFRESH_SEC,
    FORBIDDEN_RE,
    KIND_LABELS,
    MODEL_FAMILY_LABELS,
    MODEL_FAMILY_PREFIX_RE,
    TOKEN_PLAN_LABEL,
    VENDOR_HOSTS,
    VENDOR_STATIC,
)
from .health import (
    POOL_FAILURE_THRESHOLD,
    POOL_OPEN_DURATION_S,
    force_open_pool_model,
    heal_pool_model,
    is_pool_model_open,
    pool_health_snapshot,
    pool_probe_enabled,
    pool_probe_ping_enabled,
    pool_probe_snapshot,
    pool_probe_timeout_s,
    probe_pool_health,
    record_pool_call,
    reset_pool_health,
)
from .helpers import (
    clamp_model,
    classify_provider,
    compatible_hub_models,
    friendly_model_name,
    infer_model_family,
    is_forbidden_model,
    is_token_plan_url,
    models_endpoint,
    pool_failover_enabled,
    pool_failover_slow_s,
    pool_failover_timeout_s,
    static_catalog,
)
from .registry import (
    failover_models,
    invoke_with_pool_failover,
    public_pool,
    set_refresh_interval,
)

__all__ = [
    "CRAWL_KINDS",
    "DEFAULT_REFRESH_SEC",
    "FORBIDDEN_RE",
    "KIND_LABELS",
    "MODEL_FAMILY_LABELS",
    "MODEL_FAMILY_PREFIX_RE",
    "POOL_FAILURE_THRESHOLD",
    "POOL_OPEN_DURATION_S",
    "TOKEN_PLAN_LABEL",
    "VENDOR_HOSTS",
    "VENDOR_STATIC",
    "_is_auth_catalog_error",
    "clamp_model",
    "classify_provider",
    "compatible_hub_models",
    "failover_models",
    "fetch_catalog",
    "force_open_pool_model",
    "friendly_model_name",
    "heal_pool_model",
    "infer_model_family",
    "invoke_with_pool_failover",
    "is_forbidden_model",
    "is_pool_model_open",
    "is_token_plan_url",
    "models_endpoint",
    "normalize_catalog_model",
    "normalize_catalog_models",
    "parse_models_payload",
    "pool_failover_enabled",
    "pool_failover_slow_s",
    "pool_failover_timeout_s",
    "pool_health_snapshot",
    "pool_probe_enabled",
    "pool_probe_ping_enabled",
    "pool_probe_snapshot",
    "pool_probe_timeout_s",
    "probe_pool_health",
    "public_pool",
    "record_pool_call",
    "refresh_interval_sec",
    "refresh_model_catalog",
    "refresh_route_catalog",
    "reset_pool_health",
    "set_refresh_interval",
    "static_catalog",
]
