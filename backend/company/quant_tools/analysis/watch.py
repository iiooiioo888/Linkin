"""量化分析：簡易盯盤（漲跌幅、均線位置、雙均線訊號）。"""

from __future__ import annotations

from typing import Any

from ..data import _fail, _load_bars, normalize_symbol
from ..indicators import _sma
from ..strategies_advanced import _run_dual_ma


def market_watch(symbol: str, drop_pct: float = 3.0) -> dict[str, Any]:
    """簡易盯盤：漲跌幅、均線位置、雙均線訊號。"""
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, "6mo", "1d")
        closes = [float(b["c"]) for b in bars if b.get("c") is not None]
        dates = [str(b["t"]) for b in bars if b.get("c") is not None]
        if len(closes) < 25:
            return _fail("K 線不足，無法盯盤", tool="market_watch", symbol=code)
        last, prev = closes[-1], closes[-2]
        pct = (last / prev - 1.0) * 100 if prev else 0.0
        ma20 = _sma(closes, 20)[-1]
        dual = _run_dual_ma(closes, dates, 5, 20)
        alerts: list[str] = []
        threshold = abs(float(drop_pct) or 3.0)
        if pct <= -threshold:
            alerts.append(f"單日下跌 {pct:.2f}%（門檻 {threshold:g}%）")
        if pct >= threshold:
            alerts.append(f"單日上漲 {pct:.2f}%（門檻 {threshold:g}%）")
        if ma20:
            if last < ma20:
                alerts.append("收盤跌破 MA20")
            else:
                alerts.append("收盤站上 MA20")
        if dual["last_signal"] == "long":
            alerts.append("雙均線偏多")
        elif dual["last_signal"] == "cash":
            alerts.append("雙均線偏空／空倉")
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "as_of": dates[-1],
            "close": last,
            "pct_change": round(pct, 4),
            "ma20": round(ma20, 4) if ma20 is not None else None,
            "last_signal": dual["last_signal"],
            "alerts": alerts,
            "disclaimer": "預警僅反映技術條件，非進出場指令。",
        }
    except Exception as ext:
        return _fail(ext, tool="market_watch", query=symbol)
