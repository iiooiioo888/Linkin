"""進階策略訊號：SAR／ATR 移動止損／MACD 系列／複合投票等 runner。"""

from __future__ import annotations

from typing import Any

from .indicators import _atr, _ema, _rolling_std, _rsi, _sma
from .strategies import _run_position_series, _run_rsi


def _run_envelope(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    ma = _sma(closes, period)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        mid = ma[i]
        if mid is None:
            want[i] = held
            continue
        if close <= mid * 0.95:
            held = True
        elif close >= mid * 1.05:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"ma": ma[-1]}, **risk)


def _run_obv(closes: list[float], dates: list[str], vols: list[float], period: int = 20, **risk: Any) -> dict[str, Any]:
    obv = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv.append(obv[-1] + vols[i])
        elif closes[i] < closes[i - 1]:
            obv.append(obv[-1] - vols[i])
        else:
            obv.append(obv[-1])
    ma = _sma(obv, period)
    want = [False] * len(closes)
    for i, value in enumerate(obv):
        if ma[i] is None:
            continue
        want[i] = value > ma[i]
    return _run_position_series(closes, dates, want, extra={"obv": obv[-1]}, **risk)


def _run_bollinger_squeeze(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    ma = _sma(closes, period)
    std = _rolling_std(closes, period)
    width = [
        (2 * sd / mid) if mid and sd is not None else None
        for mid, sd in zip(ma, std)
    ]
    want = [False] * len(closes)
    held = False
    squeezed = False
    for i, close in enumerate(closes):
        w, mid, sd = width[i], ma[i], std[i]
        if w is None or mid is None or sd is None:
            want[i] = held
            continue
        if w < 0.03:
            squeezed = True
        if squeezed and close > mid + 2 * sd:
            held = True
            squeezed = False
        elif close < mid:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, **risk)


def _run_supertrend(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    period: int = 10,
    **risk: Any,
) -> dict[str, Any]:
    atr = _atr(highs, lows, closes, period)
    want = [False] * len(closes)
    held = False
    last = None
    for i, close in enumerate(closes):
        if atr[i] is None:
            want[i] = held
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        upper, lower = hl2 + 3 * atr[i], hl2 - 3 * atr[i]
        last = lower
        if close > upper:
            held = True
        elif close < lower:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"band": last}, **risk)


def _run_adx_trend(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    period: int = 14,
    **risk: Any,
) -> dict[str, Any]:
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    tr: list[float] = [max(highs[0] - lows[0], 0.0)]
    for i in range(1, len(closes)):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        )
    atr = _sma(tr, period)
    pdi = [
        (100.0 * pd / a) if a else None
        for pd, a in zip(_sma(plus_dm, period), atr)
    ]
    mdi = [
        (100.0 * md / a) if a else None
        for md, a in zip(_sma(minus_dm, period), atr)
    ]
    dx: list[float] = []
    for p, m in zip(pdi, mdi):
        if p is None or m is None or (p + m) == 0:
            dx.append(0.0)
        else:
            dx.append(100.0 * abs(p - m) / (p + m))
    adx = _sma(dx, period)
    want = [False] * len(closes)
    for i in range(len(closes)):
        if adx[i] is None or pdi[i] is None or mdi[i] is None:
            continue
        want[i] = adx[i] >= 20 and pdi[i] > mdi[i]
    return _run_position_series(closes, dates, want, extra={"adx": adx[-1]}, **risk)


def _run_dual_thrust(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    period: int = 4,
    **risk: Any,
) -> dict[str, Any]:
    want = [False] * len(closes)
    held = False
    for i in range(len(closes)):
        if i < period:
            want[i] = held
            continue
        hh = max(highs[i - period : i])
        ll = min(lows[i - period : i])
        hc = max(closes[i - period : i])
        lc = min(closes[i - period : i])
        rng = max(hh - lc, hc - ll, 0.0)
        buy_line = closes[i - 1] + 0.5 * rng
        sell_line = closes[i - 1] - 0.5 * rng
        if closes[i] > buy_line:
            held = True
        elif closes[i] < sell_line:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, **risk)


def _run_grid(closes: list[float], dates: list[str], period: int = 20, **risk: Any) -> dict[str, Any]:
    ma = _sma(closes, period)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        mid = ma[i]
        if mid is None:
            want[i] = held
            continue
        if close <= mid * 0.97:
            held = True
        elif close >= mid * 1.03:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"ma": ma[-1]}, **risk)


