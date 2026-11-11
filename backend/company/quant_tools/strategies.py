"""策略訊號與回測封裝：部位序列引擎、核心策略 runner 與績效打包。"""

from __future__ import annotations

from typing import Any

from .indicators import (
    _calmar,
    _ema,
    _max_drawdown,
    _rolling_ext,
    _rolling_std,
    _rsi,
    _sharpe,
    _sma,
    _sortino,
)


def _chart_points(dates: list[str], values: list[float], n: int = 96) -> list[dict[str, Any]]:
    if not values:
        return []
    length = min(len(values), len(dates) if dates else len(values))
    if length <= 0:
        return []
    if length <= n:
        idxs = list(range(length))
    else:
        step = (length - 1) / (n - 1)
        idxs = sorted({min(length - 1, round(i * step)) for i in range(n)})
        if idxs[-1] != length - 1:
            idxs.append(length - 1)
    points: list[dict[str, Any]] = []
    for i in idxs:
        stamp = dates[i] if i < len(dates) else str(i)
        points.append({"t": str(stamp), "v": round(float(values[i]), 6)})
    return points


def _pack_backtest(
    equity: list[float],
    trades: list[dict[str, Any]],
    signal: str,
    extra: dict[str, Any] | None = None,
    dates: list[str] | None = None,
    closes: list[float] | None = None,
    include_chart: bool = False,
) -> dict[str, Any]:
    wins = [t for t in trades if t.get("side") == "sell" and float(t.get("ret") or 0) > 0]
    sells = [t for t in trades if t.get("side") == "sell"]
    total_ret = equity[-1] / equity[0] - 1.0 if equity else 0.0
    payload = {
        "total_return": round(total_ret, 6),
        "max_drawdown": _max_drawdown(equity),
        "sharpe": _sharpe(equity),
        "sortino": _sortino(equity),
        "calmar": _calmar(equity),
        "trades": len(sells),
        "win_rate": round(len(wins) / len(sells), 4) if sells else None,
        "last_signal": signal,
        "recent_trades": trades[-8:],
        "equity_end": round(equity[-1], 6) if equity else 1.0,
    }
    if extra:
        payload.update(extra)
    if include_chart and equity:
        stamps = dates or [str(i) for i in range(len(equity))]
        hold: list[float] = []
        if closes and closes[0]:
            hold = [price / closes[0] for price in closes[: len(equity)]]
        payload["chart"] = {
            "equity": _chart_points(stamps, equity),
            "hold": _chart_points(stamps, hold) if hold else [],
            "close": _chart_points(stamps, closes[: len(equity)] if closes else []),
        }
    return payload


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


def _run_williams(closes: list[float], dates: list[str], period: int = 14, **risk: Any) -> dict[str, Any]:
    want = [False] * len(closes)
    held = False
    last = None
    for i in range(len(closes)):
        if i < period - 1:
            want[i] = held
            continue
        chunk = closes[i - period + 1 : i + 1]
        hi, lo = max(chunk), min(chunk)
        wr = 0.0 if hi == lo else -100.0 * (hi - closes[i]) / (hi - lo)
        last = wr
        if wr <= -80:
            held = True
        elif wr >= -20:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"williams_r": last}, **risk)


def _run_cci(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    period: int = 20,
    **risk: Any,
) -> dict[str, Any]:
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    ma = _sma(typical, period)
    want = [False] * len(closes)
    held = False
    last = None
    for i, tp in enumerate(typical):
        mid = ma[i]
        if mid is None or i < period - 1:
            want[i] = held
            continue
        chunk = typical[i - period + 1 : i + 1]
        md = sum(abs(item - mid) for item in chunk) / period
        cci = 0.0 if md == 0 else (tp - mid) / (0.015 * md)
        last = cci
        if cci <= -100:
            held = True
        elif cci >= 100:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"cci": last}, **risk)


def _candle_streak(closes: list[float], index: int) -> int:
    """連續陽線為正、陰線為負；根數為絕對值。"""
    if index < 1:
        return 0
    direction = 1 if closes[index] > closes[index - 1] else (-1 if closes[index] < closes[index - 1] else 0)
    if direction == 0:
        return 0
    count = 0
    j = index
    while j > 0:
        delta = closes[j] - closes[j - 1]
        if (direction > 0 and delta > 0) or (direction < 0 and delta < 0):
            count += 1
            j -= 1
            continue
        break
    return direction * count


def _volume_heat(
    vols: list[float],
    short: int = 5,
    long: int = 20,
) -> tuple[list[bool], list[float | None], list[float | None], list[float | None]]:
    """現量 vs 5／20 日均量，並用成交量標準差動態抬高閾值。"""
    short_n = max(2, int(short or 5))
    long_n = max(short_n + 1, int(long or 20))
    ma5 = _sma(vols, short_n)
    ma20 = _sma(vols, long_n)
    std = _rolling_std(vols, long_n)
    hot = [False] * len(vols)
    for i, vol in enumerate(vols):
        short_ma, long_ma, sd = ma5[i], ma20[i], std[i]
        if short_ma is None or long_ma is None:
            continue
        threshold = long_ma + 0.5 * sd if sd is not None else long_ma
        hot[i] = (vol > short_ma and vol > long_ma) or vol > threshold
    return hot, ma5, ma20, std


