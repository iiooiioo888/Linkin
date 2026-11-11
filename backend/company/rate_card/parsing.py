"""費率卡解析與載入（JSON 覆寫、欄位 meta）（自 backend.company.rate_card 抽出）。"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from .cards import _DEFAULT_RATE_CARDS, _empty_card
from .fields import RATE_FIELD_LABELS, RATE_FIELD_UNITS, RATE_FIELDS

logger = logging.getLogger("backend.company.rate_card")


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
        "vision_output": "image_output",
        "tts": "audio_output",
        "asr": "transcription",
        "web_search": "search",
        "tools": "tool",
        "function_call": "tool",
        "grounding": "search",
        "agent": "computer",
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
    except Exception as exc:
        logger.warning("載入模型價格配置失敗（使用預設值）：%s", exc)
    return cards


def _field_meta() -> list[dict[str, str]]:
    return [
        {"id": field, "label": RATE_FIELD_LABELS[field], "unit": RATE_FIELD_UNITS[field]}
        for field in RATE_FIELDS
    ]
