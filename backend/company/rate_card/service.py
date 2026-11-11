"""費率卡查詢／公開視圖／重載與用量成本估算（自 backend.company.rate_card 抽出）。"""

from __future__ import annotations

from typing import Any

from .cards import _card
from .fields import RATE_FIELD_LABELS, RATE_FIELD_SCALE, RATE_FIELD_UNITS
from .parsing import _field_meta, _load_rate_cards, logger

_cards: dict[str, dict[str, float]] | None = None


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
