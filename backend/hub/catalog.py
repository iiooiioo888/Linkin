"""九模型封閉目錄。目錄外 ID 一律拒絕，且禁止任何 Claude / Anthropic 字串。"""

from __future__ import annotations

import re
import time
from typing import Any

HUB_CATALOG: frozenset[str] = frozenset(
    {
        "gpt-5.6-sol",
        "gemini-3.1-pro",
        "mimo-v2.5-pro",
        "deepseek-v4-flash",
        "qwen3.5-max",
        "mercury-2",
        "nemotron-3.5-lightning",
        "glm-5.2",
        "kimi-k3",
    }
)

INTEL: dict[str, int] = {
    "gpt-5.6-sol": 96,
    "gemini-3.1-pro": 92,
    "mimo-v2.5-pro": 88,
    "qwen3.5-max": 86,
    "kimi-k3": 85,
    "glm-5.2": 85,
    "deepseek-v4-flash": 84,
    "mercury-2": 78,
    "nemotron-3.5-lightning": 74,
}

PROVIDER_OF: dict[str, str] = {
    "gpt-5.6-sol": "openai",
    "gemini-3.1-pro": "google",
    "mimo-v2.5-pro": "mimo",
    "deepseek-v4-flash": "deepseek",
    "qwen3.5-max": "qwen",
    "mercury-2": "inception",
    "nemotron-3.5-lightning": "nvidia",
    "glm-5.2": "zhipu",
    "kimi-k3": "moonshot",
}

# (input_usd_per_1m, output_usd_per_1m) — 與 company.budget 及 §1.6 對齊
PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5.6-sol": (3.00, 30.00),
    "gemini-3.1-pro": (1.25, 12.00),
    "mimo-v2.5-pro": (0.21, 0.83),
    "deepseek-v4-flash": (0.22, 0.66),
    "qwen3.5-max": (0.30, 1.20),
    "mercury-2": (0.50, 2.00),
    "nemotron-3.5-lightning": (0.00, 0.00),
    "glm-5.2": (0.10, 0.40),
    "kimi-k3": (0.40, 1.50),
}

DEFAULT_LATENCY_MS: dict[str, float] = {
    "gpt-5.6-sol": 520.0,
    "gemini-3.1-pro": 480.0,
    "mimo-v2.5-pro": 420.0,
    "deepseek-v4-flash": 390.0,
    "qwen3.5-max": 450.0,
    "mercury-2": 80.0,
    "nemotron-3.5-lightning": 95.0,
    "glm-5.2": 500.0,
    "kimi-k3": 540.0,
}

CN_SET: frozenset[str] = frozenset(
    {"deepseek-v4-flash", "qwen3.5-max", "mimo-v2.5-pro"}
)
DEFAULT_CHAIN: tuple[str, ...] = (
    "gpt-5.6-sol",
    "gemini-3.1-pro",
    "deepseek-v4-flash",
    "glm-5.2",
)
CN_CHAIN: tuple[str, ...] = (
    "deepseek-v4-flash",
    "qwen3.5-max",
    "mimo-v2.5-pro",
)
RACE_PAIR: tuple[str, str] = ("gemini-3.1-pro", "mercury-2")
QUALITY_FLAGSHIP = "gpt-5.6-sol"
COST_PREFERRED = "deepseek-v4-flash"
AGENT_FALLBACK = "qwen3.5-max"

FORBIDDEN_MODEL_RE = re.compile(
    r"(?i)claude|anthropic|opus-|sonnet-|haiku-|fable"
)

ALLOWED_STRATEGIES = frozenset(
    {"cost_first", "speed_first", "quality_first", "manual"}
)
ALLOWED_TOOLS = frozenset(
    {
        "StocksX_get_price",
        "StocksX_get_fundamentals",
        "LittleCrawler_fetch",
        "StoryForge_draft",
        "PysdnOPC_read",
        "PysdnOPC_write",
    }
)
MULTIMODAL_KEYS = frozenset({"image_url", "input_audio", "file"})


