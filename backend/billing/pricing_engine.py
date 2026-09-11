"""定價引擎 v6.0 — 多廠商 input/output + 可選 cache 項。

Cost = (input×input_mult + output×output_mult + cache_read×cache_read_mult + cache_write×cache_write_mult)
       × model_mult × role_weight × tool_coeff
L3 cache hit：按正常費用 10% 計費。缺 cache metadata → 全額 input 計費並標記 cache_metadata_missing。
"""

from __future__ import annotations

import json
from typing import Any

from backend.billing.vendor_configs import DEFAULT_VENDOR_CONFIGS, detect_vendor, vendor_config

_DEFAULT_CONFIG: dict[str, Any] = {
    "baseline_tokens_per_credit": 1000,
    "input_mult": 1.0,
    "output_mult": 1.0,
    "cache_read_mult": 0.1,
    "cache_write_mult": 1.25,
    "l3_cache_hit_mult": 0.1,
    "model_multipliers": {
        "baseline": 1.0,
        "gpt-4o-mini": 0.3,
        "gpt-4o": 1.5,
        "advanced": 3.0,
        "small": 0.3,
    },
    "role_weights": {"L5": 10, "L4": 6, "L3": 3, "L2": 1.5, "L1": 0.5, "L0": 0.2, "default": 1.0},
    "tool_coefficients": {"default": 1.0, "quant": 0.5, "docker": 1.0, "opc": 1.0},
    "estimate_buffer": 1.3,
    "vendor_configs": DEFAULT_VENDOR_CONFIGS,
}


def _normalize_model(model: str) -> str:
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.split("/", 1)[1]
    return m


def model_multiplier(config: dict[str, Any], model: str) -> float:
    mults = config.get("model_multipliers") or {}
    m = _normalize_model(model)
    if any(k in m for k in ("o1", "o3", "opus", "thinking")):
        return float(mults.get("advanced", 3.0))
    if any(k in m for k in ("mini", "nano", "small", "flash", "haiku")):
        return float(mults.get("small", 0.3))
    for key, val in mults.items():
        if key in m:
            return float(val)
    return float(mults.get("baseline", 1.0))


def role_weight(config: dict[str, Any], role: str = "") -> float:
    weights = config.get("role_weights") or {}
    key = (role or "default").upper()
    if key.startswith("L") and key in weights:
        return float(weights[key])
    return float(weights.get(role, weights.get("default", 1.0)))


def tool_coeff(config: dict[str, Any], tool: str = "") -> float:
    coeffs = config.get("tool_coefficients") or {}
    return float(coeffs.get(tool or "default", coeffs.get("default", 1.0)))


def _vendor_mults(config: dict[str, Any], model: str, vendor_id: str | None) -> dict[str, float]:
    vid = vendor_id or detect_vendor(model)
    vc_map = config.get("vendor_configs") or DEFAULT_VENDOR_CONFIGS
    vc = vendor_config(vid, vc_map.get(vid))
    return {
        "input_mult": float(vc.get("input_mult", config.get("input_mult", 1.0))),
        "output_mult": float(vc.get("output_mult", config.get("output_mult", 1.0))),
        "cache_read_mult": float(vc.get("cache_read_mult", config.get("cache_read_mult", 0.1))),
        "cache_write_mult": float(vc.get("cache_write_mult", config.get("cache_write_mult", 1.25))),
        "routing_weight": float(vc.get("routing_weight", 1.0)),
    }


