"""靈境積分（Linkin Credit）計價引擎。

1 Credit = 1,000 baseline-model tokens（可經模型倍率調整）。
環境變數可覆寫各項預設費率。
"""

from __future__ import annotations

import os
from typing import Any

BASELINE_TOKENS_PER_CREDIT = int(os.getenv("LINKIN_CREDIT_BASELINE_TOKENS", "1000"))

# 模型倍率（相對 baseline）
MODEL_MULTIPLIERS: dict[str, float] = {
    "gpt-4o-mini": float(os.getenv("LINKIN_CREDIT_MULT_GPT4O_MINI", "0.3")),
    "gpt-4o": float(os.getenv("LINKIN_CREDIT_MULT_GPT4O", "1.5")),
    "gpt-4": 1.5,
    "claude": 1.5,
    "gemini": 1.2,
    "o1": 3.0,
    "o3": 3.0,
    "advanced": float(os.getenv("LINKIN_CREDIT_MULT_ADVANCED", "3.0")),
    "baseline": 1.0,
    "small": float(os.getenv("LINKIN_CREDIT_MULT_SMALL", "0.3")),
}

REFLECTION_CREDITS_PER_ITER = float(os.getenv("LINKIN_CREDIT_REFLECTION_ITER", "2"))
RAHO_LAYER_CREDITS: dict[str, float] = {
    "L5": float(os.getenv("LINKIN_CREDIT_RAHO_L5", "10")),
    "L4": float(os.getenv("LINKIN_CREDIT_RAHO_L4", "6")),
    "L3": float(os.getenv("LINKIN_CREDIT_RAHO_L3", "3")),
    "L2": float(os.getenv("LINKIN_CREDIT_RAHO_L2", "1.5")),
    "L1": float(os.getenv("LINKIN_CREDIT_RAHO_L1", "0.5")),
    "L0": float(os.getenv("LINKIN_CREDIT_RAHO_L0", "0.2")),
}
QUANT_API_CREDITS = float(os.getenv("LINKIN_CREDIT_QUANT_CALL", "0.5"))
OPC_WRITE_CREDITS = float(os.getenv("LINKIN_CREDIT_OPC_WRITE", "5"))
OPC_READ_CREDITS = float(os.getenv("LINKIN_CREDIT_OPC_READ", "0.1"))
MC_FILL_CREDITS_PER_1000_BLOCKS = float(os.getenv("LINKIN_CREDIT_MC_FILL_PER_1K", "2"))
MC_OP_CREDITS = float(os.getenv("LINKIN_CREDIT_MC_OP", "1"))
RECALL_CREDITS = float(os.getenv("LINKIN_CREDIT_RECALL", "1"))
# Docker：$0.01/h ≈ 10 credits/h at 1000 credits/$1
DOCKER_USD_TO_CREDITS = float(os.getenv("LINKIN_CREDIT_PER_USD", "1000"))
VECTOR_STORAGE_CREDITS_PER_GB_MONTH = float(os.getenv("LINKIN_CREDIT_STORAGE_GB_MONTH", "10"))


def _normalize_model(model: str) -> str:
    m = (model or "").strip().lower()
    if "/" in m:
        m = m.split("/", 1)[1]
    return m


def model_multiplier(model: str) -> float:
    m = _normalize_model(model)
    if any(k in m for k in ("o1", "o3", "opus", "thinking")):
        return MODEL_MULTIPLIERS.get("advanced", 3.0)
    if any(k in m for k in ("mini", "nano", "small", "flash", "haiku")):
        return MODEL_MULTIPLIERS.get("small", 0.3)
    for key, mult in MODEL_MULTIPLIERS.items():
        if key in m:
            return mult
    return MODEL_MULTIPLIERS.get("baseline", 1.0)


def credits_for_llm_tokens(model: str, input_tokens: int, output_tokens: int) -> float:
    """LLM token → 靈境積分。"""
    total = max(0, int(input_tokens)) + max(0, int(output_tokens))
    if total <= 0:
        return 0.0
    mult = model_multiplier(model)
    base = total / BASELINE_TOKENS_PER_CREDIT
    return round(base * mult, 4)


def credits_for_reflection_iteration(count: int = 1) -> float:
    return round(REFLECTION_CREDITS_PER_ITER * max(1, int(count)), 4)


def credits_for_raho_layer(layer: str) -> float:
    key = str(layer or "L2").upper()
    if not key.startswith("L"):
        key = f"L{key}"
    return RAHO_LAYER_CREDITS.get(key, RAHO_LAYER_CREDITS.get("L2", 1.5))


def credits_for_quant_call(count: int = 1) -> float:
    return round(QUANT_API_CREDITS * max(1, int(count)), 4)


def credits_for_opc_write(count: int = 1) -> float:
    return round(OPC_WRITE_CREDITS * max(1, int(count)), 4)


def credits_for_opc_read(count: int = 1) -> float:
    return round(OPC_READ_CREDITS * max(1, int(count)), 4)


def credits_for_mc_fill(blocks: int) -> float:
    n = max(0, int(blocks))
    if n <= 0:
        return MC_OP_CREDITS
    return round((n / 1000.0) * MC_FILL_CREDITS_PER_1000_BLOCKS, 4)


def credits_for_mc_op(tool: str = "") -> float:
    if "fill" in (tool or "").lower():
        return MC_OP_CREDITS
    return MC_OP_CREDITS


def credits_for_docker_usd(amount_usd: float) -> float:
    return round(max(0.0, float(amount_usd)) * DOCKER_USD_TO_CREDITS, 4)


def credits_for_recall() -> float:
    return RECALL_CREDITS


def public_rate_card() -> dict[str, Any]:
    return {
        "unit": "靈境積分（Linkin Credit）",
        "baseline_tokens_per_credit": BASELINE_TOKENS_PER_CREDIT,
        "model_multipliers": MODEL_MULTIPLIERS,
        "reflection_per_iteration": REFLECTION_CREDITS_PER_ITER,
        "raho_layers": RAHO_LAYER_CREDITS,
        "quant_api_call": QUANT_API_CREDITS,
        "opc_write": OPC_WRITE_CREDITS,
        "opc_read": OPC_READ_CREDITS,
        "mc_fill_per_1k_blocks": MC_FILL_CREDITS_PER_1000_BLOCKS,
        "docker_usd_to_credits": DOCKER_USD_TO_CREDITS,
        "recall": RECALL_CREDITS,
        "storage_gb_month": VECTOR_STORAGE_CREDITS_PER_GB_MONTH,
    }