def _run_vwap(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    vols: list[float],
    period: int = 20,
    **risk: Any,
) -> dict[str, Any]:
    typical = [(highs[i] + lows[i] + closes[i]) / 3.0 for i in range(len(closes))]
    pv = [typical[i] * vols[i] for i in range(len(closes))]
    want = [False] * len(closes)
    last = None
    for i in range(len(closes)):
        if i < period - 1:
            continue
        vol_sum = sum(vols[i - period + 1 : i + 1])
        if not vol_sum:
            continue
        vwap = sum(pv[i - period + 1 : i + 1]) / vol_sum
        last = vwap
        want[i] = closes[i] >= vwap
    return _run_position_series(closes, dates, want, extra={"vwap": last}, **risk)


def _run_composite(closes: list[float], dates: list[str], short: int, long: int, **risk: Any) -> dict[str, Any]:
    dual = _run_dual_ma(closes, dates, short, long)
    rsi = _run_rsi(closes, dates)
    macd = _run_macd(closes, dates)
    votes = [
        1 if dual.get("last_signal") == "long" else 0,
        1 if rsi.get("last_signal") == "long" else 0,
        1 if macd.get("last_signal") == "long" else 0,
    ]
    want = [False] * len(closes)
    if sum(votes) >= 2:
        for i in range(len(closes)):
            want[i] = True
    extra = {"votes": int(sum(votes)), "members": ["dual_ma", "rsi", "macd"]}
    return _run_position_series(closes, dates, want, extra=extra, **risk)


def _run_parabolic_sar(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    **risk: Any,
) -> dict[str, Any]:
    if len(closes) < 5:
        return _run_position_series(closes, dates, [False] * len(closes), extra={"sar": None}, **risk)
    af = 0.02
    up = closes[1] >= closes[0]
    ep = highs[0]
    sar = lows[0]
    want = [False] * len(closes)
    last = sar
    for i in range(1, len(closes)):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if lows[i] < sar:
                up = False
                sar = ep
                ep = lows[i]
                af = 0.02
            else:
                if highs[i] > ep:
                    ep = highs[i]
                    af = min(0.2, af + 0.02)
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if highs[i] > sar:
                up = True
                sar = ep
                ep = highs[i]
                af = 0.02
            else:
                if lows[i] < ep:
                    ep = lows[i]
                    af = min(0.2, af + 0.02)
        want[i] = up
        last = sar
    return _run_position_series(closes, dates, want, extra={"sar": last}, **risk)


def _run_atr_trail(
    closes: list[float],
    dates: list[str],
    highs: list[float],
    lows: list[float],
    period: int = 20,
    **risk: Any,
) -> dict[str, Any]:
    ma = _sma(closes, max(5, period))
    atr = _atr(highs, lows, closes, 14)
    want = [False] * len(closes)
    held = False
    peak = 0.0
    last_stop = None
    for i, close in enumerate(closes):
        if ma[i] is None or atr[i] is None:
            want[i] = held
            continue
        if not held:
            if close > ma[i]:
                held = True
                peak = close
        else:
            peak = max(peak, close)
            stop = peak - 2.5 * atr[i]
            last_stop = stop
            if close < stop or close < ma[i]:
                held = False
                peak = 0.0
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"atr_stop": last_stop, "ma": ma[-1]}, **risk)


def _run_ema_volume(
    closes: list[float],
    dates: list[str],
    vols: list[float],
    short: int = 12,
    long: int = 26,
    **risk: Any,
) -> dict[str, Any]:
    fast_n = max(2, min(int(short or 12), 40))
    slow_n = max(fast_n + 1, min(int(long or 26), 80))
    fast = _ema(closes, fast_n)
    slow = _ema(closes, slow_n)
    vol_ma = _sma(vols, 20)
    want = [False] * len(closes)
    held = False
    for i in range(len(closes)):
        if fast[i] is None or slow[i] is None or vol_ma[i] is None:
            want[i] = held
            continue
        gold = fast[i] > slow[i]
        prev_gold = False
        if i and fast[i - 1] is not None and slow[i - 1] is not None:
            prev_gold = fast[i - 1] > slow[i - 1]
        if gold and not prev_gold and vols[i] >= vol_ma[i] * 1.2:
            held = True
        elif not gold and prev_gold:
            held = False
        want[i] = held
    return _run_position_series(
        closes, dates, want, extra={"ema_fast": fast[-1], "ema_slow": slow[-1]}, **risk
    )


