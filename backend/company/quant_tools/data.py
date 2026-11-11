"""量化行情抓取：HTTP helper、標的別名正規化、Yahoo／東方財富／Stooq／外匯／加密行情。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .constants import (
    _HTTP_TIMEOUT,
    _KLT_MAP,
    _MAX_BARS,
    _RANGE_MAP,
    _SH_INDEX_CODES,
    _UA,
    COINGECKO_IDS,
    CRYPTO_IDS,
    QUANT_TOOL_NAMES,
    STRATEGY_NAMES,
    SYMBOL_ALIASES,
)


def dumps_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def normalize_symbol(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise ValueError("symbol 不可為空")
    alias = SYMBOL_ALIASES.get(text) or SYMBOL_ALIASES.get(text.replace(" ", ""))
    if alias:
        return alias
    if re.fullmatch(r"\d{6}", text):
        # 滬深指數代碼在上交所（000001.SZ 仍是平安銀行，指數請用別名「上證」）
        if text.startswith(("6", "9")) or text in _SH_INDEX_CODES:
            return f"{text}.SS"
        if text.startswith(("8", "4")):
            return f"{text}.BJ"
        return f"{text}.SZ"
    return text.upper() if text.isascii() else text


def _a_share_code(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", symbol.upper())
    return match.group(1) if match else None


def _eastmoney_secid(symbol: str) -> str | None:
    match = re.fullmatch(r"(\d{6})\.(SS|SZ|BJ)", symbol.upper())
    if not match:
        return None
    code, exch = match.group(1), match.group(2)
    prefix = {"SS": "1", "SZ": "0", "BJ": "0"}.get(exch, "1")
    return f"{prefix}.{code}"


def _http_headers() -> dict[str, str]:
    return {
        "User-Agent": _UA,
        "Accept": "application/json,text/csv,text/plain,*/*",
        "Referer": "https://finance.eastmoney.com/",
    }


def _http_get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_http_headers())
        resp.raise_for_status()
        return resp.json()


def _http_get_text(url: str, params: dict[str, Any] | None = None) -> str:
    with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=_http_headers())
        resp.raise_for_status()
        return resp.text


def _fail(error: str | BaseException, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": str(error)[:400], **extra}
    payload.setdefault("disclaimer", "公開數據僅供研究，非投資建議。")
    return payload


def _yahoo_chart(symbol: str, range_: str, interval: str) -> dict[str, Any]:
    params = {"range": range_, "interval": interval, "includePrePost": "false"}
    last_err: str | None = None
    for host in ("query1.finance.yahoo.com", "query2.finance.yahoo.com"):
        url = f"https://{host}/v8/finance/chart/{symbol}"
        try:
            data = _http_get_json(url, params)
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
    data = _http_get_json(
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


def _stooq_ticker(symbol: str) -> str | None:
    if _a_share_code(symbol):
        return None
    text = symbol.strip().lower()
    if "." not in text:
        return f"{text}.us"
    if text.endswith((".ss", ".sz", ".bj")):
        return None
    return text


def _bars_from_stooq(symbol: str) -> list[dict[str, Any]]:
    ticker = _stooq_ticker(symbol)
    if not ticker:
        raise RuntimeError("Stooq 不適用此代碼")
    text = _http_get_text("https://stooq.com/q/d/l/", {"s": ticker, "i": "d"})
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


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def market_sources() -> dict[str, Any]:
    from backend.company.quant_feeds import keyed_status

    keyed = keyed_status()
    return {
        "ok": True,
        "primary": "yahoo",
        "inspired_by": "https://github.com/iiooiioo888/stock-quant",
        "tools": list(QUANT_TOOL_NAMES),
        "strategies": [{"id": key, "name": label} for key, label in STRATEGY_NAMES.items()],
        "strategy_catalog": "market_strategy_catalog",
        "portfolio_methods": [
            "equal_weight",
            "risk_parity",
            "vol_target",
            "kelly",
            "mvo",
            "max_div",
            "anti_corr",
            "regime",
            "frontier",
            "dynamic",
            "degradation",
        ],
        "sources": [
            {"id": "yahoo", "markets": ["A股", "美股", "指數"], "auth": False, "wired": True, "role": "主行情／K 線"},
            {"id": "eastmoney", "markets": ["A股"], "auth": False, "wired": True, "role": "K 線備援、基本面、資金流、板塊、龍虎榜、分鐘線"},
            {"id": "sina", "markets": ["A股"], "auth": False, "wired": True, "role": "即時盤口與日 K 備援"},
            {"id": "stooq", "markets": ["美股"], "auth": False, "wired": True, "role": "Yahoo 失敗時日 K 備援"},
            {"id": "frankfurter", "markets": ["外匯"], "auth": False, "wired": True, "role": "歐洲央行日頻匯率"},
            {"id": "currency_api", "markets": ["外匯"], "auth": False, "wired": True, "role": "fawazahmed0 匯率備援"},
            {"id": "coinpaprika", "markets": ["加密貨幣"], "auth": False, "wired": True, "role": "全市場報價，無需 Key"},
            {"id": "coingecko", "markets": ["加密貨幣"], "auth": False, "wired": True, "role": "CoinPaprika 備援"},
            {"id": "binance", "markets": ["加密貨幣"], "auth": False, "wired": True, "role": "交易所 24h ticker 備援"},
            {"id": "tushare", "markets": ["A股"], "auth": True, "wired": keyed["tushare"], "role": "積分制；設 EVOL_TUSHARE_TOKEN 後作為 A 股備援"},
            {"id": "finnhub", "markets": ["美股"], "auth": True, "wired": keyed["finnhub"], "role": "免費層 60 次/分；設 EVOL_FINNHUB_TOKEN"},
            {"id": "alpha_vantage", "markets": ["美股", "外匯", "加密"], "auth": True, "wired": keyed["alphavantage"], "role": "免費層 25 次/日；設 EVOL_ALPHAVANTAGE_KEY"},
            {"id": "baostock", "markets": ["A股"], "auth": False, "wired": False, "role": "歷史資料，需本地庫，本倉庫不直連"},
            {"id": "itick", "markets": ["多市場"], "auth": True, "wired": keyed["itick"], "role": "需 Token；目錄項，未直連 REST"},
            {"id": "qos", "markets": ["多市場"], "auth": False, "wired": False, "role": "一站式行情，可選接入"},
            {"id": "akshare", "markets": ["A股"], "auth": False, "wired": False, "role": "不引入套件；東財／新浪 HTTP 對齊其公開源"},
        ],
        "disclaimer": "公開數據僅供研究，非投資建議。Hub StocksX 仍為沙箱測試工具。wired=false 僅供角色選擇，本倉庫未直連。",
    }


def market_quote(symbol: str) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, "5d", "1d")
        last = bars[-1]
        prev = bars[-2] if len(bars) > 1 else None
        last_close = last["c"]
        prev_close = prev["c"] if prev else None
        change = None
        pct = None
        if last_close is not None and prev_close:
            change = round(last_close - prev_close, 6)
            pct = round((last_close / prev_close - 1.0) * 100, 4)
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "as_of": last["t"],
            "open": last.get("o"),
            "high": last.get("h"),
            "low": last.get("l"),
            "close": last_close,
            "volume": last.get("v"),
            "change": change,
            "pct_change": pct,
            "disclaimer": "公開數據僅供研究，非投資建議。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_quote", query=symbol)


def market_kline(symbol: str, range: str = "1y", interval: str = "1d") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        range_ = _RANGE_MAP.get(range, "1y")
        interval_ = interval if interval in _KLT_MAP or interval in {"1d", "1wk"} else "1d"
        bars, source = _load_bars(code, range_, interval_)
        closes = [float(b["c"]) for b in bars if b.get("c") is not None]
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "range": range_,
            "interval": interval_,
            "bars": bars[-80:],
            "count": len(bars),
            "last_close": closes[-1] if closes else None,
            "disclaimer": "公開數據僅供研究，非投資建議。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_kline", query=symbol)


def fx_rate(base: str = "USD", quote: str = "CNY", date: str = "") -> dict[str, Any]:
    try:
        from_ccy = (base or "USD").strip().upper()
        to_ccy = (quote or "CNY").strip().upper()
        path = date.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", (date or "").strip()) else "latest"
        try:
            data = _http_get_json(
                f"https://api.frankfurter.app/{path}",
                {"from": from_ccy, "to": to_ccy},
            )
            rates = data.get("rates") if isinstance(data, dict) else None
            if isinstance(rates, dict) and to_ccy in rates:
                return {
                    "ok": True,
                    "source": "frankfurter",
                    "base": data.get("base", from_ccy),
                    "quote": to_ccy,
                    "rate": rates[to_ccy],
                    "as_of": data.get("date"),
                    "disclaimer": "歐洲央行參考匯率，每日更新一次，非即時。",
                }
        except Exception as frank_err:
            last = str(frank_err)[:200]
        else:
            last = "Frankfurter 無此幣對"
        data = _http_get_json(
            f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{from_ccy.lower()}.json"
        )
        bucket = data.get(from_ccy.lower()) if isinstance(data, dict) else None
        rate = bucket.get(to_ccy.lower()) if isinstance(bucket, dict) else None
        if rate is None:
            return _fail(last, tool="fx_rate", base=from_ccy, quote=to_ccy)
        return {
            "ok": True,
            "source": "currency_api",
            "base": from_ccy,
            "quote": to_ccy,
            "rate": rate,
            "as_of": data.get("date") if isinstance(data, dict) else None,
            "disclaimer": "社區匯率備援（fawazahmed0），每日更新，非即時。",
        }
    except Exception as exc:
        return _fail(exc, tool="fx_rate", base=base, quote=quote)


def crypto_quote(symbol: str = "BTC") -> dict[str, Any]:
    try:
        query = (symbol or "BTC").strip()
        coin_id = CRYPTO_IDS.get(query.upper())
        if not coin_id:
            if "-" in query:
                coin_id = query.lower()
            else:
                found = _http_get_json(
                    "https://api.coinpaprika.com/v1/search",
                    {"q": query, "c": "currencies", "limit": 1},
                )
                currencies = found.get("currencies") if isinstance(found, dict) else None
                if currencies:
                    coin_id = currencies[0].get("id")
        if not coin_id:
            return _fail(f"找不到加密貨幣 {query}", tool="crypto_quote")
        data = _http_get_json(f"https://api.coinpaprika.com/v1/tickers/{coin_id}")
        quotes = (data.get("quotes") or {}).get("USD") if isinstance(data, dict) else None
        if isinstance(quotes, dict):
            return {
                "ok": True,
                "source": "coinpaprika",
                "id": data.get("id"),
                "symbol": data.get("symbol"),
                "name": data.get("name"),
                "price_usd": quotes.get("price"),
                "pct_change_24h": quotes.get("percent_change_24h"),
                "volume_24h_usd": quotes.get("volume_24h"),
                "market_cap_usd": quotes.get("market_cap"),
                "as_of": data.get("last_updated"),
                "disclaimer": "公開數據僅供研究，非投資建議。",
            }
        gecko_id = COINGECKO_IDS.get(query.upper())
        if gecko_id:
            return _crypto_from_coingecko(query, gecko_id)
        return _crypto_from_binance(query)
    except Exception as exc:
        gecko_id = COINGECKO_IDS.get((symbol or "BTC").strip().upper())
        if gecko_id:
            try:
                return _crypto_from_coingecko(symbol, gecko_id)
            except Exception:
                pass
        try:
            return _crypto_from_binance(symbol)
        except Exception:
            pass
        return _fail(exc, tool="crypto_quote", query=symbol)


def _crypto_from_binance(query: str) -> dict[str, Any]:
    pair = f"{(query or 'BTC').strip().upper()}USDT"
    data = _http_get_json("https://api.binance.com/api/v3/ticker/24hr", {"symbol": pair})
    price = _num((data or {}).get("lastPrice")) if isinstance(data, dict) else None
    if price is None:
        raise RuntimeError("Binance 報價為空")
    return {
        "ok": True,
        "source": "binance",
        "id": pair,
        "symbol": pair.replace("USDT", ""),
        "name": pair,
        "price_usd": price,
        "pct_change_24h": _num(data.get("priceChangePercent")),
        "volume_24h_usd": _num(data.get("quoteVolume")),
        "disclaimer": "交易所公開 ticker，僅現貨 USDT 對。",
    }


def _crypto_from_coingecko(query: str, gecko_id: str) -> dict[str, Any]:
    data = _http_get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        {
            "ids": gecko_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        },
    )
    row = data.get(gecko_id) if isinstance(data, dict) else None
    if not isinstance(row, dict) or row.get("usd") is None:
        raise RuntimeError("CoinGecko 報價為空")
    return {
        "ok": True,
        "source": "coingecko",
        "id": gecko_id,
        "symbol": (query or "").upper(),
        "name": gecko_id,
        "price_usd": row.get("usd"),
        "pct_change_24h": row.get("usd_24h_change"),
        "volume_24h_usd": row.get("usd_24h_vol"),
        "market_cap_usd": row.get("usd_market_cap"),
        "disclaimer": "公開數據僅供研究，非投資建議。",
    }


def market_minutes(symbol: str, interval: str = "5m", limit: int = 80) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        if not _a_share_code(code):
            return _fail("分鐘 K 線目前僅支援 A 股（東方財富）", tool="market_minutes", symbol=code)
        period = interval if interval in _KLT_MAP else "5m"
        bars = _eastmoney_bars(code, period, max(20, min(int(limit or 80), _MAX_BARS)))
        return {
            "ok": True,
            "symbol": code,
            "source": "eastmoney",
            "interval": period,
            "bars": bars[-80:],
            "count": len(bars),
            "disclaimer": "分鐘線來自東財，僅供研究。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_minutes", query=symbol)


def market_realtime(symbol: str) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        if _a_share_code(code):
            try:
                from backend.company.quant_feeds import sina_realtime

                return sina_realtime(code)
            except Exception:
                pass
        return market_quote(code)
    except Exception as exc:
        return _fail(exc, tool="market_realtime", query=symbol)
