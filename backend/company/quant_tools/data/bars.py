"""K 線抓取與解析：Yahoo／東方財富／Stooq 與來源降級鏈。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..constants import _KLT_MAP, _MAX_BARS
from . import _compat
from .symbols import _a_share_code, _eastmoney_secid, _stooq_ticker
from .util import _num


def _yahoo_chart(symbol: str, range_: str, interval: str) -> dict[str, Any]:
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    last_err: str | None = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            data = _compat.http_get_json(url, params)
            chart = data.get("chart") if isinstance(data, dict) else None
            if not isinstance(chart, dict):
                last_err = "Yahoo 回應格式無效"
                continue
            result = chart.get("result") or []
            if result:
                return result[0]
            err = chart.get("error") or "empty chart"
            last_err = str(err)[:200]
        except Exception as exc:
            last_err = str(exc)[:200]
    raise RuntimeError(f"Yahoo 無法取得 {symbol}: {last_err}")

def _bars_from_yahoo(result: dict[str, Any]) -> list[dict[str, Any]]:
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    bars: list[dict[str, Any]] = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        bars.append(
            {
                "t": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"),
                "o": _num(opens[i] if i < len(opens) else None),
                "h": _num(highs[i] if i < len(highs) else None),
                "l": _num(lows[i] if i < len(lows) else None),
                "c": _num(close),
                "v": _num(volumes[i] if i < len(volumes) else None),
            }
        )
    return bars[-_MAX_BARS:]

def _eastmoney_bars(symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
    secid = _eastmoney_secid(symbol)
    if not secid:
        raise RuntimeError("非 A 股代碼，無法使用東方財富備援")
    klt = _KLT_MAP.get(interval, "101")
    data = _compat.http_get_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": secid,
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
            "klt": klt,
            "fqt": "1",
            "end": "20500101",
            "lmt": str(max(20, min(limit, _MAX_BARS))),
        },
    )
    payload = data.get("data") if isinstance(data, dict) else None
    klines = (payload or {}).get("klines") if isinstance(payload, dict) else None
    if not klines:
        raise RuntimeError("東方財富 K 線為空")
    bars: list[dict[str, Any]] = []
    for row in klines:
        parts = str(row).split(",")
        if len(parts) < 6:
            continue
        bars.append(
            {
                "t": parts[0],
                "o": _num(parts[1]),
                "c": _num(parts[2]),
                "h": _num(parts[3]),
                "l": _num(parts[4]),
                "v": _num(parts[5]),
            }
        )
    return bars[-_MAX_BARS:]

def _bars_from_stooq(symbol: str) -> list[dict[str, Any]]:
    ticker = _stooq_ticker(symbol)
    if not ticker:
        raise RuntimeError("Stooq 不適用此代碼")
    text = _compat.http_get_text("https://stooq.com/q/d/l/", {"s": ticker, "i": "d"})
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 3 or "Not Found" in text:
        raise RuntimeError("Stooq 無資料")
    bars: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < 5:
            continue
        close = _num(parts[4])
        if close is None:
            continue
        bars.append(
            {
                "t": parts[0],
                "o": _num(parts[1]),
                "h": _num(parts[2]),
                "l": _num(parts[3]),
                "c": close,
                "v": _num(parts[5]) if len(parts) > 5 else None,
            }
        )
    bars.sort(key=lambda item: str(item.get("t") or ""))
    if not bars:
        raise RuntimeError("Stooq K 線為空")
    return bars[-_MAX_BARS:]

def _load_bars(symbol: str, range_: str, interval: str) -> tuple[list[dict[str, Any]], str]:
    yahoo_err = ""
    try:
        result = _yahoo_chart(symbol, range_, interval)
        bars = _bars_from_yahoo(result)
        if bars:
            return bars, "yahoo"
        yahoo_err = "Yahoo 無有效收盤價"
    except Exception as exc:
        yahoo_err = str(exc)[:200]
    errors = [yahoo_err] if yahoo_err else []
    daily = interval in ("1d", "1wk", "5d")
    if _a_share_code(symbol) and daily:
        try:
            return _eastmoney_bars(symbol, "1d" if interval == "5d" else interval, 180), "eastmoney"
        except Exception as exc:
            errors.append(f"東方財富：{exc}")
        try:
            from backend.company.quant_feeds import sina_bars

            return sina_bars(symbol, "1d" if interval == "5d" else interval), "sina"
        except Exception as exc:
            errors.append(f"新浪：{exc}")
        try:
            from backend.company.quant_feeds import tushare_bars

            return tushare_bars(symbol), "tushare"
        except Exception as exc:
            errors.append(f"Tushare：{exc}")
    if daily and _stooq_ticker(symbol):
        try:
            return _bars_from_stooq(symbol), "stooq"
        except Exception as exc:
            errors.append(f"Stooq：{exc}")
    if daily and not _a_share_code(symbol):
        try:
            from backend.company.quant_feeds import finnhub_bars

            return finnhub_bars(symbol), "finnhub"
        except Exception as exc:
            errors.append(f"Finnhub：{exc}")
        try:
            from backend.company.quant_feeds import alphavantage_bars

            return alphavantage_bars(symbol), "alpha_vantage"
        except Exception as exc:
            errors.append(f"Alpha Vantage：{exc}")
    raise RuntimeError("；".join(errors) or f"無法取得 {symbol} K 線")