def _run_single_volume(
    closes: list[float],
    dates: list[str],
    vols: list[float],
    short: int = 5,
    long: int = 20,
    period: int = 0,
    **risk: Any,
) -> dict[str, Any]:
    """stock-quant SingleVolumeStrategy：只看成交量與連續陰陽線。"""
    need = max(2, int(period or 0) or 2)
    hot, ma5, ma20, std = _volume_heat(vols, short, long)
    want = [False] * len(closes)
    held = False
    last_grade = "none"
    for i in range(len(closes)):
        streak = _candle_streak(closes, i)
        ordinary_buy = hot[i] and streak >= need
        ordinary_sell = hot[i] and streak <= -need
        if ordinary_buy:
            held = True
            last_grade = "ordinary"
        elif ordinary_sell:
            held = False
            last_grade = "ordinary"
        want[i] = held
    extra = {
        "grade": last_grade,
        "vol_ma5": ma5[-1],
        "vol_ma20": ma20[-1],
        "vol_std": std[-1],
        "inspired_by": "stock-quant SingleVolumeStrategy",
    }
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_enhanced_volume(
    closes: list[float],
    dates: list[str],
    vols: list[float],
    short: int = 5,
    long: int = 20,
    period: int = 0,
    **risk: Any,
) -> dict[str, Any]:
    """stock-quant EnhancedVolumeStrategy：成交量 + RSI／布林／KDJ 協同過濾。"""
    need = max(2, int(period or 0) or 2)
    hot, ma5, ma20, std = _volume_heat(vols, short, long)
    rsi = _rsi(closes, 14)
    mid = _sma(closes, 20)
    px_std = _rolling_std(closes, 20)
    k_line, d_line = _kdj_lines(closes, 9)
    want = [False] * len(closes)
    held = False
    last_grade = "none"
    last_filters = {"rsi": False, "bollinger": False, "kdj": False}
    for i, close in enumerate(closes):
        streak = _candle_streak(closes, i)
        ordinary_buy = hot[i] and streak >= need
        ordinary_sell = hot[i] and streak <= -need
        rsi_v = rsi[i]
        rsi_prev = rsi[i - 1] if i else None
        rsi_buy = rsi_v is not None and (
            rsi_v < 40 or (rsi_prev is not None and rsi_prev < 50 <= rsi_v)
        )
        rsi_sell = rsi_v is not None and (
            rsi_v > 60 or (rsi_prev is not None and rsi_prev > 50 >= rsi_v)
        )
        band_mid, band_sd = mid[i], px_std[i]
        bb_buy = band_mid is not None and band_sd is not None and close <= band_mid - band_sd
        bb_sell = band_mid is not None and band_sd is not None and close >= band_mid + band_sd
        k_val, d_val = k_line[i], d_line[i]
        k_prev = k_line[i - 1] if i else None
        d_prev = d_line[i - 1] if i else None
        kdj_buy = (
            k_val is not None
            and d_val is not None
            and k_val > d_val
            and (k_val < 30 or (k_prev is not None and d_prev is not None and k_prev <= d_prev))
        )
        kdj_sell = (
            k_val is not None
            and d_val is not None
            and k_val < d_val
            and (k_val > 70 or (k_prev is not None and d_prev is not None and k_prev >= d_prev))
        )
        buy_n = int(rsi_buy) + int(bb_buy) + int(kdj_buy)
        sell_n = int(rsi_sell) + int(bb_sell) + int(kdj_sell)
        enhanced_buy = ordinary_buy and buy_n >= 2
        enhanced_sell = ordinary_sell and sell_n >= 2
        if enhanced_buy:
            held = True
            last_grade = "enhanced"
            last_filters = {"rsi": rsi_buy, "bollinger": bb_buy, "kdj": kdj_buy}
        elif enhanced_sell or (held and ordinary_sell):
            held = False
            last_grade = "enhanced" if enhanced_sell else "ordinary"
            last_filters = {"rsi": rsi_sell, "bollinger": bb_sell, "kdj": kdj_sell}
        elif ordinary_buy:
            last_grade = "ordinary"
        want[i] = held
    extra = {
        "grade": last_grade,
        "filters": last_filters,
        "vol_ma5": ma5[-1],
        "vol_ma20": ma20[-1],
        "vol_std": std[-1],
        "rsi": rsi[-1],
        "k": k_line[-1],
        "d": d_line[-1],
        "inspired_by": "stock-quant EnhancedVolumeStrategy",
    }
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_volume_price(
    closes: list[float],
    dates: list[str],
    vols: list[float],
    period: int = 20,
    **risk: Any,
) -> dict[str, Any]:
    pma = _sma(closes, period)
    vma = _sma(vols, period)
    want = [False] * len(closes)
    for i, close in enumerate(closes):
        if pma[i] is None or vma[i] is None:
            continue
        want[i] = close > pma[i] and vols[i] > (vma[i] or 0)
    return _run_position_series(closes, dates, want, **risk)
