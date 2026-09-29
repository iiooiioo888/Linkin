"""靈境積分（Linkin Credit）計價引擎。

1 Credit = 1,000 baseline-model tokens（可經模型倍率調整）。
環境變數可覆寫各項預設費率。
"""

from __future__ import annotations

import os
import re
from typing import Any

BASELINE_TOKENS_PER_CREDIT = int(os.getenv("LINKIN_CREDIT_BASELINE_TOKENS", "1000"))

# 價檔常數。有價目的機型不手寫倍率，改由 in+4×out 混合單價落檔（見 tier_for_mixed_price）。
_FRONTIER_MULT = float(os.getenv("LINKIN_CREDIT_MULT_FRONTIER", "5.0"))
_SMALL_MULT = float(os.getenv("LINKIN_CREDIT_MULT_SMALL", "0.3"))
_STANDARD_MULT = float(os.getenv("LINKIN_CREDIT_MULT_GPT4O", "1.5"))
_ADVANCED_MULT = float(os.getenv("LINKIN_CREDIT_MULT_ADVANCED", "3.0"))
_BASELINE_MULT = 1.0

# 混合單價上限（USD / 1M，input + 4×output）。錨點：
# gpt-4o-mini ≈ 2.55、luna ≈ 5、mercury ≈ 8.5 → small；
# glm-5.3 ≈ 13.8、kimi-k2.7-code ≈ 16 → baseline；
# qwen3.8-max ≈ 21、gpt-4o ≈ 42.5、terra ≈ 50 → standard；
# sol ≈ 123 → advanced；astra ≈ 210 → frontier。
# 零計價（探針）單獨成檔，不得套用小檔。
_TIER_SMALL_MAX = 10.0
_TIER_BASE_MAX = 20.0
_TIER_STANDARD_MAX = 60.0
_TIER_ADVANCED_MAX = 160.0

# 價目表沒有的名稱才走家族別名。尺寸詞必須是獨立片段，禁止用子串
# （「gemini」含有「mini」，整詞掃描會把旗艦收成小檔）。
_SMALL_TOKENS = frozenset({"mini", "nano", "small", "flash", "haiku"})
_ADVANCED_TOKENS = frozenset({"o1", "o3", "opus", "thinking"})
_TIER_ALIAS_KEYS = frozenset({"baseline", "small", "advanced", "frontier"})
_FAMILY_ALIASES: dict[str, float] = {
    "baseline": _BASELINE_MULT,
    "small": _SMALL_MULT,
    "advanced": _ADVANCED_MULT,
    "frontier": _FRONTIER_MULT,
    "gpt-4": _STANDARD_MULT,
    "claude": _STANDARD_MULT,
    "gemini": 1.2,
    "o1": _ADVANCED_MULT,
    "o3": _ADVANCED_MULT,
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


def _segments(model: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", model) if part}


def mixed_unit_price(input_usd: float, output_usd: float) -> float:
    """in + 4×out。輸出權重對齊既有落檔註記，避免只看輸入把貴模型收成小檔。"""
    return float(input_usd) + 4.0 * float(output_usd)


def tier_for_mixed_price(mixed: float) -> float:
    if mixed <= 0:
        return 0.0
    if mixed <= _TIER_SMALL_MAX:
        return _SMALL_MULT
    if mixed <= _TIER_BASE_MAX:
        return _BASELINE_MULT
    if mixed <= _TIER_STANDARD_MAX:
        return _STANDARD_MULT
    if mixed <= _TIER_ADVANCED_MAX:
        return _ADVANCED_MULT
    return _FRONTIER_MULT


def match_multiplier_table(model: str, mults: dict[str, Any]) -> float:
    """自訂倍率表。尺寸詞只認獨立片段，家族鍵只認前綴邊界。"""
    m = _normalize_model(model)
    exact = mults.get(m)
    if exact is not None:
        return float(exact)
    segments = _segments(m)
    if segments & _ADVANCED_TOKENS:
        return float(mults.get("advanced", _ADVANCED_MULT))
    if segments & _SMALL_TOKENS:
        return float(mults.get("small", _SMALL_MULT))
    for key in sorted(mults, key=len, reverse=True):
        if key in _TIER_ALIAS_KEYS:
            continue
        if m == key or m.startswith(f"{key}-") or m.startswith(f"{key}."):
            return float(mults[key])
    return float(mults.get("baseline", _BASELINE_MULT))


def model_multiplier(model: str) -> float:
    """有價目用混合單價落檔；沒有價目才用家族別名。禁止用子串猜檔。"""
    m = _normalize_model(model)
    if not m:
        return _BASELINE_MULT
    # 舊環境變數只釘錨點機型，不改整檔。未設定時仍走價目分檔。
    if m == "gpt-4o-mini":
        pinned = os.getenv("LINKIN_CREDIT_MULT_GPT4O_MINI")
        if pinned:
            return float(pinned)
    if m == "gpt-4o":
        pinned = os.getenv("LINKIN_CREDIT_MULT_GPT4O")
        if pinned:
            return float(pinned)
    from backend.company.rate_card import get_model_rate_cards

    card = get_model_rate_cards().get(m)
    if card is not None:
        return tier_for_mixed_price(mixed_unit_price(card.get("input", 0.0), card.get("output", 0.0)))
    return match_multiplier_table(m, _FAMILY_ALIASES)


def effective_model_multipliers() -> dict[str, float]:
    """價目表每一型的實際倍率，加上無價目時才用的家族別名。"""
    from backend.company.rate_card import get_model_rate_cards

    priced = {
        name: tier_for_mixed_price(mixed_unit_price(card.get("input", 0.0), card.get("output", 0.0)))
        for name, card in get_model_rate_cards().items()
    }
    return {**_FAMILY_ALIASES, **priced}


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
    from backend.billing.docker_pricing import base_hourly_rates
    from backend.billing.plans import PLAN_ORDER, get_plan

    docker_tiers = {}
    for pid in PLAN_ORDER:
        plan = get_plan(pid)
        docker_tiers[pid] = {
            "name_zh": plan.get("name_zh", pid),
            "rate_multiplier": plan.get("docker_rate_multiplier", 1.0),
            "included_hours_per_month": plan.get("docker_included_hours_per_month", 0),
            "description_zh": plan.get("docker_description_zh", ""),
        }
    return {
        "unit": "靈境積分（Linkin Credit）",
        "baseline_tokens_per_credit": BASELINE_TOKENS_PER_CREDIT,
        "model_multipliers": effective_model_multipliers(),
        "reflection_per_iteration": REFLECTION_CREDITS_PER_ITER,
        "raho_layers": RAHO_LAYER_CREDITS,
        "quant_api_call": QUANT_API_CREDITS,
        "opc_write": OPC_WRITE_CREDITS,
        "opc_read": OPC_READ_CREDITS,
        "mc_fill_per_1k_blocks": MC_FILL_CREDITS_PER_1000_BLOCKS,
        "docker_usd_to_credits": DOCKER_USD_TO_CREDITS,
        "docker_base_hourly_rates_usd": base_hourly_rates(),
        "docker_tiers": docker_tiers,
        "recall": RECALL_CREDITS,
        "storage_gb_month": VECTOR_STORAGE_CREDITS_PER_GB_MONTH,
    }
