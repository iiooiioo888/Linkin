"""多廠商配置（v6.0）— vendor_configs 預設與查詢。"""

from __future__ import annotations

from typing import Any

DEFAULT_VENDOR_CONFIGS: dict[str, dict[str, Any]] = {
    "openai": {
        "vendor_id": "openai",
        "name_zh": "OpenAI",
        "tier": "战略",
        "routing_weight": 1.5,
        "supports_cache": True,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.1,
        "cache_write_mult": 1.25,
    },
    "google": {
        "vendor_id": "google",
        "name_zh": "Google",
        "tier": "优选",
        "routing_weight": 1.2,
        "supports_cache": True,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.1,
        "cache_write_mult": 1.25,
    },
    "deepseek": {
        "vendor_id": "deepseek",
        "name_zh": "DeepSeek",
        "tier": "优选",
        "routing_weight": 1.2,
        "supports_cache": True,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.1,
        "cache_write_mult": 1.0,
    },
    "tongyi": {
        "vendor_id": "tongyi",
        "name_zh": "通义",
        "tier": "标准",
        "routing_weight": 1.0,
        "supports_cache": False,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.0,
        "cache_write_mult": 0.0,
    },
    "kimi": {
        "vendor_id": "kimi",
        "name_zh": "Kimi",
        "tier": "标准",
        "routing_weight": 1.0,
        "supports_cache": False,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.0,
        "cache_write_mult": 0.0,
    },
    "self_host": {
        "vendor_id": "self_host",
        "name_zh": "自架",
        "tier": "标准",
        "routing_weight": 1.0,
        "supports_cache": False,
        "input_mult": 1.0,
        "output_mult": 1.0,
        "cache_read_mult": 0.0,
        "cache_write_mult": 0.0,
    },
}


def detect_vendor(model: str) -> str:
    m = (model or "").lower()
    if "gpt" in m or "openai" in m or m.startswith("o1") or m.startswith("o3"):
        return "openai"
    if "gemini" in m or "google" in m:
        return "google"
    if "deepseek" in m:
        return "deepseek"
    if "qwen" in m or "tongyi" in m or "通义" in m:
        return "tongyi"
    if "kimi" in m or "moonshot" in m:
        return "kimi"
    return "self_host"


def vendor_config(vendor_id: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(DEFAULT_VENDOR_CONFIGS.get(vendor_id, DEFAULT_VENDOR_CONFIGS["self_host"]))
    if overrides:
        base.update(overrides)
    return base