def assert_catalog_integrity() -> None:
    """啟動時斷言目錄 / 智能分 / 廠商 / 價目四集合相等。"""
    sets = (HUB_CATALOG, set(INTEL), set(PROVIDER_OF), set(PRICE_PER_1M))
    if not (sets[0] == sets[1] == sets[2] == sets[3]):
        raise RuntimeError("Hub 目錄集合不一致")
    joined = " ".join(HUB_CATALOG).lower()
    if FORBIDDEN_MODEL_RE.search(joined):
        raise RuntimeError("Hub 目錄含禁止供應商字串")


def provider_of(model: str) -> str:
    return PROVIDER_OF[model]


def is_forbidden_model_string(value: str) -> bool:
    return bool(FORBIDDEN_MODEL_RE.search(value or ""))


def validate_model_id(model: str | None) -> str | None:
    """回傳模型 ID；非法則拋 ValueError（code 由上層轉成 UNSUPPORTED_MODEL）。"""
    if model is None or model == "":
        return None
    if is_forbidden_model_string(model) or model not in HUB_CATALOG:
        raise ValueError("UNSUPPORTED_MODEL")
    return model


def runtime_hub_whitelist() -> list[str] | None:
    """目前 API 能用的 Hub 模型；對不到則 None（沿用完整目錄 + clamp）。"""
    from backend.core.provider_pool import compatible_hub_models, public_pool

    pool = public_pool()
    if not pool.get("allowed_models"):
        return None
    compat = compatible_hub_models(sorted(HUB_CATALOG), PROVIDER_OF)
    return compat or None


def catalog_payload() -> dict[str, Any]:
    """公開目錄（不含任何 Claude ID）。"""
    available = set(runtime_hub_whitelist() or HUB_CATALOG)
    models = []
    for model in sorted(HUB_CATALOG):
        in_p, out_p = PRICE_PER_1M[model]
        try:
            from backend.company.rate_card import rate_card_for

            extra = rate_card_for(model)
        except Exception:  # noqa: BLE001
            extra = {}
        models.append(
            {
                "id": model,
                "provider": PROVIDER_OF[model],
                "intelligence": INTEL[model],
                "price_in_per_1m": in_p,
                "price_out_per_1m": out_p,
                "price_cached_in_per_1m": extra.get("cached_input") or None,
                "price_cache_write_per_1m": extra.get("cache_write") or None,
                "price_reasoning_per_1m": extra.get("reasoning") or None,
                "price_image_per_1m": extra.get("image") or None,
                "price_audio_per_1m": extra.get("audio") or None,
                "cn_allowed": model in CN_SET,
                "available_in_pool": model in available,
            }
        )
    return {
        "models": models,
        "strategies": sorted(ALLOWED_STRATEGIES),
        "default_chain": list(DEFAULT_CHAIN),
        "cn_set": sorted(CN_SET),
        "race_pair": list(RACE_PAIR),
        "quality_flagship": QUALITY_FLAGSHIP,
        "forbidden_vendor": "anthropic",
        "pool_lock": public_pool_lock(),
    }


def public_pool_lock() -> dict[str, Any]:
    from backend.core.provider_pool import public_pool

    pool = public_pool()
    return {
        "provider_kind": pool.get("provider_kind") or "",
        "provider_label": pool.get("provider_label") or "",
        "lock_message": pool.get("lock_message") or "",
        "allowed_models": pool.get("allowed_models") or [],
    }


def seed_default_metrics(target: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """寫入目錄預設延遲 / 單價，供探針尚未跑完前的動態權重使用。"""
    now = int(time.time())
    for model in HUB_CATALOG:
        in_p, out_p = PRICE_PER_1M[model]
        target.setdefault(
            model,
            {
                "latency_ewma_ms": DEFAULT_LATENCY_MS.get(model, 800.0),
                "ttfb_ms": DEFAULT_LATENCY_MS.get(model, 800.0),
                "price_in_per_1m": in_p,
                "price_out_per_1m": out_p,
                "consecutive_fail": 0,
                "ts": now,
            },
        )
    return target


assert_catalog_integrity()
