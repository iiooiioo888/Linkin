"""模型公開價卡：輸入／輸出之外的收費項。

金額單位預設 USD / 1M tokens。實際帳單以供應商為準，此處供路由、
預算估算與前端目錄顯示。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

RATE_FIELDS: tuple[str, ...] = (
    "input",
    "output",
    "cached_input",
    "cache_write",
    "reasoning",
    "image",
    "audio",
    "embedding",
)

RATE_FIELD_LABELS: dict[str, str] = {
    "input": "輸入",
    "output": "輸出",
    "cached_input": "快取命中",
    "cache_write": "快取寫入",
    "reasoning": "推理／思考",
    "image": "視覺輸入",
    "audio": "音訊輸入",
    "embedding": "嵌入",
}


def _card(
    input: float,
    output: float,
    *,
    cached_input: float = 0.0,
    cache_write: float = 0.0,
    reasoning: float = 0.0,
    image: float = 0.0,
    audio: float = 0.0,
    embedding: float = 0.0,
) -> dict[str, float]:
    return {
        "input": float(input),
        "output": float(output),
        "cached_input": float(cached_input),
        "cache_write": float(cache_write),
        "reasoning": float(reasoning),
        "image": float(image),
        "audio": float(audio),
        "embedding": float(embedding),
    }


_DEFAULT_RATE_CARDS: dict[str, dict[str, float]] = {
    "gpt-4o": _card(2.50, 10.00, cached_input=1.25, cache_write=2.50, image=3.75, audio=40.00),
    "gpt-4o-mini": _card(0.15, 0.60, cached_input=0.075, cache_write=0.15, image=0.25, audio=10.00),
    "gpt-4-turbo": _card(10.00, 30.00, image=10.00),
    "gpt-3.5-turbo": _card(0.50, 1.50),
    "gpt-4.1": _card(2.00, 8.00, cached_input=0.50, cache_write=2.00, image=2.00),
    "gpt-4.1-mini": _card(0.40, 1.60, cached_input=0.10, cache_write=0.40, image=0.40),
    "gpt-4.1-nano": _card(0.10, 0.40, cached_input=0.025, cache_write=0.10),
    "gpt-5.6-sol": _card(3.00, 30.00, cached_input=0.75, cache_write=3.75, reasoning=30.00, image=4.50),
    "deepseek-v4-flash": _card(0.22, 0.66, cached_input=0.022, cache_write=0.28, reasoning=0.66),
    "deepseek-v4-pro": _card(0.66, 1.98, cached_input=0.066, cache_write=0.83, reasoning=1.98),
    "deepseek-v4-flash-vision-exp": _card(0.22, 0.66, cached_input=0.022, image=0.80),
    "qwen-turbo": _card(0.05, 0.20, cached_input=0.02, cache_write=0.08),
    "qwen-plus": _card(0.40, 1.20, cached_input=0.08, cache_write=0.50, reasoning=1.20),
    "qwen-max": _card(1.60, 6.40, cached_input=0.32, cache_write=2.00, reasoning=6.40, image=2.40),
    "qwen-long": _card(0.50, 2.00, cached_input=0.10, cache_write=0.60),
    "qwen3.5-max": _card(0.30, 1.20, cached_input=0.06, cache_write=0.38, reasoning=2.40, image=1.20),
    "qwen3-coder-plus": _card(1.00, 4.00, cached_input=0.20, cache_write=1.25, reasoning=4.00),
    "qwen-vl-plus": _card(0.40, 1.20, image=1.20),
    "qwen-vl-max": _card(0.80, 3.20, image=2.40),
    "kimi-k2": _card(0.60, 2.50, cached_input=0.15, cache_write=0.75, reasoning=2.50),
    "kimi-k3": _card(0.40, 1.50, cached_input=0.10, cache_write=0.50, reasoning=3.00),
    "moonshot-v1-8k": _card(1.20, 1.20),
    "moonshot-v1-32k": _card(2.40, 2.40),
    "moonshot-v1-128k": _card(6.00, 6.00),
    "glm-4-flash": _card(0.01, 0.01),
    "glm-4": _card(0.10, 0.10),
    "glm-4-plus": _card(0.50, 0.50, image=0.80),
    "glm-5.2": _card(0.10, 0.40, cached_input=0.02, cache_write=0.12, reasoning=0.80),
    "gemini-3.1-pro": _card(1.25, 12.00, cached_input=0.31, reasoning=12.00, image=1.25, audio=3.00),
    "mimo-v2.5-pro": _card(0.21, 0.83, cached_input=0.05, reasoning=0.83),
    "mercury-2": _card(0.50, 2.00),
    "nemotron-3.5-lightning": _card(0.00, 0.00),
    "text-embedding-3-small": _card(0.02, 0.00, embedding=0.02),
    "text-embedding-3-large": _card(0.13, 0.00, embedding=0.13),
    "qwen-embedding-v3": _card(0.03, 0.00, embedding=0.03),
}

_cards: dict[str, dict[str, float]] | None = None


def _empty_card() -> dict[str, float]:
    return {field: 0.0 for field in RATE_FIELDS}


def _parse_card(value: object) -> dict[str, float] | None:
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        card = _empty_card()
        card["input"] = float(value[0])
        card["output"] = float(value[1])
        return card
    if not isinstance(value, dict):
        return None
    card = _empty_card()
    alias = {
        "in": "input",
        "out": "output",
        "price_in": "input",
        "price_out": "output",
        "cached": "cached_input",
        "cache_hit": "cached_input",
        "thinking": "reasoning",
        "vision": "image",
    }
    for key, raw in value.items():
        field = alias.get(str(key), str(key))
        if field not in card:
            continue
        try:
            card[field] = float(raw)
        except (TypeError, ValueError):
            continue
    return card


def _load_rate_cards() -> dict[str, dict[str, float]]:
    cards = {model: dict(card) for model, card in _DEFAULT_RATE_CARDS.items()}
    config_path = os.getenv("EVOL_MODEL_COSTS_PATH")
    if not config_path:
        default_path = Path(__file__).resolve().parent.parent / "config" / "model_costs.json"
        if default_path.exists():
            config_path = str(default_path)
    if not config_path:
        return cards
    try:
        with open(config_path, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            return cards
        for model, prices in loaded.items():
            parsed = _parse_card(prices)
            if not parsed:
                continue
            merged = dict(cards.get(str(model)) or _empty_card())
            for field, amount in parsed.items():
                if amount or field in {"input", "output"}:
                    merged[field] = amount
            cards[str(model)] = merged
        logger.info("從配置文件載入 %d 個模型價目：%s", len(loaded), config_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("載入模型價格配置失敗（使用預設值）：%s", exc)
    return cards


def get_model_rate_cards() -> dict[str, dict[str, float]]:
    global _cards
    if _cards is None:
        _cards = _load_rate_cards()
    return _cards


def get_model_costs() -> dict[str, tuple[float, float]]:
    return {
        model: (card.get("input", 0.0), card.get("output", 0.0))
        for model, card in get_model_rate_cards().items()
    }


def rate_card_for(model: str) -> dict[str, float]:
    cards = get_model_rate_cards()
    hit = cards.get(model)
    if hit:
        return dict(hit)
    bare = (model or "").split("/")[-1]
    hit = cards.get(bare)
    if hit:
        return dict(hit)
    return _card(1.0, 4.0)


def public_rate_cards() -> dict[str, Any]:
    items = []
    for model, card in sorted(get_model_rate_cards().items()):
        paid = {k: v for k, v in card.items() if v}
        items.append(
            {
                "id": model,
                "input": card.get("input", 0.0),
                "output": card.get("output", 0.0),
                "items": [
                    {
                        "id": field,
                        "label": RATE_FIELD_LABELS.get(field, field),
                        "usd_per_1m": amount,
                    }
                    for field, amount in card.items()
                    if amount
                ],
                **paid,
                "currency": "USD",
                "unit": "1M tokens",
            }
        )
    return {
        "currency": "USD",
        "unit": "1M tokens",
        "fields": [{"id": k, "label": v} for k, v in RATE_FIELD_LABELS.items()],
        "models": items,
        "by_id": {row["id"]: row for row in items},
    }


def reload_model_costs() -> None:
    global _cards
    _cards = _load_rate_cards()
    logger.info("模型價格配置已重新載入")


def estimate_usage_cost(
    model: str,
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    cache_write_tokens: int = 0,
    reasoning_tokens: int = 0,
    image_tokens: int = 0,
    audio_tokens: int = 0,
    embedding_tokens: int = 0,
) -> float:
    card = rate_card_for(model)
    usage = {
        "input": input_tokens,
        "output": output_tokens,
        "cached_input": cached_input_tokens,
        "cache_write": cache_write_tokens,
        "reasoning": reasoning_tokens,
        "image": image_tokens,
        "audio": audio_tokens,
        "embedding": embedding_tokens,
    }
    total = 0.0
    for field, tokens in usage.items():
        if tokens:
            total += (tokens / 1_000_000) * float(card.get(field) or 0.0)
    return total
