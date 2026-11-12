"""量價策略 runner（自 backend.company.quant_tools.strategies 抽出）。

量價策略 runner（Williams／CCI／量能熱度／單量／增強量／量價）。
"""

from __future__ import annotations

from typing import Any

from ..indicators import _rolling_std, _rsi, _sma
from .runner import _kdj_lines, _run_position_series


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
