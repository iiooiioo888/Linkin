"""貢獻者獎勵引擎 v6.0 — 不含 cache hit rate，含消費者評分。"""

from __future__ import annotations

from typing import Any


def quality_score(
    *,
    uptime: float = 1.0,
    latency: float = 1.0,
    stability: float = 1.0,
    consumer_rating: float = 1.0,
) -> float:
    """quality = 0.35×uptime + 0.35×latency + 0.20×stability + 0.10×consumer_rating"""
    return round(
        0.35 * max(0.0, min(1.0, uptime))
        + 0.35 * max(0.0, min(1.0, latency))
        + 0.20 * max(0.0, min(1.0, stability))
        + 0.10 * max(0.0, min(1.0, consumer_rating)),
        4,
    )


def demand_multiplier(peak: bool = False) -> float:
    return 1.2 if peak else 0.8


def compute_reward(
    actual_api_cost: float,
    *,
    discount: float = 0.7,
    uptime: float = 1.0,
    latency: float = 1.0,
    stability: float = 1.0,
    consumer_rating: float = 1.0,
    peak: bool = False,
    lock_multiplier: float = 1.0,
    platform_take: float = 0.3,
) -> dict[str, Any]:
    """Reward = actual_api_cost × discount × quality × demand × lock_multiplier；平台抽成 20-40%。"""
    q = quality_score(uptime=uptime, latency=latency, stability=stability, consumer_rating=consumer_rating)
    d = demand_multiplier(peak)
    gross = actual_api_cost * max(0.6, min(0.8, discount)) * q * d * lock_multiplier
    take = gross * max(0.2, min(0.4, platform_take))
    contributor = gross - take
    return {
        "gross_reward": round(gross, 6),
        "platform_take": round(take, 6),
        "contributor_reward": round(contributor, 6),
        "quality": q,
        "demand_mult": d,
        "lock_multiplier": lock_multiplier,
    }
