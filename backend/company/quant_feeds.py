"""額外行情來源：新浪免 Key，以及可選的 Tushare／Finnhub／Alpha Vantage。

不引入 yfinance／akshare。金鑰走環境變數，未設定時工具仍可用免費源。
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

_TIMEOUT = 20.0
_UA = "Mozilla/5.0 (compatible; LinkinQuant/1.0)"
_MAX_BARS = 240


def keyed_status() -> dict[str, Any]:
    tokens = env_tokens()
    return {
        "tushare": bool(tokens["tushare"]),
        "finnhub": bool(tokens["finnhub"]),
        "alphavantage": bool(tokens["alphavantage"]),
        "itick": bool(tokens["itick"]),
    }


def env_tokens() -> dict[str, str]:
    return {
        "tushare": (os.getenv("EVOL_TUSHARE_TOKEN") or os.getenv("TUSHARE_TOKEN") or "").strip(),
        "finnhub": (os.getenv("EVOL_FINNHUB_TOKEN") or os.getenv("FINNHUB_API_KEY") or "").strip(),
        "alphavantage": (
            os.getenv("EVOL_ALPHAVANTAGE_KEY") or os.getenv("ALPHAVANTAGE_API_KEY") or ""
        ).strip(),
        "itick": (os.getenv("EVOL_ITICK_TOKEN") or os.getenv("ITICK_TOKEN") or "").strip(),
    }


def _headers(referer: str = "https://finance.sina.com.cn/") -> dict[str, str]:
    return {
        "User-Agent": _UA,
        "Accept": "application/json,text/plain,*/*",
        "Referer": referer,
    }


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _get_json(url: str, params: dict[str, Any] | None = None, referer: str = "") -> Any:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_headers(referer or url))
        resp.raise_for_status()
        return resp.json()


def _get_bytes(url: str, params: dict[str, Any] | None = None) -> bytes:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_headers())
        resp.raise_for_status()
        return resp.content


def _post_json(url: str, payload: dict[str, Any]) -> Any:
    with httpx.Client(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = client.post(url, json=payload, headers=_headers("https://tushare.pro/"))
        resp.raise_for_status()
        return resp.json()


def sina_symbol(yahoo_symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", (yahoo_symbol or "").upper())
    if not match:
        return None
    code, exch = match.group(1), match.group(2)
    if exch == "SS":
        return f"sh{code}"
    if exch == "BJ":
        return f"bj{code}"
    return f"sz{code}"


def sina_realtime(symbol: str) -> dict[str, Any]:
    sid = sina_symbol(symbol)
    if not sid:
        raise RuntimeError("新浪即時僅支援 A 股")
    raw = _get_bytes(f"https://hq.sinajs.cn/list={sid}")
    text = raw.decode("gbk", errors="ignore")
    match = re.search(r'"([^"]*)"', text)
    if not match:
        raise RuntimeError("新浪即時為空")
    parts = match.group(1).split(",")
    if len(parts) < 9:
        raise RuntimeError("新浪即時欄位不足")
    close = _num(parts[3])
    prev = _num(parts[2])
    if close is None:
        raise RuntimeError("新浪無最新價")
    change = round(close - prev, 6) if prev else None
    pct = round((close / prev - 1.0) * 100, 4) if prev else None
    return {
        "ok": True,
        "source": "sina",
        "symbol": symbol,
        "name": parts[0],
        "open": _num(parts[1]),
        "prev_close": prev,
        "close": close,
        "high": _num(parts[4]),
        "low": _num(parts[5]),
        "volume": _num(parts[8]),
        "change": change,
        "pct_change": pct,
        "as_of": f"{parts[30]} {parts[31]}".strip() if len(parts) > 31 else None,
        "disclaimer": "新浪公開盤口，非官方 API。",
    }


def sina_bars(symbol: str, interval: str = "1d", limit: int = 180) -> list[dict[str, Any]]:
    sid = sina_symbol(symbol)
    if not sid:
        raise RuntimeError("新浪 K 線僅支援 A 股")
    scale = {"1d": "240", "1wk": "1200", "5d": "240", "60m": "60", "30m": "30", "15m": "15", "5m": "5"}.get(
        interval, "240"
    )
    rows = _get_json(
        "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData",
        {"symbol": sid, "scale": scale, "ma": "no", "datalen": str(max(20, min(int(limit), _MAX_BARS)))},
    )
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("新浪 K 線為空")
    bars: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close = _num(row.get("close"))
        if close is None:
            continue
        bars.append(
            {
                "t": str(row.get("day") or "")[:16],
                "o": _num(row.get("open")),
                "h": _num(row.get("high")),
                "l": _num(row.get("low")),
                "c": close,
                "v": _num(row.get("volume")),
            }
        )
    if not bars:
        raise RuntimeError("新浪 K 線無有效收盤")
    return bars[-_MAX_BARS:]


def tushare_bars(symbol: str, limit: int = 180) -> list[dict[str, Any]]:
    token = env_tokens()["tushare"]
    if not token:
        raise RuntimeError("未設定 EVOL_TUSHARE_TOKEN")
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", (symbol or "").upper())
    if not match:
        raise RuntimeError("Tushare 日線目前僅接 A 股")
    code, exch = match.group(1), match.group(2)
    suffix = {"SS": "SH", "SZ": "SZ", "BJ": "BJ"}[exch]
    data = _post_json(
        "http://api.tushare.pro",
        {
            "api_name": "daily",
            "token": token,
            "params": {"ts_code": f"{code}.{suffix}", "limit": max(20, min(int(limit), _MAX_BARS))},
            "fields": "trade_date,open,high,low,close,vol",
        },
    )
    items = ((data or {}).get("data") or {}).get("items") if isinstance(data, dict) else None
    if not items:
        raise RuntimeError(str((data or {}).get("msg") or "Tushare 無資料")[:200])
    bars: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, list) or len(row) < 5:
            continue
        day = str(row[0])
        stamp = f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 else day
        close = _num(row[4])
        if close is None:
            continue
        bars.append(
            {
                "t": stamp,
                "o": _num(row[1]),
                "h": _num(row[2]),
                "l": _num(row[3]),
                "c": close,
                "v": _num(row[5]) if len(row) > 5 else None,
            }
        )
    bars.sort(key=lambda item: str(item.get("t") or ""))
    if not bars:
        raise RuntimeError("Tushare 日線為空")
    return bars[-_MAX_BARS:]


def finnhub_quote(symbol: str) -> dict[str, Any]:
    token = env_tokens()["finnhub"]
    if not token:
        raise RuntimeError("未設定 EVOL_FINNHUB_TOKEN")
    data = _get_json("https://finnhub.io/api/v1/quote", {"symbol": symbol, "token": token})
    price = _num((data or {}).get("c"))
    if price is None:
        raise RuntimeError("Finnhub 報價為空")
    return {
        "ok": True,
        "source": "finnhub",
        "symbol": symbol,
        "close": price,
        "open": _num(data.get("o")),
        "high": _num(data.get("h")),
        "low": _num(data.get("l")),
        "prev_close": _num(data.get("pc")),
        "change": _num(data.get("d")),
        "pct_change": _num(data.get("dp")),
        "disclaimer": "Finnhub 免費層約 60 次/分鐘。",
    }


def finnhub_bars(symbol: str) -> list[dict[str, Any]]:
    token = env_tokens()["finnhub"]
    if not token:
        raise RuntimeError("未設定 EVOL_FINNHUB_TOKEN")
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=400)
    data = _get_json(
        "https://finnhub.io/api/v1/stock/candle",
        {
            "symbol": symbol,
            "resolution": "D",
            "from": int(start.timestamp()),
            "to": int(now.timestamp()),
            "token": token,
        },
    )
    if not isinstance(data, dict) or data.get("s") != "ok":
        raise RuntimeError("Finnhub K 線不可用")
    closes = data.get("c") or []
    times = data.get("t") or []
    bars: list[dict[str, Any]] = []
    for i, ts in enumerate(times):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        bars.append(
            {
                "t": datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d"),
                "o": _num((data.get("o") or [None])[i] if i < len(data.get("o") or []) else None),
                "h": _num((data.get("h") or [None])[i] if i < len(data.get("h") or []) else None),
                "l": _num((data.get("l") or [None])[i] if i < len(data.get("l") or []) else None),
                "c": _num(close),
                "v": _num((data.get("v") or [None])[i] if i < len(data.get("v") or []) else None),
            }
        )
    if not bars:
        raise RuntimeError("Finnhub K 線為空")
    return bars[-_MAX_BARS:]


def alphavantage_quote(symbol: str) -> dict[str, Any]:
    key = env_tokens()["alphavantage"]
    if not key:
        raise RuntimeError("未設定 EVOL_ALPHAVANTAGE_KEY")
    data = _get_json(
        "https://www.alphavantage.co/query",
        {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key},
    )
    row = (data or {}).get("Global Quote") if isinstance(data, dict) else None
    if not isinstance(row, dict):
        raise RuntimeError(str((data or {}).get("Note") or "Alpha Vantage 報價為空")[:200])
    close = _num(row.get("05. price"))
    if close is None:
        raise RuntimeError("Alpha Vantage 無最新價")
    return {
        "ok": True,
        "source": "alpha_vantage",
        "symbol": symbol,
        "open": _num(row.get("02. open")),
        "high": _num(row.get("03. high")),
        "low": _num(row.get("04. low")),
        "close": close,
        "volume": _num(row.get("06. volume")),
        "prev_close": _num(row.get("08. previous close")),
        "change": _num(row.get("09. change")),
        "pct_change": _num(str(row.get("10. change percent") or "").replace("%", "")),
        "as_of": row.get("07. latest trading day"),
        "disclaimer": "Alpha Vantage 免費層約 25 次/日。",
    }


def alphavantage_bars(symbol: str) -> list[dict[str, Any]]:
    key = env_tokens()["alphavantage"]
    if not key:
        raise RuntimeError("未設定 EVOL_ALPHAVANTAGE_KEY")
    data = _get_json(
        "https://www.alphavantage.co/query",
        {"function": "TIME_SERIES_DAILY", "symbol": symbol, "apikey": key, "outputsize": "compact"},
    )
    series = (data or {}).get("Time Series (Daily)") if isinstance(data, dict) else None
    if not isinstance(series, dict):
        raise RuntimeError(str((data or {}).get("Note") or "Alpha Vantage 日線為空")[:200])
    bars: list[dict[str, Any]] = []
    for day, row in series.items():
        if not isinstance(row, dict):
            continue
        close = _num(row.get("4. close"))
        if close is None:
            continue
        bars.append(
            {
                "t": day,
                "o": _num(row.get("1. open")),
                "h": _num(row.get("2. high")),
                "l": _num(row.get("3. low")),
                "c": close,
                "v": _num(row.get("5. volume")),
            }
        )
    bars.sort(key=lambda item: str(item.get("t") or ""))
    if not bars:
        raise RuntimeError("Alpha Vantage 日線為空")
    return bars[-_MAX_BARS:]