def token_cost_units(
    config: dict[str, Any],
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    model: str = "default",
    vendor_id: str | None = None,
    cache_metadata_missing: bool = False,
    l3_cache_hit: bool = False,
    # 向後相容
    cached_tokens: int = 0,
) -> tuple[float, dict[str, Any]]:
    """返回 (units, flags)。"""
    baseline = max(1, int(config.get("baseline_tokens_per_credit", 1000)))
    vm = _vendor_mults(config, model, vendor_id)
    flags: dict[str, Any] = {}

    inp = max(0, int(input_tokens))
    out = max(0, int(output_tokens))
    cread = max(0, int(cache_read_tokens or cached_tokens))
    cwrite = max(0, int(cache_write_tokens))

    if cache_metadata_missing:
        flags["cache_metadata_missing"] = True
        cread = 0
        cwrite = 0
    elif cread > inp:
        cread = inp

    billable_input = max(0, inp - cread) if not cache_metadata_missing else inp

    units = (
        billable_input * vm["input_mult"]
        + out * vm["output_mult"]
        + cread * vm["cache_read_mult"]
        + cwrite * vm["cache_write_mult"]
    ) / baseline

    if l3_cache_hit:
        units *= float(config.get("l3_cache_hit_mult", 0.1))
        flags["l3_cache_hit"] = True
        savings = 1.0 - float(config.get("l3_cache_hit_mult", 0.1))
        flags["cache_savings_ratio"] = savings

    return units, flags


def compute_cost_credits(
    config: dict[str, Any],
    *,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cached_tokens: int = 0,
    role: str = "",
    tool: str = "",
    vendor_id: str | None = None,
    cache_metadata_missing: bool = False,
    l3_cache_hit: bool = False,
    lock_multiplier: float = 1.0,
) -> float:
    units, _ = token_cost_units(
        config,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        cached_tokens=cached_tokens,
        model=model,
        vendor_id=vendor_id,
        cache_metadata_missing=cache_metadata_missing,
        l3_cache_hit=l3_cache_hit,
    )
    cost = units * model_multiplier(config, model) * role_weight(config, role) * tool_coeff(config, tool) * lock_multiplier
    return round(max(0.0, cost), 6)


def compute_cost_with_meta(
    config: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    units, flags = token_cost_units(config, **kwargs)
    cost = compute_cost_credits(config, **kwargs)
    normal_cost = compute_cost_credits(config, **{**kwargs, "l3_cache_hit": False, "cache_read_tokens": 0})
    savings = max(0.0, normal_cost - cost) if flags.get("l3_cache_hit") or kwargs.get("cache_read_tokens") else 0.0
    return {"cost_credits": cost, "flags": flags, "cache_savings_credits": round(savings, 6)}


def estimate_task_reserve(
    config: dict[str, Any],
    *,
    model: str,
    baseline_tokens: int,
    iterations: int = 1,
    roles: int = 1,
) -> float:
    buffer = float(config.get("estimate_buffer", 1.3))
    vm = _vendor_mults(config, model, None)
    units = (baseline_tokens * (vm["input_mult"] + vm["output_mult"])) / max(1, int(config.get("baseline_tokens_per_credit", 1000)))
    est = units * model_multiplier(config, model) * max(1, iterations) * max(1, roles) * buffer
    return round(est, 4)


def merge_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = json.loads(json.dumps(_DEFAULT_CONFIG))
    if raw:
        out.update(raw)
        for k in ("model_multipliers", "role_weights", "tool_coefficients", "vendor_configs"):
            if k in raw and isinstance(raw[k], dict):
                out[k] = {**out.get(k, {}), **raw[k]}
    return out


DEFAULT_PRICING_CONFIG = merge_config(None)
DEFAULT_CREDIT_POLICY: dict[str, Any] = {
    "monthly_rollover_ratio": 0.5,
    "rollover_cap": 50000,
    "by_tier": {
        "free": {"monthly_rollover_ratio": 0.3, "rollover_cap": 5000},
        "starter": {"monthly_rollover_ratio": 0.4, "rollover_cap": 15000},
        "pro": {"monthly_rollover_ratio": 0.5, "rollover_cap": 50000},
        "business": {"monthly_rollover_ratio": 0.6, "rollover_cap": 200000},
        "enterprise": {"monthly_rollover_ratio": 0.7, "rollover_cap": 1000000},
    },
}