def _macd_lines(closes: list[float]) -> tuple[list[float | None], list[float | None]]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line: list[float | None] = [None] * len(closes)
    for i, (a, b) in enumerate(zip(ema12, ema26)):
        if a is not None and b is not None:
            macd_line[i] = a - b
    signal_src = [item if item is not None else 0.0 for item in macd_line]
    start = next((i for i, item in enumerate(macd_line) if item is not None), None)
    signal_line: list[float | None] = [None] * len(closes)
    if start is not None:
        sliced = _ema(signal_src[start:], 9)
        for i, val in enumerate(sliced):
            signal_line[start + i] = val
    return macd_line, signal_line


def _run_macd_rsi(closes: list[float], dates: list[str], **risk: Any) -> dict[str, Any]:
    macd_line, signal_line = _macd_lines(closes)
    rsi = _rsi(closes, 14)
    want = [False] * len(closes)
    held = False
    for i in range(len(closes)):
        macd, sig, rsi_v = macd_line[i], signal_line[i], rsi[i]
        if macd is None or sig is None or rsi_v is None:
            want[i] = held
            continue
        gold = macd > sig
        prev_gold = False
        if i and macd_line[i - 1] is not None and signal_line[i - 1] is not None:
            prev_gold = macd_line[i - 1] > signal_line[i - 1]
        if gold and not prev_gold and 35 < rsi_v < 68:
            held = True
        elif (not gold and prev_gold) or rsi_v >= 68:
            held = False
        want[i] = held
    return _run_position_series(closes, dates, want, extra={"rsi": rsi[-1]}, **risk)


def _run_pullback_ma(
    closes: list[float],
    dates: list[str],
    short: int = 10,
    long: int = 50,
    **risk: Any,
) -> dict[str, Any]:
    fast_n = max(2, min(int(short or 10), 30))
    slow_n = max(fast_n + 1, min(int(long or 50), 80))
    trend_n = max(slow_n + 1, 120)
    fast = _sma(closes, fast_n)
    slow = _sma(closes, slow_n)
    trend = _sma(closes, trend_n)
    want = [False] * len(closes)
    held = False
    for i, close in enumerate(closes):
        if fast[i] is None or slow[i] is None or trend[i] is None:
            want[i] = held
            continue
        gold = fast[i] > slow[i]
        prev_gold = False
        if i and fast[i - 1] is not None and slow[i - 1] is not None:
            prev_gold = fast[i - 1] > slow[i - 1]
        uptrend = close > trend[i] and slow[i] > trend[i]
        if gold and not prev_gold and uptrend:
            held = True
        elif (not gold and prev_gold) or close < slow[i]:
            held = False
        want[i] = held
    return _run_position_series(
        closes, dates, want, extra={"fast_ma": fast[-1], "slow_ma": slow[-1], "trend_ma": trend[-1]}, **risk
    )


def _run_dual_ma(closes: list[float], dates: list[str], short: int, long: int, **risk: Any) -> dict[str, Any]:
    short_ma = _sma(closes, short)
    long_ma = _sma(closes, long)
    want = [False] * len(closes)
    for i, (fast, slow) in enumerate(zip(short_ma, long_ma)):
        if fast is None or slow is None:
            continue
        want[i] = fast > slow
    last_s, last_l = short_ma[-1], long_ma[-1]
    return _run_position_series(closes, dates, want, extra={"short_ma": last_s, "long_ma": last_l}, **risk)


def _run_macd(closes: list[float], dates: list[str], **risk: Any) -> dict[str, Any]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line: list[float | None] = [None] * len(closes)
    for i, (a, b) in enumerate(zip(ema12, ema26)):
        if a is not None and b is not None:
            macd_line[i] = a - b
    signal_src = [item if item is not None else 0.0 for item in macd_line]
    start = next((i for i, item in enumerate(macd_line) if item is not None), None)
    signal_line: list[float | None] = [None] * len(closes)
    if start is not None:
        sliced = _ema(signal_src[start:], 9)
        for i, val in enumerate(sliced):
            signal_line[start + i] = val
    want = [False] * len(closes)
    for i, (macd, sig) in enumerate(zip(macd_line, signal_line)):
        if macd is None or sig is None:
            continue
        want[i] = macd > sig
    last_macd, last_sig = macd_line[-1], signal_line[-1]
    return _run_position_series(
        closes,
        dates,
        want,
        extra={
            "macd": last_macd,
            "signal": last_sig,
            "hist": (last_macd - last_sig) if last_macd is not None and last_sig is not None else None,
        },
        **risk,
    )
