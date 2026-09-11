"""定價引擎：版本化配置 + 任務快照 + 成本公式。

Cost = (cached×read_mult + uncached×1.0 + cache_write×write_mult) × model_mult × role_weight × tool_coeff
預設值僅作 fallback；真實值來自 pricing_configs DB。
"""

from __future__ import annotations

import json
from typing import Any

# Fallback defaults（DB 無配置時使用，非 source of truth）
_DEFAULT_CONFIG: dict[str, Any] = {
    "baseline_tokens_per_credit": 1000,
    "read_mult": 0.25,
    "write_mult": 1.25,
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


def token_cost_units(
    config: dict[str, Any],
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """未乘模型/角色係數的 token 成本單位。"""
    read_mult = float(config.get("read_mult", 0.25))
    write_mult = float(config.get("write_mult", 1.25))
    baseline = int(config.get("baseline_tokens_per_credit", 1000))
    inp = max(0, int(input_tokens))
    out = max(0, int(output_tokens))
    cached = max(0, min(int(cached_tokens), inp))
    uncached_in = max(0, inp - cached)
    cwrite = max(0, int(cache_write_tokens))
    units = (
        cached * read_mult
        + uncached_in * 1.0
        + out * 1.0
        + cwrite * write_mult
    ) / max(1, baseline)
    return units


def compute_cost_credits(
    config: dict[str, Any],
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    role: str = "",
    tool: str = "",
) -> float:
    units = token_cost_units(
        config,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
    )
    cost = units * model_multiplier(config, model) * role_weight(config, role) * tool_coeff(config, tool)
    return round(max(0.0, cost), 6)


def estimate_task_reserve(
    config: dict[str, Any],
    *,
    model: str,
    baseline_tokens: int,
    iterations: int = 1,
    roles: int = 1,
) -> float:
    buffer = float(config.get("estimate_buffer", 1.3))
    units = (baseline_tokens * 2) / max(1, int(config.get("baseline_tokens_per_credit", 1000)))
    est = units * model_multiplier(config, model) * max(1, iterations) * max(1, roles) * buffer
    return round(est, 4)


def merge_config(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = json.loads(json.dumps(_DEFAULT_CONFIG))
    if raw:
        out.update(raw)
        for k in ("model_multipliers", "role_weights", "tool_coefficients"):
            if k in raw and isinstance(raw[k], dict):
                out[k] = {**out.get(k, {}), **raw[k]}
    return out


DEFAULT_PRICING_CONFIG = merge_config(None)
DEFAULT_CREDIT_POLICY: dict[str, Any] = {
    "monthly_rollover_ratio": 0.5,
    "rollover_cap": 50000,
    "by_tier": {},
}
