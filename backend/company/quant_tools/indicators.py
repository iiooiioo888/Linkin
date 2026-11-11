"""技術指標與績效統計：SMA／EMA／ATR／RSI／布林通道／波動度與風險調整報酬。"""

from __future__ import annotations

import math
from typing import Any


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    total = 0.0
    for i, val in enumerate(values):
        total += val
        if i >= window:
            total -= values[i - window]
        if i >= window - 1:
            out[i] = total / window
    return out


def _ema(values: list[float], span: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if span <= 0 or len(values) < span:
        return out
    k = 2.0 / (span + 1)
    seed = sum(values[:span]) / span
    out[span - 1] = seed
    prev = seed
    for i in range(span, len(values)):
        prev = values[i] * k + prev * (1.0 - k)
        out[i] = prev
    return out


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 1.0
    dd = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            dd = min(dd, value / peak - 1.0)
    return round(dd, 6)


def _sharpe(equity: list[float]) -> float | None:
    if len(equity) < 3:
        return None
    rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity)) if equity[i - 1]]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    var = sum((item - mean) ** 2 for item in rets) / len(rets)
    std = math.sqrt(var)
    if std == 0:
        return 0.0
    return round((mean / std) * math.sqrt(252), 4)


def _sortino(equity: list[float]) -> float | None:
    if len(equity) < 3:
        return None
    rets = [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity)) if equity[i - 1]]
    if not rets:
        return None
    mean = sum(rets) / len(rets)
    downside = [item for item in rets if item < 0]
    if not downside:
        return None if mean <= 0 else 99.99
    dstd = math.sqrt(sum(item * item for item in downside) / len(rets))
    if dstd == 0:
        return 0.0
    return round((mean / dstd) * math.sqrt(252), 4)


def _calmar(equity: list[float]) -> float | None:
    if len(equity) < 2 or not equity[0]:
        return None
    years = max(len(equity) / 252.0, 1.0 / 252.0)
    cagr = equity[-1] ** (1.0 / years) - 1.0
    drawdown = abs(_max_drawdown(equity))
    if drawdown == 0:
        return None
    return round(cagr / drawdown, 4)


def _bars_series(bars: list[dict[str, Any]]) -> tuple[list[float], list[str], list[float], list[float], list[float]]:
    closes: list[float] = []
    dates: list[str] = []
    highs: list[float] = []
    lows: list[float] = []
    vols: list[float] = []
    for bar in bars:
        close = bar.get("c")
        if close is None:
            continue
        price = float(close)
        closes.append(price)
        dates.append(str(bar.get("t") or ""))
        highs.append(float(bar["h"]) if bar.get("h") is not None else price)
        lows.append(float(bar["l"]) if bar.get("l") is not None else price)
        vols.append(float(bar["v"]) if bar.get("v") is not None else 0.0)
    return closes, dates, highs, lows, vols


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int = 14) -> list[float | None]:
    tr: list[float] = []
    for i, close in enumerate(closes):
        if i == 0:
            tr.append(max(highs[i] - lows[i], 0.0))
            continue
        tr.append(
            max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
                0.0,
            )
        )
    return _sma(tr, period)


def _rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if period <= 0 or len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def _rolling_std(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 1:
        return out
    for i in range(window - 1, len(values)):
        chunk = values[i - window + 1 : i + 1]
        mean = sum(chunk) / window
        var = sum((item - mean) ** 2 for item in chunk) / window
        out[i] = math.sqrt(var)
    return out


def _rolling_ext(values: list[float], window: int, *, high: bool) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if window <= 0:
        return out
    for i in range(window - 1, len(values)):
        chunk = values[i - window + 1 : i + 1]
        out[i] = max(chunk) if high else min(chunk)
    return out
