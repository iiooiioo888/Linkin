"""部位序列引擎與核心策略 runner（自 backend.company.quant_tools.strategies 抽出）。

部位序列引擎與核心策略 runner（RSI／布林／動能／均值回歸／突破／KDJ／均線／唐奇安）。
"""

from __future__ import annotations

from typing import Any

from ..indicators import _ema, _rolling_ext, _rolling_std, _rsi, _sma
from .charts import _pack_backtest


def _run_position_series(
    closes: list[float],
    dates: list[str],
    want_long: list[bool],
    extra: dict[str, Any] | None = None,
    slippage_pct: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    trailing_stop_pct: float = 0.0,
    enable_t1: bool = False,
    enable_limit: bool = False,
    include_chart: bool = False,
) -> dict[str, Any]:
    slip = max(0.0, float(slippage_pct or 0.0)) / 100.0
    stop = max(0.0, float(stop_loss_pct or 0.0)) / 100.0
    take = max(0.0, float(take_profit_pct or 0.0)) / 100.0
    trail = max(0.0, float(trailing_stop_pct or 0.0)) / 100.0
    pos = 0
    entry = 0.0
    peak = 0.0
    bought_at = -1
    equity = [1.0]
    trades: list[dict[str, Any]] = []
    for i in range(1, len(closes)):
        should = bool(want_long[i]) if i < len(want_long) else False
        day_ret = (closes[i] / closes[i - 1] - 1.0) if closes[i - 1] else 0.0
        limit_up = bool(enable_limit) and day_ret >= 0.098
        limit_dn = bool(enable_limit) and day_ret <= -0.098
        move = (closes[i] / entry - 1.0) if pos == 1 and entry else 0.0
        if pos == 1:
            peak = max(peak, closes[i])
        hit_stop = pos == 1 and stop > 0 and move <= -stop
        hit_take = pos == 1 and take > 0 and move >= take
        hit_trail = pos == 1 and trail > 0 and peak > 0 and closes[i] <= peak * (1.0 - trail)
        t1_block = bool(enable_t1) and pos == 1 and i <= bought_at
        if pos == 0 and should and not limit_up:
            pos = 1
            entry = closes[i] * (1.0 + slip)
            peak = closes[i]
            bought_at = i + 1
            trades.append({"side": "buy", "t": dates[i] if i < len(dates) else None, "price": round(entry, 4)})
        elif pos == 1 and (not should or hit_stop or hit_take or hit_trail) and not t1_block and not limit_dn:
            fill = closes[i] * (1.0 - slip)
            ret = fill / entry - 1.0 if entry else 0.0
            pos = 0
            reason = "signal"
            if hit_stop:
                reason = "stop"
            elif hit_take:
                reason = "take_profit"
            elif hit_trail:
                reason = "trailing"
            trades.append(
                {
                    "side": "sell",
                    "t": dates[i] if i < len(dates) else None,
                    "price": round(fill, 4),
                    "ret": round(ret, 6),
                    "reason": reason,
                }
            )
        if pos == 1 and closes[i - 1]:
            equity.append(equity[-1] * (closes[i] / closes[i - 1]))
        else:
            equity.append(equity[-1])
    signal = "long" if want_long and want_long[-1] else "cash"
    return _pack_backtest(
        equity,
        trades,
        signal,
        extra=extra,
        dates=dates,
        closes=closes,
        include_chart=bool(include_chart),
    )


def _run_rsi(closes: list[float], dates: list[str], period: int = 14, **risk: Any) -> dict[str, Any]:
    rsi = _rsi(closes, period)
    want = [False] * len(closes)
    held = False
    for i, value in enumerate(rsi):
        if value is None:
            want[i] = held
            continue
        if value < 30:
            held = True
        elif value > 70:
            held = False
        want[i] = held
    last = rsi[-1]
    return _run_position_series(
        closes, dates, want, extra={"rsi": round(last, 4) if last is not None else None}, **risk
    )


