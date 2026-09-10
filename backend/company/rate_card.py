"""模型公開價卡：輸入／輸出之外的收費項。

金額單位預設 USD / 1M tokens；搜尋、工具、圖像生成等以每次／每千次計。
實際帳單以供應商為準，此處供路由、預算估算與前端目錄顯示。
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
    "image_output",
    "audio",
    "audio_output",
    "transcription",
    "video",
    "embedding",
    "search",
    "tool",
    "batch_input",
    "batch_output",
    "long_context",
    "request",
    "storage",
    "computer",
    "realtime",
    "file_search",
    "code_exec",
)

RATE_FIELD_LABELS: dict[str, str] = {
    "input": "輸入",
    "output": "輸出",
    "cached_input": "快取命中",
    "cache_write": "快取寫入",
    "reasoning": "推理／思考",
    "image": "視覺輸入",
    "image_output": "圖像生成",
    "audio": "音訊輸入",
    "audio_output": "語音合成",
    "transcription": "語音轉寫",
    "video": "影片輸入",
    "embedding": "嵌入",
    "search": "網路搜尋",
    "tool": "工具呼叫",
    "batch_input": "批次輸入",
    "batch_output": "批次輸出",
    "long_context": "長上下文",
    "request": "單次請求",
    "storage": "檔案儲存",
    "computer": "電腦使用",
    "realtime": "即時音訊",
    "file_search": "檔案檢索",
    "code_exec": "程式執行",
}

RATE_FIELD_UNITS: dict[str, str] = {
    "input": "1M tokens",
    "output": "1M tokens",
    "cached_input": "1M tokens",
    "cache_write": "1M tokens",
    "reasoning": "1M tokens",
    "image": "1M tokens",
    "image_output": "1K images",
    "audio": "1M tokens",
    "audio_output": "1M chars",
    "transcription": "1K minutes",
    "video": "1M tokens",
    "embedding": "1M tokens",
    "search": "1K calls",
    "tool": "1K calls",
    "batch_input": "1M tokens",
    "batch_output": "1M tokens",
    "long_context": "1M tokens",
    "request": "1K requests",
    "storage": "GB-month",
    "computer": "1K calls",
    "realtime": "1M tokens",
    "file_search": "1K calls",
    "code_exec": "1K sessions",
}

# 計價除數：token 類 / 1M；呼叫類 / 1K；儲存按 GB-月
RATE_FIELD_SCALE: dict[str, float] = {
    "input": 1_000_000,
    "output": 1_000_000,
    "cached_input": 1_000_000,
    "cache_write": 1_000_000,
    "reasoning": 1_000_000,
    "image": 1_000_000,
    "audio": 1_000_000,
    "embedding": 1_000_000,
    "video": 1_000_000,
    "audio_output": 1_000_000,
    "batch_input": 1_000_000,
    "batch_output": 1_000_000,
    "long_context": 1_000_000,
    "realtime": 1_000_000,
    "image_output": 1_000,
    "transcription": 1_000,
    "search": 1_000,
    "tool": 1_000,
    "request": 1_000,
    "computer": 1_000,
    "file_search": 1_000,
    "code_exec": 1_000,
    "storage": 1,
}

def _empty_card() -> dict[str, float]:
    return {field: 0.0 for field in RATE_FIELDS}


def _card(input: float, output: float, **paid: float) -> dict[str, float]:
    card = _empty_card()
    card["input"] = float(input)
    card["output"] = float(output)
    for field, amount in paid.items():
        if field in card:
            card[field] = float(amount)
    return card


_DEFAULT_RATE_CARDS: dict[str, dict[str, float]] = {
    "gpt-4o": _card(
        2.50,
        10.00,
        cached_input=1.25,
        cache_write=2.50,
        image=3.75,
        audio=40.00,
        video=6.00,
        audio_output=40.00,
        transcription=6.00,
        search=25.00,
        tool=0.60,
        batch_input=1.25,
        batch_output=5.00,
        long_context=5.00,
        realtime=40.00,
        computer=3.00,
        file_search=2.50,
        code_exec=0.03,
        request=0.50,
        storage=0.10,
        image_output=40.00,
    ),
    "gpt-4o-mini": _card(
        0.15,
        0.60,
        cached_input=0.075,
        cache_write=0.15,
        image=0.25,
        audio=10.00,
        video=1.20,
        audio_output=12.00,
        transcription=3.00,
        search=10.00,
        tool=0.15,
        batch_input=0.075,
        batch_output=0.30,
        long_context=0.30,
        realtime=10.00,
        computer=1.50,
        file_search=1.00,
        code_exec=0.03,
        request=0.20,
        storage=0.10,
        image_output=16.00,
    ),
    "gpt-4-turbo": _card(10.00, 30.00, image=10.00, batch_input=5.00, batch_output=15.00, tool=0.40),
    "gpt-3.5-turbo": _card(0.50, 1.50, batch_input=0.25, batch_output=0.75, tool=0.10),
    "gpt-4.1": _card(
        2.00,
        8.00,
        cached_input=0.50,
        cache_write=2.00,
        image=2.00,
        search=25.00,
        tool=0.50,
        batch_input=1.00,
        batch_output=4.00,
        long_context=4.00,
        computer=3.00,
        file_search=2.50,
        code_exec=0.03,
    ),
    "gpt-4.1-mini": _card(
        0.40,
        1.60,
        cached_input=0.10,
        cache_write=0.40,
        image=0.40,
        search=10.00,
        tool=0.20,
        batch_input=0.20,
        batch_output=0.80,
        long_context=0.80,
        computer=1.50,
        file_search=1.00,
    ),
    "gpt-4.1-nano": _card(
        0.10,
        0.40,
        cached_input=0.025,
        cache_write=0.10,
        tool=0.08,
        batch_input=0.05,
        batch_output=0.20,
        long_context=0.20,
    ),
    "gpt-5.6-sol": _card(
        3.00,
        30.00,
        cached_input=0.75,
        cache_write=3.75,
        reasoning=30.00,
        image=4.50,
        audio=32.00,
        video=8.00,
        search=35.00,
        tool=0.80,
        batch_input=1.50,
        batch_output=15.00,
        long_context=6.00,
        computer=6.00,
        realtime=32.00,
        file_search=3.00,
        code_exec=0.05,
        request=1.00,
        storage=0.20,
        image_output=50.00,
    ),
    "deepseek-v4-flash": _card(
        0.22,
        0.66,
        cached_input=0.022,
        cache_write=0.28,
        reasoning=0.66,
        tool=0.05,
        batch_input=0.11,
        batch_output=0.33,
        long_context=0.44,
        search=8.00,
        request=0.05,
    ),
    "deepseek-v4-pro": _card(
        0.66,
        1.98,
        cached_input=0.066,
        cache_write=0.83,
        reasoning=1.98,
        tool=0.10,
        batch_input=0.33,
        batch_output=0.99,
        long_context=1.32,
        search=12.00,
        code_exec=0.02,
    ),
    "deepseek-v4-flash-vision-exp": _card(
        0.22,
        0.66,
        cached_input=0.022,
        image=0.80,
        video=1.20,
        tool=0.05,
        batch_input=0.11,
        batch_output=0.33,
    ),
    "qwen-turbo": _card(
        0.05,
        0.20,
        cached_input=0.02,
        cache_write=0.08,
        tool=0.04,
        batch_input=0.025,
        batch_output=0.10,
        long_context=0.10,
        search=5.00,
        request=0.02,
    ),
    "qwen-plus": _card(
        0.40,
        1.20,
        cached_input=0.08,
        cache_write=0.50,
        reasoning=1.20,
        tool=0.08,
        batch_input=0.20,
        batch_output=0.60,
        long_context=0.80,
        search=8.00,
        code_exec=0.02,
    ),
    "qwen-max": _card(
        1.60,
        6.40,
        cached_input=0.32,
        cache_write=2.00,
        reasoning=6.40,
        image=2.40,
        search=12.00,
        tool=0.20,
        batch_input=0.80,
        batch_output=3.20,
        long_context=3.20,
        computer=2.00,
        file_search=1.50,
        code_exec=0.03,
    ),
    "qwen-long": _card(
        0.50,
        2.00,
        cached_input=0.10,
        cache_write=0.60,
        long_context=0.50,
        tool=0.08,
        batch_input=0.25,
        batch_output=1.00,
        file_search=1.00,
        storage=0.05,
    ),
    "qwen3.5-max": _card(
        0.30,
        1.20,
        cached_input=0.06,
        cache_write=0.38,
        reasoning=2.40,
        image=1.20,
        search=10.00,
        tool=0.12,
        batch_input=0.15,
        batch_output=0.60,
        long_context=0.60,
        computer=1.80,
        code_exec=0.03,
    ),
    "qwen3-coder-plus": _card(
        1.00,
        4.00,
        cached_input=0.20,
        cache_write=1.25,
        reasoning=4.00,
        tool=0.25,
        batch_input=0.50,
        batch_output=2.00,
        long_context=2.00,
        code_exec=0.04,
        computer=2.50,
        file_search=1.20,
    ),
    "qwen-vl-plus": _card(0.40, 1.20, image=1.20, video=1.80, tool=0.08, batch_input=0.20, batch_output=0.60),
    "qwen-vl-max": _card(0.80, 3.20, image=2.40, video=3.60, tool=0.15, batch_input=0.40, batch_output=1.60),
    "qwen-omni-turbo": _card(
        0.08,
        0.32,
        cached_input=0.02,
        image=0.40,
        audio=0.80,
        audio_output=2.00,
        transcription=0.80,
        video=1.00,
        tool=0.06,
        realtime=1.20,
        search=6.00,
        batch_input=0.04,
        batch_output=0.16,
    ),
    "kimi-k2": _card(
        0.60,
        2.50,
        cached_input=0.15,
        cache_write=0.75,
        reasoning=2.50,
        search=10.00,
        tool=0.12,
        batch_input=0.30,
        batch_output=1.25,
        long_context=1.20,
        file_search=1.00,
    ),
    "kimi-k3": _card(
        0.40,
        1.50,
        cached_input=0.10,
        cache_write=0.50,
        reasoning=3.00,
        search=12.00,
        tool=0.15,
        batch_input=0.20,
        batch_output=0.75,
        long_context=0.80,
        computer=1.80,
        file_search=1.20,
        code_exec=0.03,
    ),
    "moonshot-v1-8k": _card(1.20, 1.20, tool=0.08, request=0.10),
    "moonshot-v1-32k": _card(2.40, 2.40, tool=0.10, long_context=2.40, request=0.15),
    "moonshot-v1-128k": _card(6.00, 6.00, tool=0.15, long_context=6.00, request=0.25),
    "glm-4-flash": _card(0.01, 0.01, tool=0.02, batch_input=0.005, batch_output=0.005, search=3.00),
    "glm-4": _card(0.10, 0.10, tool=0.05, batch_input=0.05, batch_output=0.05, search=5.00),
    "glm-4-plus": _card(0.50, 0.50, image=0.80, tool=0.08, search=8.00, batch_input=0.25, batch_output=0.25),
    "glm-5.2": _card(
        0.10,
        0.40,
        cached_input=0.02,
        cache_write=0.12,
        reasoning=0.80,
        image=0.40,
        search=6.00,
        tool=0.06,
        batch_input=0.05,
        batch_output=0.20,
        long_context=0.20,
        code_exec=0.02,
    ),
    "gemini-3.1-pro": _card(
        1.25,
        12.00,
        cached_input=0.31,
        reasoning=12.00,
        image=1.25,
        audio=3.00,
        video=3.50,
        search=14.00,
        tool=0.35,
        batch_input=0.625,
        batch_output=6.00,
        long_context=2.50,
        computer=4.00,
        file_search=2.00,
        code_exec=0.04,
        realtime=8.00,
        storage=0.15,
    ),
    "gemini-3.1-flash": _card(
        0.15,
        0.60,
        cached_input=0.04,
        reasoning=0.60,
        image=0.15,
        audio=0.50,
        video=0.60,
        search=8.00,
        tool=0.10,
        batch_input=0.075,
        batch_output=0.30,
        long_context=0.30,
        code_exec=0.02,
        realtime=2.00,
    ),
    "mimo-v2.5-pro": _card(
        0.21,
        0.83,
        cached_input=0.05,
        reasoning=0.83,
        tool=0.08,
        batch_input=0.105,
        batch_output=0.415,
        long_context=0.42,
        search=6.00,
    ),
    "mercury-2": _card(0.50, 2.00, tool=0.10, batch_input=0.25, batch_output=1.00, search=8.00, long_context=1.00),
    "nemotron-3.5-lightning": _card(0.00, 0.00),
    "text-embedding-3-small": _card(0.02, 0.00, embedding=0.02, batch_input=0.01, request=0.02),
    "text-embedding-3-large": _card(0.13, 0.00, embedding=0.13, batch_input=0.065, request=0.05),
    "qwen-embedding-v3": _card(0.03, 0.00, embedding=0.03, batch_input=0.015, request=0.02),
    "whisper-1": _card(0.00, 0.00, transcription=6.00, audio=6.00, request=0.10),
    "tts-1": _card(0.00, 0.00, audio_output=15.00, request=0.10),
    "gpt-image-1": _card(0.00, 0.00, image_output=40.00, image=5.00, request=0.20, storage=0.10),
}

_cards: dict[str, dict[str, float]] | None = None


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


def _field_meta() -> list[dict[str, str]]:
    return [
        {"id": field, "label": RATE_FIELD_LABELS[field], "unit": RATE_FIELD_UNITS[field]}
        for field in RATE_FIELDS
    ]


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
                        "unit": RATE_FIELD_UNITS.get(field, "1M tokens"),
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
        "fields": _field_meta(),
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
    video_tokens: int = 0,
    audio_output_tokens: int = 0,
    transcription_tokens: int = 0,
    batch_input_tokens: int = 0,
    batch_output_tokens: int = 0,
    long_context_tokens: int = 0,
    realtime_tokens: int = 0,
    search_calls: int = 0,
    tool_calls: int = 0,
    request_count: int = 0,
    computer_calls: int = 0,
    code_exec_calls: int = 0,
    file_search_calls: int = 0,
    image_output_count: int = 0,
    storage_gb_month: float = 0.0,
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
        "video": video_tokens,
        "audio_output": audio_output_tokens,
        "transcription": transcription_tokens,
        "batch_input": batch_input_tokens,
        "batch_output": batch_output_tokens,
        "long_context": long_context_tokens,
        "realtime": realtime_tokens,
        "search": search_calls,
        "tool": tool_calls,
        "request": request_count,
        "computer": computer_calls,
        "code_exec": code_exec_calls,
        "file_search": file_search_calls,
        "image_output": image_output_count,
        "storage": storage_gb_month,
    }
    total = 0.0
    for field, amount in usage.items():
        if not amount:
            continue
        scale = RATE_FIELD_SCALE.get(field, 1_000_000)
        total += (float(amount) / scale) * float(card.get(field) or 0.0)
    return total
