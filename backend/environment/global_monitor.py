"""L0 態勢感知雷達：把 Token、延遲、質詢失敗率轉成環境偏置。

外部行情預設走環境變數／Mock，不強連 Yahoo；測試可注入 metrics。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EnvSnapshot:
    timestamp: float
    metrics: dict[str, Any] = field(default_factory=dict)
    bias_instructions: str = ""
    energy_save: bool = False
    pressure: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "metrics": dict(self.metrics),
            "bias_instructions": self.bias_instructions,
            "energy_save": self.energy_save,
            "pressure": round(self.pressure, 3),
        }


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def collect_metrics(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """收集內部壓力。外部欄位可用環境變數或 overrides 覆寫。"""
    token_ratio = _env_float("EVOL_L0_TOKEN_RATIO", 0.0)
    latency_ms = _env_float("EVOL_L0_LATENCY_MS", 0.0)
    sentiment = (os.getenv("EVOL_L0_MARKET_SENTIMENT") or "neutral").strip() or "neutral"
    urgency = (os.getenv("EVOL_L0_USER_URGENCY") or "normal").strip() or "normal"
    grill_fail = 0.0
    pending = 0
    try:
        from backend.company.raho.scorecard import all_metrics
        from backend.company.raho.store import STORE

        cards = all_metrics() or {}
        rates: list[float] = []
        for card in cards.values() if isinstance(cards, dict) else []:
            if isinstance(card, dict) and card.get("grill_rate") is not None:
                rates.append(float(card["grill_rate"]))
        if rates:
            grill_fail = sum(rates) / len(rates)
        pending = len(STORE.list_pending())
        repeats = [
            int(getattr(sess, "repeat_count", 0) or 0)
            for sess in STORE.user_sessions.values()
        ]
        if repeats and max(repeats) >= 2:
            urgency = "high"
    except Exception:  # noqa: BLE001
        pass

    metrics = {
        "token_usage_ratio": max(0.0, min(1.5, token_ratio)),
        "avg_latency_ms": max(0.0, latency_ms),
        "grill_fail_rate": max(0.0, min(1.0, grill_fail)),
        "pending_decisions": pending,
        "external_market_sentiment": sentiment,
        "user_urgency": urgency,
    }
    if overrides:
        metrics.update(overrides)
    return metrics


def compute_bias(metrics: dict[str, Any]) -> tuple[str, bool, float]:
    """回傳 (偏置指令, 是否節能, 壓力 0~1)。"""
    token = float(metrics.get("token_usage_ratio") or 0)
    latency = float(metrics.get("avg_latency_ms") or 0)
    fail = float(metrics.get("grill_fail_rate") or 0)
    pending = float(metrics.get("pending_decisions") or 0)
    urgency = str(metrics.get("user_urgency") or "normal")
    sentiment = str(metrics.get("external_market_sentiment") or "neutral")

    pressure = min(
        1.0,
        0.35 * token
        + 0.25 * min(1.0, latency / 4000.0)
        + 0.25 * fail
        + 0.10 * min(1.0, pending / 5.0)
        + (0.15 if urgency == "high" else 0.0),
    )
    energy = token >= 0.8 or latency >= 2500 or fail >= 0.55
    parts: list[str] = []
    if energy:
        parts.append("因系統負載偏高，建議啟用節能模式：L2 Max Iterations 上限 1，L1 可對邊界項降級通過。")
    if urgency == "high":
        parts.append("用戶催促偏高，優先給可驗證的最小交付，禁止擴範圍。")
    if sentiment in {"bearish", "risk_off"}:
        parts.append("外部情緒偏空，量化／定價任務須加註風險警示。")
    if fail >= 0.4:
        parts.append("近期質詢失敗率偏高，拆解時優先沿用歷史成功 DAG。")
    if not parts:
        parts.append("環境壓力正常，依規格完整驗收，不得降級通過。")
    return " ".join(parts), energy, pressure


def snapshot(overrides: dict[str, Any] | None = None) -> EnvSnapshot:
    metrics = collect_metrics(overrides)
    bias, energy, pressure = compute_bias(metrics)
    return EnvSnapshot(
        timestamp=time.time(),
        metrics=metrics,
        bias_instructions=bias,
        energy_save=energy,
        pressure=pressure,
    )