def _run_bollinger(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    ma = _sma(closes, period)
    std = _rolling_std(closes, period)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        mid, sd = ma[i], std[i]
        if mid is None or sd is None or sd == 0:
            want[i] = held
            continue
        lower, upper = mid - 2 * sd, mid + 2 * sd
        if close <= lower:
            held = True
        elif close >= upper or close >= mid:
            held = False
        want[i] = held
    last_ma, last_sd = ma[-1], std[-1]
    extra = {
        "ma": last_ma,
        "lower": (last_ma - 2 * last_sd) if last_ma is not None and last_sd is not None else None,
        "upper": (last_ma + 2 * last_sd) if last_ma is not None and last_sd is not None else None,
    }
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_momentum(closes: list[float], dates: list[str], lookback: int = 20, **risk: Any) -> dict[str, Any]:
    want = [False] * len(closes)
    last_roc = None
    for i in range(len(closes)):
        if i < lookback or not closes[i - lookback]:
            continue
        roc = closes[i] / closes[i - lookback] - 1.0
        last_roc = roc
        want[i] = roc > 0
    return _run_position_series(
        closes, dates, want, extra={"roc": round(last_roc, 6) if last_roc is not None else None}, **risk
    )


def _run_mean_reversion(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    ma = _sma(closes, period)
    std = _rolling_std(closes, period)
    want = [False] * len(closes)
    held = False
    last_z = None
    for i, close in enumerate(closes):
        mid, sd = ma[i], std[i]
        if mid is None or not sd:
            want[i] = held
            continue
        z = (close - mid) / sd
        last_z = z
        if z <= -2.0:
            held = True
        elif z >= 0:
            held = False
        want[i] = held
    return _run_position_series(
        closes, dates, want, extra={"zscore": round(last_z, 4) if last_z is not None else None}, **risk
    )


def _run_breakout(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    highs = _rolling_ext(closes, period, high=True)
    lows = _rolling_ext(closes, max(5, period // 2), high=False)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        prev_high = highs[i - 1] if i > 0 else None
        prev_low = lows[i - 1] if i > 0 else None
        if prev_high is not None and close > prev_high:
            held = True
        elif prev_low is not None and close < prev_low:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, **risk)


def _kdj_lines(closes: list[float], period: int = 9) -> tuple[list[float | None], list[float | None]]:
    rsv: list[float | None] = [None] * len(closes)
    window = max(2, int(period or 9))
    for i in range(window - 1, len(closes)):
        chunk = closes[i - window + 1 : i + 1]
        lo, hi = min(chunk), max(chunk)
        rsv[i] = 50.0 if hi == lo else 100.0 * (closes[i] - lo) / (hi - lo)
    k_line = _sma([item if item is not None else 50.0 for item in rsv], 3)
    d_line = _sma([item if item is not None else 50.0 for item in k_line], 3)
    return k_line, d_line


def _run_kdj(closes: list[float], dates: list[str], period: int = 9, **risk: Any) -> dict[str, Any]:
    k_line, d_line = _kdj_lines(closes, period)
    want = [False] * len(closes)
    for i, (k_val, d_val) in enumerate(zip(k_line, d_line)):
        if k_val is None or d_val is None:
            continue
        want[i] = k_val > d_val
    extra = {"k": k_line[-1], "d": d_line[-1]}
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_ema_cross(closes: list[float], dates: list[str], short: int, long: int, **risk: Any) -> dict[str, Any]:
    fast = _ema(closes, short)
    slow = _ema(closes, long)
    want = [False] * len(closes)
    for i, (a, b) in enumerate(zip(fast, slow)):
        if a is None or b is None:
            continue
        want[i] = a > b
    extra = {"ema_fast": fast[-1], "ema_slow": slow[-1]}
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_triple_ma(closes: list[float], dates: list[str], short: int, long: int, **risk: Any) -> dict[str, Any]:
    mid = max(short + 1, min((short + long) // 2, long - 1))
    a, b, c = _sma(closes, short), _sma(closes, mid), _sma(closes, long)
    want = [False] * len(closes)
    for i in range(len(closes)):
        if a[i] is None or b[i] is None or c[i] is None:
            continue
        want[i] = a[i] > b[i] > c[i]
    return _run_position_series(closes, dates, want, extra={"mid": mid}, **risk)


def _run_donchian(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    highs = _rolling_ext(closes, period, high=True)
    lows = _rolling_ext(closes, period, high=False)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        prev_high = highs[i - 1] if i else None
        prev_low = lows[i - 1] if i else None
        if prev_high is not None and close >= prev_high:
            held = True
        elif prev_low is not None and close <= prev_low:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"period": period}, **risk)


def _run_turtle(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    return _run_donchian(closes, dates, period=period, **risk)
