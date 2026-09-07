"""量化行情工具 — 角色可呼叫的免費數據源。

對齊 stock-quant（https://github.com/iiooiioo888/stock-quant）的角色側能力：
報價、K 線／分鐘線、31 策略回測（含 stock-quant 增強成交量／單成交量；滑點／T+1／漲跌停／移動止損）、
策略庫分類目錄、多策略對比、網格優化、Walk-Forward、熱力圖、訊號、排行、
組合方法、盯盤、基本面、資金流、北向、龍虎榜、板塊、選股、基準對比。
以 httpx 直連公開 API，不嵌入其 Web 工作站，也不引入 yfinance／akshare。

資料源（已接通）：
- 股票／指數：Yahoo → 東方財富／新浪（A 股）→ Stooq（美股）
- 可選金鑰：Tushare／Finnhub／Alpha Vantage（見 EVOL_* 環境變數）
- 外匯：Frankfurter（歐洲央行，免註冊）
- 加密貨幣：CoinPaprika（主）→ CoinGecko Demo → Binance
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.company.quant_strategy_catalog import market_strategy_catalog, resolve_strategy

_HTTP_TIMEOUT = 20.0
_UA = "Mozilla/5.0 (compatible; LinkinQuant/1.0; +https://github.com/iiooiioo888/Linkin)"
_MAX_BARS = 240

QUANT_ROLES = [
    "finance_lead",
    "quant_analyst",
    "risk_analyst",
    "market_data_eng",
    "portfolio_mgr",
    "sentiment_analyst",
    "analyst",
    "researcher",
    "manager",
]

SYMBOL_ALIASES = {
    "茅台": "600519.SS",
    "貴州茅台": "600519.SS",
    "贵州茅台": "600519.SS",
    "平安銀行": "000001.SZ",
    "平安银行": "000001.SZ",
    "五糧液": "000858.SZ",
    "五粮液": "000858.SZ",
    "中國平安": "601318.SS",
    "中国平安": "601318.SS",
    "美的集團": "000333.SZ",
    "美的集团": "000333.SZ",
    "上證": "000001.SS",
    "上证": "000001.SS",
    "滬深300": "000300.SS",
    "沪深300": "000300.SS",
    "hs300": "000300.SS",
}

CRYPTO_IDS = {
    "BTC": "btc-bitcoin",
    "ETH": "eth-ethereum",
    "USDT": "usdt-tether",
    "BNB": "bnb-binance-coin",
    "SOL": "sol-solana",
    "XRP": "xrp-xrp",
    "DOGE": "doge-dogecoin",
}

COINGECKO_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "DOGE": "dogecoin",
}

STRATEGY_NAMES = {
    "dual_ma": "雙均線金叉/死叉",
    "macd": "MACD 金叉/死叉",
    "rsi": "RSI 超買超賣",
    "bollinger": "布林帶均值回歸",
    "momentum": "動量 ROC",
    "mean_reversion": "Z-score 均值回歸",
    "breakout": "N 日高點突破",
    "kdj": "KDJ 隨機指標",
    "ema_cross": "EMA 金叉/死叉",
    "triple_ma": "三重均線",
    "turtle": "海龜趨勢",
    "donchian": "唐奇安通道",
    "williams_r": "威廉指標",
    "cci": "CCI 順勢",
    "volume_price": "量價齊升",
    "envelope": "均線通道",
    "obv": "OBV 能量潮",
    "bollinger_squeeze": "布林帶收窄突破",
    "supertrend": "SuperTrend",
    "adx_trend": "ADX 趨勢",
    "dual_thrust": "DualThrust 突破",
    "grid": "網格偏離",
    "vwap": "VWAP 偏離",
    "parabolic_sar": "拋物線 SAR",
    "atr_trail": "ATR 移動止損趨勢",
    "ema_volume": "EMA 量價確認",
    "macd_rsi": "MACD+RSI 過濾",
    "pullback_ma": "趨勢回調均線",
    "composite": "多策略投票",
    "single_volume": "單成交量",
    "enhanced_volume": "增強成交量（RSI／布林／KDJ）",
}

QUANT_TOOL_NAMES = [
    "market_quote",
    "market_kline",
    "market_backtest",
    "market_compare",
    "market_optimize",
    "market_walkforward",
    "market_heatmap",
    "market_signals",
    "market_leaderboard",
    "market_watch",
    "market_search",
    "market_screener",
    "market_fundamentals",
    "market_capital_flow",
    "market_north_flow",
    "market_dragon_tiger",
    "market_sectors",
    "market_portfolio",
    "market_minutes",
    "market_benchmark",
    "market_returns",
    "market_flow",
    "market_realtime",
    "fx_rate",
    "crypto_quote",
    "market_sources",
    "market_strategy_catalog",
]

_OPTIMIZE_GRIDS: dict[str, list[dict[str, int]]] = {
    "dual_ma": [{"short": s, "long": lng} for s in (3, 5, 8, 10) for lng in (15, 20, 30, 40) if s < lng],
    "ema_cross": [{"short": s, "long": lng} for s in (5, 8, 12) for lng in (20, 26, 40) if s < lng],
    "rsi": [{"period": p} for p in (7, 10, 14, 21)],
    "bollinger": [{"period": p} for p in (10, 15, 20, 30)],
    "momentum": [{"period": p} for p in (10, 15, 20, 30)],
    "breakout": [{"period": p} for p in (10, 20, 40, 60)],
    "kdj": [{"period": p} for p in (6, 9, 14)],
    "donchian": [{"period": p} for p in (10, 20, 40)],
    "ema_volume": [{"short": s, "long": lng} for s in (8, 12) for lng in (20, 26) if s < lng],
    "pullback_ma": [{"short": s, "long": lng} for s in (8, 10) for lng in (40, 50) if s < lng],
    "atr_trail": [{"period": p} for p in (15, 20, 30)],
    "single_volume": [{"short": s, "long": lng} for s in (3, 5) for lng in (10, 20) if s < lng],
    "enhanced_volume": [{"short": s, "long": lng} for s in (5,) for lng in (15, 20) if s < lng],
}

_RANGE_MAP = {
    "1d": "1d",
    "5d": "5d",
    "1mo": "1mo",
    "1m": "1mo",
    "3mo": "3mo",
    "3m": "3mo",
    "6mo": "6mo",
    "6m": "6mo",
    "1y": "1y",
    "2y": "2y",
    "5y": "5y",
}

_KLT_MAP = {"1m": "1", "5m": "5", "15m": "15", "30m": "30", "60m": "60", "1d": "101", "1wk": "102"}

# 上交所指數（與 000001.SZ 平安銀行等個股區分）
_SH_INDEX_CODES = {"000016", "000300", "000688", "000852", "000903", "000905", "000010"}


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


def _fail(error: str, **extra: Any) -> dict[str, Any]:
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
        except Exception as exc:  # noqa: BLE001
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
    if text.endswith(".ss") or text.endswith(".sz") or text.endswith(".bj"):
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
    except Exception as exc:  # noqa: BLE001
        yahoo_err = str(exc)[:200]
    errors = [yahoo_err] if yahoo_err else []
    daily = interval in ("1d", "1wk", "5d")
    if _a_share_code(symbol) and daily:
        try:
            return _eastmoney_bars(symbol, "1d" if interval == "5d" else interval, 180), "eastmoney"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"東方財富：{exc}")
        try:
            from backend.company.quant_feeds import sina_bars

            return sina_bars(symbol, "1d" if interval == "5d" else interval), "sina"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"新浪：{exc}")
        try:
            from backend.company.quant_feeds import tushare_bars

            return tushare_bars(symbol), "tushare"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Tushare：{exc}")
    if daily and _stooq_ticker(symbol):
        try:
            return _bars_from_stooq(symbol), "stooq"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Stooq：{exc}")
    if daily and not _a_share_code(symbol):
        try:
            from backend.company.quant_feeds import finnhub_bars

            return finnhub_bars(symbol), "finnhub"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Finnhub：{exc}")
        try:
            from backend.company.quant_feeds import alphavantage_bars

            return alphavantage_bars(symbol), "alpha_vantage"
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Alpha Vantage：{exc}")
    raise RuntimeError("；".join(errors) or f"無法取得 {symbol} K 線")


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
    return _pack_backtest(equity, trades, signal, extra=extra)


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


def _dispatch_strategy(
    name: str,
    closes: list[float],
    dates: list[str],
    short: int,
    long: int,
    period: int = 0,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    vols: list[float] | None = None,
    slippage_pct: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    trailing_stop_pct: float = 0.0,
    enable_t1: bool = False,
    enable_limit: bool = False,
) -> dict[str, Any]:
    risk = {
        "slippage_pct": slippage_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "enable_t1": enable_t1,
        "enable_limit": enable_limit,
    }
    hi = highs if highs is not None else closes
    lo = lows if lows is not None else closes
    vo = vols if vols is not None else [0.0] * len(closes)
    window = period if period and period > 0 else 0
    if name == "dual_ma":
        return _run_dual_ma(closes, dates, short, long, **risk)
    if name == "macd":
        return _run_macd(closes, dates, **risk)
    if name == "rsi":
        return _run_rsi(closes, dates, period=window or 14, **risk)
    if name == "bollinger":
        return _run_bollinger(closes, dates, period=window or 20, **risk)
    if name == "momentum":
        return _run_momentum(closes, dates, lookback=window or 20, **risk)
    if name == "mean_reversion":
        return _run_mean_reversion(closes, dates, period=window or 20, **risk)
    if name == "breakout":
        return _run_breakout(closes, dates, period=window or 20, **risk)
    if name == "kdj":
        return _run_kdj(closes, dates, period=window or 9, **risk)
    if name == "ema_cross":
        return _run_ema_cross(closes, dates, short, long, **risk)
    if name == "triple_ma":
        return _run_triple_ma(closes, dates, short, long, **risk)
    if name == "turtle":
        return _run_turtle(closes, dates, period=window or 20, **risk)
    if name == "donchian":
        return _run_donchian(closes, dates, period=window or 20, **risk)
    if name == "williams_r":
        return _run_williams(closes, dates, period=window or 14, **risk)
    if name == "cci":
        return _run_cci(closes, dates, hi, lo, period=window or 20, **risk)
    if name == "volume_price":
        return _run_volume_price(closes, dates, vo, period=window or 20, **risk)
    if name == "envelope":
        return _run_envelope(closes, dates, period=window or 20, **risk)
    if name == "obv":
        return _run_obv(closes, dates, vo, period=window or 20, **risk)
    if name == "bollinger_squeeze":
        return _run_bollinger_squeeze(closes, dates, period=window or 20, **risk)
    if name == "supertrend":
        return _run_supertrend(closes, dates, hi, lo, period=window or 10, **risk)
    if name == "adx_trend":
        return _run_adx_trend(closes, dates, hi, lo, period=window or 14, **risk)
    if name == "dual_thrust":
        return _run_dual_thrust(closes, dates, hi, lo, period=window or 4, **risk)
    if name == "grid":
        return _run_grid(closes, dates, period=window or 20, **risk)
    if name == "vwap":
        return _run_vwap(closes, dates, hi, lo, vo, period=window or 20, **risk)
    if name == "parabolic_sar":
        return _run_parabolic_sar(closes, dates, hi, lo, **risk)
    if name == "atr_trail":
        return _run_atr_trail(closes, dates, hi, lo, period=window or 20, **risk)
    if name == "ema_volume":
        return _run_ema_volume(closes, dates, vo, short=short, long=long, **risk)
    if name == "macd_rsi":
        return _run_macd_rsi(closes, dates, **risk)
    if name == "pullback_ma":
        return _run_pullback_ma(closes, dates, short=short, long=long, **risk)
    if name == "composite":
        return _run_composite(closes, dates, short, long, **risk)
    if name == "single_volume":
        return _run_single_volume(closes, dates, vo, short=short, long=long, period=window, **risk)
    if name == "enhanced_volume":
        return _run_enhanced_volume(closes, dates, vo, short=short, long=long, period=window, **risk)
    raise ValueError(f"不支援策略 {name}")


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


def _pack_backtest(
    equity: list[float],
    trades: list[dict[str, Any]],
    signal: str,
    extra: dict[str, Any] | None = None,
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
    return payload


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
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_kline", query=symbol)


def market_backtest(
    symbol: str,
    strategy: str = "dual_ma",
    range: str = "1y",
    short: int = 5,
    long: int = 20,
    period: int = 0,
    slippage_pct: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    trailing_stop_pct: float = 0.0,
    enable_t1: bool = False,
    enable_limit: bool = False,
) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        requested = (strategy or "dual_ma").strip().lower()
        name = resolve_strategy(requested)
        if not name:
            return _fail(
                f"不支援策略 {strategy}。先呼叫 market_strategy_catalog；可回測引擎：{' / '.join(STRATEGY_NAMES)}",
                tool="market_backtest",
                query=symbol,
            )
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 30:
            return _fail("K 線不足 30 根，無法回測", tool="market_backtest", symbol=code, count=len(closes))
        short_n = max(2, min(int(short), 60))
        long_n = max(short_n + 1, min(int(long), 200))
        stats = _dispatch_strategy(
            name,
            closes,
            dates,
            short_n,
            long_n,
            period=int(period or 0),
            highs=highs,
            lows=lows,
            vols=vols,
            slippage_pct=float(slippage_pct or 0),
            stop_loss_pct=float(stop_loss_pct or 0),
            take_profit_pct=float(take_profit_pct or 0),
            trailing_stop_pct=float(trailing_stop_pct or 0),
            enable_t1=bool(enable_t1),
            enable_limit=bool(enable_limit),
        )
        params: dict[str, Any]
        if name in {
            "dual_ma",
            "ema_cross",
            "triple_ma",
            "composite",
            "ema_volume",
            "pullback_ma",
            "single_volume",
            "enhanced_volume",
        }:
            params = {"short": short_n, "long": long_n}
        elif name in {"macd", "macd_rsi"}:
            params = {"fast": 12, "slow": 26, "signal": 9}
        else:
            params = {"strategy": name, "period": int(period or 0) or None}
        if slippage_pct or stop_loss_pct or take_profit_pct or trailing_stop_pct or enable_t1 or enable_limit:
            params.update(
                {
                    "slippage_pct": float(slippage_pct or 0),
                    "stop_loss_pct": float(stop_loss_pct or 0),
                    "take_profit_pct": float(take_profit_pct or 0),
                    "trailing_stop_pct": float(trailing_stop_pct or 0),
                    "enable_t1": bool(enable_t1),
                    "enable_limit": bool(enable_limit),
                }
            )
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "strategy": name,
            "requested_strategy": requested,
            "params": params,
            "bars": len(closes),
            **stats,
            "disclaimer": "回測可含滑點／止損，不含稅費，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_backtest", query=symbol)


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
    except Exception as ext:  # noqa: BLE001
        return _fail(ext, tool="market_watch", query=symbol)


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
        except Exception as frank_err:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
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
    except Exception as exc:  # noqa: BLE001
        gecko_id = COINGECKO_IDS.get((symbol or "BTC").strip().upper())
        if gecko_id:
            try:
                return _crypto_from_coingecko(symbol, gecko_id)
            except Exception:  # noqa: BLE001
                pass
        try:
            return _crypto_from_binance(symbol)
        except Exception:  # noqa: BLE001
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


def _eastmoney_ulist(symbol: str) -> dict[str, Any]:
    secid = _eastmoney_secid(symbol)
    if not secid:
        raise RuntimeError("非 A 股代碼")
    data = _http_get_json(
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        {
            "fltt": "2",
            "secids": secid,
            "fields": "f12,f14,f2,f3,f9,f23,f20,f21,f37,f115,f116,f117",
        },
    )
    diff = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("diff") or []
    if not diff:
        raise RuntimeError("東方財富基本面為空")
    return diff[0]


def _eastmoney_clist(fs: str, fields: str, fid: str, limit: int) -> list[dict[str, Any]]:
    data = _http_get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": "1",
            "pz": str(max(1, min(int(limit), 40))),
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": fid,
            "fs": fs,
            "fields": fields,
        },
    )
    payload = data.get("data") if isinstance(data, dict) else None
    rows = (payload or {}).get("diff") if isinstance(payload, dict) else None
    return rows if isinstance(rows, list) else []


def _eastmoney_datacenter(report_name: str, page_size: int = 15, extra: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "reportName": report_name,
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": str(max(1, min(int(page_size), 40))),
        "source": "WEB",
        "client": "WEB",
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
    }
    if extra:
        params.update(extra)
    data = _http_get_json("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    result = data.get("result") if isinstance(data, dict) else None
    rows = (result or {}).get("data") if isinstance(result, dict) else None
    return rows if isinstance(rows, list) else []


def market_compare(symbol: str, range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法對比", tool="market_compare", symbol=code)
        ranking: list[dict[str, Any]] = []
        for name in STRATEGY_NAMES:
            stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
            ranking.append(
                {
                    "strategy": name,
                    "name": STRATEGY_NAMES[name],
                    "total_return": stats.get("total_return"),
                    "max_drawdown": stats.get("max_drawdown"),
                    "sharpe": stats.get("sharpe"),
                    "trades": stats.get("trades"),
                    "win_rate": stats.get("win_rate"),
                    "last_signal": stats.get("last_signal"),
                }
            )
        ranking.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999), -(row.get("total_return") or 0)))
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "bars": len(closes),
            "ranking": ranking,
            "best": ranking[0] if ranking else None,
            "disclaimer": "對比不含滑點／稅費，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_compare", query=symbol)


def market_search(keyword: str) -> dict[str, Any]:
    try:
        query = (keyword or "").strip()
        if not query:
            return _fail("keyword 不可為空", tool="market_search")
        hits: list[dict[str, Any]] = []
        alias = SYMBOL_ALIASES.get(query) or SYMBOL_ALIASES.get(query.replace(" ", ""))
        if alias:
            hits.append({"symbol": alias, "name": query, "source": "alias"})
        if re.fullmatch(r"\d{6}", query):
            hits.append({"symbol": normalize_symbol(query), "name": query, "source": "code"})
        try:
            data = _http_get_json(
                "https://query1.finance.yahoo.com/v1/finance/search",
                {"q": query, "quotesCount": 8, "newsCount": 0},
            )
            for item in data.get("quotes") or []:
                symbol = item.get("symbol")
                if not symbol:
                    continue
                hits.append(
                    {
                        "symbol": symbol,
                        "name": item.get("shortname") or item.get("longname") or symbol,
                        "type": item.get("quoteType"),
                        "source": "yahoo",
                    }
                )
        except Exception:  # noqa: BLE001
            pass
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in hits:
            key = str(item.get("symbol"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return {"ok": True, "query": query, "hits": unique[:10], "disclaimer": "公開數據僅供研究，非投資建議。"}
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_search", query=keyword)


def market_screener(sort: str = "pct", limit: int = 15) -> dict[str, Any]:
    try:
        fid = {"pct": "f3", "pe": "f9", "mv": "f20"}.get((sort or "pct").strip().lower(), "f3")
        rows = _eastmoney_clist(
            "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "f12,f14,f2,f3,f6,f9,f20,f23",
            fid,
            limit,
        )
        items = [
            {
                "code": row.get("f12"),
                "name": row.get("f14"),
                "close": row.get("f2"),
                "pct": row.get("f3"),
                "pe": row.get("f9"),
                "pb": row.get("f23"),
                "market_cap": row.get("f20"),
            }
            for row in rows
            if row.get("f12")
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "sort": sort,
            "items": items,
            "disclaimer": "A 股盤面快照，非投資建議。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_screener")


def market_fundamentals(symbol: str) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        row = _eastmoney_ulist(code)
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": "eastmoney",
            "code": row.get("f12"),
            "name": row.get("f14"),
            "close": row.get("f2"),
            "pct": row.get("f3"),
            "pe": row.get("f9") or row.get("f115"),
            "pb": row.get("f23"),
            "roe": row.get("f37"),
            "market_cap": row.get("f20") or row.get("f116"),
            "circ_cap": row.get("f21") or row.get("f117"),
            "disclaimer": "基本面快照，口徑可能與財報不一致。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_fundamentals", query=symbol)


def market_capital_flow(symbol: str, days: int = 15) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        secid = _eastmoney_secid(code)
        if not secid:
            return _fail("僅支援 A 股資金流", tool="market_capital_flow", symbol=code)
        limit = max(5, min(int(days or 15), 40))
        data = _http_get_json(
            "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
            {
                "lmt": str(limit),
                "klt": "101",
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            },
        )
        klines = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("klines") or []
        flows: list[dict[str, Any]] = []
        for row in klines[-limit:]:
            parts = str(row).split(",")
            if len(parts) < 2:
                continue
            flows.append(
                {
                    "t": parts[0],
                    "main_net": _num(parts[1]),
                    "small_net": _num(parts[2]) if len(parts) > 2 else None,
                    "mid_net": _num(parts[3]) if len(parts) > 3 else None,
                    "large_net": _num(parts[4]) if len(parts) > 4 else None,
                    "super_net": _num(parts[5]) if len(parts) > 5 else None,
                }
            )
        return {
            "ok": True,
            "symbol": code,
            "source": "eastmoney",
            "flows": flows,
            "latest": flows[-1] if flows else None,
            "disclaimer": "主力淨額單位依東財口徑，僅供研究。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_capital_flow", query=symbol)


def market_north_flow(days: int = 15) -> dict[str, Any]:
    try:
        limit = max(5, min(int(days or 15), 40))
        rows = _eastmoney_datacenter("RPT_MUTUAL_DEAL_HISTORY", limit)
        daily: list[dict[str, Any]] = []
        for row in rows[:limit]:
            daily.append(
                {
                    "t": row.get("TRADE_DATE") or row.get("trade_date"),
                    "north_net": row.get("NORTH_NET_INFLOW") or row.get("NET_DEAL_AMT") or row.get("FUND_INFLOW"),
                    "buy": row.get("BUY_AMT") or row.get("BUY_VALUE"),
                    "sell": row.get("SELL_AMT") or row.get("SELL_VALUE"),
                }
            )
        return {
            "ok": True,
            "source": "eastmoney",
            "daily": daily,
            "latest": daily[0] if daily else None,
            "disclaimer": "滬深港通北向匯總，非即時成交。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_north_flow")


def market_dragon_tiger(limit: int = 15) -> dict[str, Any]:
    try:
        size = max(5, min(int(limit or 15), 30))
        rows = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            size,
            extra={"sortColumns": "TRADE_DATE,SECURITY_CODE", "sortTypes": "-1,-1"},
        )
        if not rows:
            rows = _eastmoney_datacenter("RPT_DAILYBILLBOARD_DETAILS", size)
        items = [
            {
                "code": row.get("SECURITY_CODE"),
                "name": row.get("SECURITY_NAME_ABBR") or row.get("SECURITY_NAME"),
                "t": row.get("TRADE_DATE"),
                "pct": row.get("CHANGE_RATE"),
                "net": row.get("BILLBOARD_NET_AMT") or row.get("NET_AMT"),
                "explain": row.get("EXPLAIN") or row.get("REASON"),
            }
            for row in rows[:size]
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "items": items,
            "disclaimer": "龍虎榜公開數據，非進出場指令。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_dragon_tiger")


def market_sectors(kind: str = "industry", limit: int = 15) -> dict[str, Any]:
    try:
        label = (kind or "industry").strip().lower()
        fs = "m:90+t:3" if label in {"concept", "概念"} else "m:90+t:2"
        rows = _eastmoney_clist(fs, "f12,f14,f2,f3,f62", "f3", limit)
        items = [
            {
                "code": row.get("f12"),
                "name": row.get("f14"),
                "close": row.get("f2"),
                "pct": row.get("f3"),
                "main_net": row.get("f62"),
            }
            for row in rows
            if row.get("f14")
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "kind": "concept" if fs.endswith("t:3") else "industry",
            "items": items,
            "disclaimer": "板塊漲跌快照，非投資建議。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_sectors")


_PORTFOLIO_METHODS = {
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
}


def _corr_pair(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 3:
        return 0.0
    ma = sum(left[:n]) / n
    mb = sum(right[:n]) / n
    cov = sum((left[i] - ma) * (right[i] - mb) for i in range(n)) / n
    sa = math.sqrt(sum((item - ma) ** 2 for item in left[:n]) / n)
    sb = math.sqrt(sum((item - mb) ** 2 for item in right[:n]) / n)
    if sa == 0 or sb == 0:
        return 0.0
    return cov / (sa * sb)


def _normalize_weights(raw: list[float]) -> list[float]:
    clipped = [max(0.0, float(item)) for item in raw]
    total = sum(clipped)
    if total <= 0:
        return [1.0 / len(raw)] * len(raw) if raw else []
    return [item / total for item in clipped]


def _portfolio_weights(mode: str, rets_by_leg: list[list[float]], vols: list[float]) -> list[float]:
    n = len(rets_by_leg)
    equal = [1.0 / n] * n
    if mode in {"equal_weight", "frontier"}:
        return equal
    if mode in {"risk_parity", "vol_target"}:
        inv = [1.0 / v for v in vols]
        return _normalize_weights(inv)
    means = [sum(row) / len(row) if row else 0.0 for row in rets_by_leg]
    vars_ = []
    for row, mean in zip(rets_by_leg, means):
        var = sum((item - mean) ** 2 for item in row) / len(row) if row else 1e-9
        vars_.append(max(var, 1e-12))
    if mode == "kelly":
        return _normalize_weights([means[i] / vars_[i] for i in range(n)])
    if mode == "mvo":
        best = equal
        best_score = -999.0
        steps = 5 if n <= 3 else 3
        if n == 2:
            for k in range(steps + 1):
                w0 = k / steps
                cand = [w0, 1.0 - w0]
                score = _portfolio_sharpe(cand, rets_by_leg)
                if score > best_score:
                    best_score = score
                    best = cand
            return best
        return _normalize_weights([max(m, 0.0) / v for m, v in zip(means, vars_)])
    if mode in {"max_div", "anti_corr"}:
        scores = []
        for i in range(n):
            corrs = [_corr_pair(rets_by_leg[i], rets_by_leg[j]) for j in range(n) if j != i]
            avg = sum(corrs) / len(corrs) if corrs else 0.0
            scores.append(max(0.01, 1.0 - avg))
        return _normalize_weights(scores)
    if mode == "regime":
        recent = [sum(row[-20:]) for row in rets_by_leg]
        if sum(recent) > 0:
            return _normalize_weights([max(item, 0.0) for item in recent])
        return equal
    if mode == "dynamic":
        window = [sum(row[-20:]) / max(len(row[-20:]), 1) for row in rets_by_leg]
        return _normalize_weights([max(item, 0.0) for item in window])
    if mode == "degradation":
        weights = list(equal)
        for i, row in enumerate(rets_by_leg):
            if sum(row[-20:]) < 0:
                weights[i] *= 0.5
        return _normalize_weights(weights)
    return equal


def _portfolio_sharpe(weights: list[float], rets_by_leg: list[list[float]]) -> float:
    if not rets_by_leg or not rets_by_leg[0]:
        return -999.0
    port = []
    for i in range(len(rets_by_leg[0])):
        port.append(sum(weights[j] * rets_by_leg[j][i] for j in range(len(weights))))
    mean = sum(port) / len(port)
    var = sum((item - mean) ** 2 for item in port) / len(port)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def market_portfolio(symbols: str, range: str = "1y", method: str = "equal_weight") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()]
        if len(parts) < 2:
            return _fail("請提供至少兩個標的，逗號分隔", tool="market_portfolio")
        mode = (method or "equal_weight").strip().lower()
        aliases = {
            "equal": "equal_weight",
            "ew": "equal_weight",
            "等權": "equal_weight",
            "rp": "risk_parity",
            "riskparity": "risk_parity",
            "vol": "vol_target",
            "volatility": "vol_target",
            "vt": "vol_target",
            "max_diversification": "max_div",
            "anti-correlation": "anti_corr",
            "regime-switch": "regime",
            "markowitz": "mvo",
        }
        mode = aliases.get(mode, mode)
        if mode not in _PORTFOLIO_METHODS:
            allowed = " / ".join(sorted(_PORTFOLIO_METHODS))
            return _fail(f"method 僅支援 {allowed}", tool="market_portfolio")
        legs: list[tuple[str, str, dict[str, float]]] = []
        errors: list[str] = []
        for raw in parts[:8]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                series = {str(b["t"]): float(b["c"]) for b in bars if b.get("c") is not None and b.get("t")}
                if series:
                    legs.append((code, source, series))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{raw}: {exc}")
        if len(legs) < 2:
            return _fail("有效標的不足兩個：" + "；".join(errors), tool="market_portfolio")
        common = set.intersection(*[set(item[2].keys()) for item in legs])
        dates = sorted(common)
        if len(dates) < 20:
            return _fail("共同交易日不足 20 根", tool="market_portfolio", dates=len(dates))
        rets_by_leg: list[list[float]] = []
        for _code, _src, series in legs:
            row: list[float] = []
            for i, day in enumerate(dates):
                if i == 0:
                    continue
                prev, cur = series[dates[i - 1]], series[day]
                row.append((cur / prev - 1.0) if prev else 0.0)
            rets_by_leg.append(row)
        vols = []
        for row in rets_by_leg:
            mean = sum(row) / len(row) if row else 0.0
            var = sum((item - mean) ** 2 for item in row) / len(row) if row else 0.0
            vols.append(math.sqrt(var) if var > 0 else 1e-9)
        weights = _portfolio_weights(mode, rets_by_leg, vols)
        frontier = None
        if mode == "frontier" and len(legs) >= 2:
            frontier = []
            # 參數名 range 會遮蔽內建 range()，此處用固定步長
            for k in (0, 1, 2, 3, 4):
                w0 = k / 4.0
                cand = [w0, 1.0 - w0] + [0.0] * (len(legs) - 2)
                if len(legs) > 2:
                    rest = (1.0 - w0) / (len(legs) - 1)
                    cand = [w0] + [rest] * (len(legs) - 1)
                frontier.append(
                    {
                        "weight_0": round(cand[0], 4),
                        "sharpe": round(_portfolio_sharpe(cand, rets_by_leg), 4),
                    }
                )
        target_vol = 0.12 / math.sqrt(252) if mode == "vol_target" else None
        equity = [1.0]
        port_rets: list[float] = []
        for i, _ret in enumerate(rets_by_leg[0]):
            avg = sum(weights[j] * rets_by_leg[j][i] for j, _leg in enumerate(legs))
            port_rets.append(avg)
        if target_vol is not None and port_rets:
            mean = sum(port_rets) / len(port_rets)
            var = sum((item - mean) ** 2 for item in port_rets) / len(port_rets)
            realized = math.sqrt(var) if var > 0 else target_vol
            scale = min(3.0, target_vol / realized) if realized else 1.0
            port_rets = [item * scale for item in port_rets]
            weights = [w * scale for w in weights]
        for avg in port_rets:
            equity.append(equity[-1] * (1.0 + avg))
        total_ret = equity[-1] / equity[0] - 1.0
        return {
            "ok": True,
            "method": mode,
            "weights": {code: round(weights[i], 4) for i, (code, _src, _series) in enumerate(legs)},
            "symbols": [item[0] for item in legs],
            "sources": list({item[1] for item in legs}),
            "bars": len(dates),
            "total_return": round(total_ret, 6),
            "max_drawdown": _max_drawdown(equity),
            "sharpe": _sharpe(equity),
            "sortino": _sortino(equity),
            "frontier": frontier,
            "errors": errors,
            "disclaimer": "組合不含再平衡成本，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_portfolio", query=symbols)


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
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_minutes", query=symbol)


def market_realtime(symbol: str) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        if _a_share_code(code):
            try:
                from backend.company.quant_feeds import sina_realtime

                return sina_realtime(code)
            except Exception:  # noqa: BLE001
                pass
        return market_quote(code)
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_realtime", query=symbol)


def market_flow(days: int = 15) -> dict[str, Any]:
    try:
        limit = max(5, min(int(days or 15), 40))
        data = _http_get_json(
            "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
            {
                "lmt": str(limit),
                "klt": "101",
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            },
        )
        klines = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("klines") or []
        flows: list[dict[str, Any]] = []
        for row in klines[-limit:]:
            parts = str(row).split(",")
            if len(parts) < 2:
                continue
            flows.append({"t": parts[0], "main_net": _num(parts[1]), "super_net": _num(parts[5]) if len(parts) > 5 else None})
        return {
            "ok": True,
            "source": "eastmoney",
            "benchmark": "000001.SS",
            "flows": flows,
            "latest": flows[-1] if flows else None,
            "disclaimer": "上證指數資金流向，口徑依東財。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_flow")


def market_benchmark(symbol: str, range: str = "1y", benchmark: str = "000300") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bench = normalize_symbol(benchmark or "000300")
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        bench_bars, bench_src = _load_bars(bench, _RANGE_MAP.get(range, "1y"), "1d")
        a = {str(b["t"]): float(b["c"]) for b in bars if b.get("c") is not None}
        b = {str(row["t"]): float(row["c"]) for row in bench_bars if row.get("c") is not None}
        days = sorted(set(a) & set(b))
        if len(days) < 20:
            return _fail("與基準共同交易日不足", tool="market_benchmark")
        eq_a = [1.0]
        eq_b = [1.0]
        excess: list[float] = []
        rets_a: list[float] = []
        rets_b: list[float] = []
        prev_day: str | None = None
        for day in days:
            if prev_day is None:
                prev_day = day
                continue
            ra = a[day] / a[prev_day] - 1.0
            rb = b[day] / b[prev_day] - 1.0
            eq_a.append(eq_a[-1] * (1.0 + ra))
            eq_b.append(eq_b[-1] * (1.0 + rb))
            excess.append(ra - rb)
            rets_a.append(ra)
            rets_b.append(rb)
            prev_day = day
        n_obs = len(rets_a) or 1
        mean_e = sum(excess) / n_obs
        var_b = sum(item * item for item in rets_b) / n_obs
        mean_b = sum(rets_b) / n_obs
        mean_a = sum(rets_a) / n_obs
        cov = sum((ra - mean_a) * (rb - mean_b) for ra, rb in zip(rets_a, rets_b)) / n_obs
        beta = cov / var_b if var_b else None
        alpha = (mean_a - (beta or 0) * mean_b) * 252 if beta is not None else None
        te = math.sqrt(sum((item - mean_e) ** 2 for item in excess) / len(excess)) if excess else 0.0
        return {
            "ok": True,
            "symbol": code,
            "benchmark": bench,
            "sources": [source, bench_src],
            "bars": len(days),
            "total_return": round(eq_a[-1] - 1.0, 6),
            "benchmark_return": round(eq_b[-1] - 1.0, 6),
            "excess_return": round(eq_a[-1] / eq_b[-1] - 1.0, 6) if eq_b[-1] else None,
            "alpha": round(alpha, 6) if alpha is not None else None,
            "beta": round(beta, 4) if beta is not None else None,
            "tracking_error": round(te * math.sqrt(252), 6),
            "disclaimer": "基準對比不含股息再投資差異，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_benchmark", query=symbol)


def market_returns(symbols: str, range: str = "1y") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()]
        if len(parts) < 2:
            return _fail("請提供至少兩個標的", tool="market_returns")
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for raw in parts[:8]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                closes = [float(b["c"]) for b in bars if b.get("c") is not None]
                if len(closes) < 5:
                    errors.append(f"{code}: K 線不足")
                    continue
                ret = closes[-1] / closes[0] - 1.0
                rows.append(
                    {
                        "symbol": code,
                        "source": source,
                        "start": closes[0],
                        "end": closes[-1],
                        "total_return": round(ret, 6),
                        "bars": len(closes),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{raw}: {exc}")
        rows.sort(key=lambda item: -(item.get("total_return") or 0))
        return {
            "ok": True,
            "ranking": rows,
            "best": rows[0] if rows else None,
            "errors": errors,
            "disclaimer": "區間收益不含股息，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_returns", query=symbols)


def _score_stats(stats: dict[str, Any]) -> float:
    sharpe = stats.get("sharpe")
    if sharpe is None:
        return -999.0
    return float(sharpe)


def market_optimize(symbol: str, strategy: str = "dual_ma", range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        name = resolve_strategy(strategy or "dual_ma")
        if not name:
            return _fail(f"不支援策略 {strategy}。先呼叫 market_strategy_catalog。", tool="market_optimize")
        grid = _OPTIMIZE_GRIDS.get(name)
        if not grid:
            allowed = " / ".join(_OPTIMIZE_GRIDS)
            return _fail(f"策略 {strategy} 無網格，可用 {allowed}", tool="market_optimize")
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法優化", tool="market_optimize", symbol=code)
        trials: list[dict[str, Any]] = []
        for params in grid:
            stats = _dispatch_strategy(
                name,
                closes,
                dates,
                int(params.get("short") or 5),
                int(params.get("long") or 20),
                period=int(params.get("period") or 0),
                highs=highs,
                lows=lows,
                vols=vols,
            )
            trials.append(
                {
                    "params": params,
                    "sharpe": stats.get("sharpe"),
                    "total_return": stats.get("total_return"),
                    "max_drawdown": stats.get("max_drawdown"),
                    "trades": stats.get("trades"),
                }
            )
        trials.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999)))
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": name,
            "method": "grid",
            "trials": trials[:12],
            "best": trials[0] if trials else None,
            "disclaimer": "網格搜尋不含前視偏差校正，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_optimize", query=symbol)


def market_walkforward(symbol: str, strategy: str = "dual_ma", range: str = "2y", windows: int = 4) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        name = resolve_strategy(strategy or "dual_ma")
        if not name:
            return _fail(f"不支援策略 {strategy}", tool="market_walkforward")
        folds = max(2, min(int(windows or 4), 6))
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "2y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 80:
            return _fail("K 線不足 80 根，無法 Walk-Forward", tool="market_walkforward", count=len(closes))
        step = max(20, len(closes) // (folds + 1))
        rows: list[dict[str, Any]] = []
        for i, _fold in enumerate([None] * folds):
            train_end = min(len(closes) - 15, step * (i + 2))
            test_end = min(len(closes), train_end + step)
            if test_end - train_end < 10:
                continue
            train_c, test_c = closes[:train_end], closes[train_end:test_end]
            train_d, test_d = dates[:train_end], dates[train_end:test_end]
            train_h, test_h = highs[:train_end], highs[train_end:test_end]
            train_l, test_l = lows[:train_end], lows[train_end:test_end]
            train_v, test_v = vols[:train_end], vols[train_end:test_end]
            grid = _OPTIMIZE_GRIDS.get(name) or [{"short": 5, "long": 20}]
            best_params = grid[0]
            best_score = -999.0
            for params in grid:
                stats = _dispatch_strategy(
                    name,
                    train_c,
                    train_d,
                    int(params.get("short") or 5),
                    int(params.get("long") or 20),
                    period=int(params.get("period") or 0),
                    highs=train_h,
                    lows=train_l,
                    vols=train_v,
                )
                score = _score_stats(stats)
                if score > best_score:
                    best_score = score
                    best_params = params
            oos = _dispatch_strategy(
                name,
                test_c,
                test_d,
                int(best_params.get("short") or 5),
                int(best_params.get("long") or 20),
                period=int(best_params.get("period") or 0),
                highs=test_h,
                lows=test_l,
                vols=test_v,
            )
            rows.append(
                {
                    "fold": i + 1,
                    "train_end": train_d[-1] if train_d else None,
                    "test_end": test_d[-1] if test_d else None,
                    "params": best_params,
                    "in_sample_sharpe": round(best_score, 4) if best_score > -900 else None,
                    "oos_sharpe": oos.get("sharpe"),
                    "oos_return": oos.get("total_return"),
                    "oos_drawdown": oos.get("max_drawdown"),
                }
            )
        oos_sharpes = [row["oos_sharpe"] for row in rows if row.get("oos_sharpe") is not None]
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": name,
            "windows": rows,
            "mean_oos_sharpe": round(sum(oos_sharpes) / len(oos_sharpes), 4) if oos_sharpes else None,
            "disclaimer": "Walk-Forward 樣本外績效仍可能過擬合，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_walkforward", query=symbol)


def market_heatmap(symbol: str, range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法繪熱力圖", tool="market_heatmap")
        shorts = [3, 5, 8, 10]
        longs = [15, 20, 30, 40]
        cells: list[dict[str, Any]] = []
        for short in shorts:
            for long in longs:
                if short >= long:
                    continue
                stats = _dispatch_strategy(
                    "dual_ma", closes, dates, short, long, highs=highs, lows=lows, vols=vols
                )
                cells.append(
                    {
                        "short": short,
                        "long": long,
                        "sharpe": stats.get("sharpe"),
                        "total_return": stats.get("total_return"),
                    }
                )
        cells.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999)))
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": "dual_ma",
            "cells": cells,
            "best": cells[0] if cells else None,
            "disclaimer": "參數敏感度熱力圖，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_heatmap", query=symbol)


def market_signals(symbol: str, range: str = "6mo") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "6mo"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 30:
            return _fail("K 線不足，無法產生訊號", tool="market_signals")
        items: list[dict[str, Any]] = []
        long_votes = 0
        for name, label in STRATEGY_NAMES.items():
            stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
            signal = stats.get("last_signal")
            if signal == "long":
                long_votes += 1
            items.append({"strategy": name, "name": label, "signal": signal, "sharpe": stats.get("sharpe")})
        consensus = "long" if long_votes >= max(3, len(STRATEGY_NAMES) // 3) else "cash"
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "as_of": dates[-1] if dates else None,
            "close": closes[-1],
            "consensus": consensus,
            "long_votes": long_votes,
            "strategies": items,
            "disclaimer": "訊號僅反映技術條件，非進出場指令。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_signals", query=symbol)


def market_leaderboard(symbols: str = "600519,000001,AAPL", range: str = "1y") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()] or [
            "600519",
            "000001",
        ]
        scores: dict[str, list[float]] = {name: [] for name in STRATEGY_NAMES}
        used: list[str] = []
        errors: list[str] = []
        for raw in parts[:6]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                closes, dates, highs, lows, vols = _bars_series(bars)
                if len(closes) < 40:
                    errors.append(f"{code}: K 線不足")
                    continue
                used.append(code)
                for name in STRATEGY_NAMES:
                    stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
                    if stats.get("sharpe") is not None:
                        scores[name].append(float(stats["sharpe"]))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{raw}: {exc}")
        ranking = []
        for name, values in scores.items():
            if not values:
                continue
            ranking.append(
                {
                    "strategy": name,
                    "name": STRATEGY_NAMES[name],
                    "mean_sharpe": round(sum(values) / len(values), 4),
                    "samples": len(values),
                }
            )
        ranking.sort(key=lambda row: -row["mean_sharpe"])
        return {
            "ok": True,
            "symbols": used,
            "ranking": ranking,
            "best": ranking[0] if ranking else None,
            "errors": errors,
            "disclaimer": "跨標的平均夏普，樣本外未必持續，禁止當作收益保證。",
        }
    except Exception as exc:  # noqa: BLE001
        return _fail(exc, tool="market_leaderboard", query=symbols)


def register_company_tools(registry: Any) -> None:
    """向公司 tool_registry 註冊量化工具，供金融／研究角色引用。"""
    roles = list(QUANT_ROLES)
    specs: list[dict[str, Any]] = [
        {
            "name": "market_quote",
            "description": "查詢股票／指數最新行情（Yahoo 主源，A 股可備援東方財富，美股可備援 Stooq）。",
            "parameters": {"symbol": {"type": "string", "description": "標的代碼或中文簡稱，如 600519、茅台、AAPL"}},
            "execute": lambda symbol: dumps_result(market_quote(symbol)),
            "timeout_seconds": 25.0,
        },
        {
            "name": "market_kline",
            "description": "取得歷史 K 線（開高低收量）。range：1mo/3mo/6mo/1y/2y；interval 預設 1d。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "range": {"type": "string", "description": "區間，預設 1y"},
                "interval": {"type": "string", "description": "週期，預設 1d"},
            },
            "execute": lambda symbol, range="1y", interval="1d": dumps_result(
                market_kline(symbol, range=range, interval=interval)
            ),
            "timeout_seconds": 25.0,
        },
        {
            "name": "market_backtest",
            "description": "單策略回測（31 種引擎，含 enhanced_volume／single_volume；可用策略庫別名）。可設滑點、T+1、漲跌停、移動止損。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "strategy": {"type": "string", "description": "策略 id，預設 dual_ma"},
                "range": {"type": "string", "description": "K 線區間，預設 1y"},
                "short": {"type": "integer", "description": "短均線（dual_ma／ema_cross，預設 5）"},
                "long": {"type": "integer", "description": "長均線（預設 20）"},
                "period": {"type": "integer", "description": "指標窗口（rsi/donchian 等）"},
                "slippage_pct": {"type": "number", "description": "滑點百分比，預設 0"},
                "stop_loss_pct": {"type": "number", "description": "止損百分比，0 為關閉"},
                "take_profit_pct": {"type": "number", "description": "止盈百分比，0 為關閉"},
                "trailing_stop_pct": {"type": "number", "description": "移動止損百分比，0 為關閉"},
                "enable_t1": {"type": "boolean", "description": "A 股 T+1，買入次日才能賣"},
                "enable_limit": {"type": "boolean", "description": "漲跌停時跳過對應買賣"},
            },
            "execute": lambda symbol, strategy="dual_ma", range="1y", short=5, long=20, period=0, slippage_pct=0, stop_loss_pct=0, take_profit_pct=0, trailing_stop_pct=0, enable_t1=False, enable_limit=False: dumps_result(
                market_backtest(
                    symbol,
                    strategy=strategy,
                    range=range,
                    short=short,
                    long=long,
                    period=period,
                    slippage_pct=slippage_pct,
                    stop_loss_pct=stop_loss_pct,
                    take_profit_pct=take_profit_pct,
                    trailing_stop_pct=trailing_stop_pct,
                    enable_t1=enable_t1,
                    enable_limit=enable_limit,
                )
            ),
            "timeout_seconds": 30.0,
        },
        {
            "name": "market_compare",
            "description": "對同一標的跑全部內建策略並依夏普排序，對齊 stock-quant 多策略對比。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "range": {"type": "string", "description": "區間，預設 1y"},
            },
            "execute": lambda symbol, range="1y": dumps_result(market_compare(symbol, range=range)),
            "timeout_seconds": 45.0,
        },
        {
            "name": "market_optimize",
            "description": "網格搜尋策略參數（dual_ma／rsi／bollinger／momentum／breakout 等），依夏普選最佳。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "strategy": {"type": "string", "description": "策略 id，預設 dual_ma"},
                "range": {"type": "string", "description": "區間，預設 1y"},
            },
            "execute": lambda symbol, strategy="dual_ma", range="1y": dumps_result(
                market_optimize(symbol, strategy=strategy, range=range)
            ),
            "timeout_seconds": 40.0,
        },
        {
            "name": "market_walkforward",
            "description": "Walk-Forward：樣本內優化、樣本外驗證。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "strategy": {"type": "string", "description": "策略 id，預設 dual_ma"},
                "range": {"type": "string", "description": "區間，預設 2y"},
                "windows": {"type": "integer", "description": "折數，預設 4"},
            },
            "execute": lambda symbol, strategy="dual_ma", range="2y", windows=4: dumps_result(
                market_walkforward(symbol, strategy=strategy, range=range, windows=windows)
            ),
            "timeout_seconds": 45.0,
        },
        {
            "name": "market_heatmap",
            "description": "dual_ma 短/長均線夏普熱力圖。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "range": {"type": "string", "description": "區間，預設 1y"},
            },
            "execute": lambda symbol, range="1y": dumps_result(market_heatmap(symbol, range=range)),
            "timeout_seconds": 35.0,
        },
        {
            "name": "market_signals",
            "description": "全部策略最新多空訊號與投票共識。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "range": {"type": "string", "description": "區間，預設 6mo"},
            },
            "execute": lambda symbol, range="6mo": dumps_result(market_signals(symbol, range=range)),
            "timeout_seconds": 40.0,
        },
        {
            "name": "market_leaderboard",
            "description": "多標的策略排行（平均夏普）。symbols 逗號分隔。",
            "parameters": {
                "symbols": {"type": "string", "description": "如 600519,000001,AAPL"},
                "range": {"type": "string", "description": "區間，預設 1y"},
            },
            "execute": lambda symbols="600519,000001,AAPL", range="1y": dumps_result(
                market_leaderboard(symbols, range=range)
            ),
            "timeout_seconds": 50.0,
        },
        {
            "name": "market_watch",
            "description": "盯盤預警：單日漲跌、MA20、雙均線訊號。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "drop_pct": {"type": "number", "description": "漲跌預警門檻百分比，預設 3"},
            },
            "execute": lambda symbol, drop_pct=3.0: dumps_result(market_watch(symbol, drop_pct=drop_pct)),
            "timeout_seconds": 25.0,
        },
        {
            "name": "market_search",
            "description": "依關鍵字或代碼搜尋標的（本地別名 + Yahoo Search）。",
            "parameters": {"keyword": {"type": "string", "description": "代碼或名稱，如 茅台、AAPL"}},
            "execute": lambda keyword: dumps_result(market_search(keyword)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_screener",
            "description": "A 股條件快照（漲跌幅／PE／市值排序），對齊 stock-quant screener。",
            "parameters": {
                "sort": {"type": "string", "description": "pct、pe 或 mv，預設 pct"},
                "limit": {"type": "integer", "description": "條數，預設 15"},
            },
            "execute": lambda sort="pct", limit=15: dumps_result(market_screener(sort=sort, limit=limit)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_fundamentals",
            "description": "A 股基本面快照（PE／PB／ROE／市值），東方財富。",
            "parameters": {"symbol": {"type": "string", "description": "A 股代碼或簡稱"}},
            "execute": lambda symbol: dumps_result(market_fundamentals(symbol)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_capital_flow",
            "description": "個股資金流向（主力／大單淨額）。",
            "parameters": {
                "symbol": {"type": "string", "description": "A 股代碼"},
                "days": {"type": "integer", "description": "天數，預設 15"},
            },
            "execute": lambda symbol, days=15: dumps_result(market_capital_flow(symbol, days=days)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_north_flow",
            "description": "北向資金（滬深港通）近日淨流入。",
            "parameters": {"days": {"type": "integer", "description": "天數，預設 15"}},
            "execute": lambda days=15: dumps_result(market_north_flow(days=days)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_dragon_tiger",
            "description": "龍虎榜近日明細。",
            "parameters": {"limit": {"type": "integer", "description": "條數，預設 15"}},
            "execute": lambda limit=15: dumps_result(market_dragon_tiger(limit=limit)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_sectors",
            "description": "行業或概念板塊漲跌排名。",
            "parameters": {
                "kind": {"type": "string", "description": "industry 或 concept"},
                "limit": {"type": "integer", "description": "條數，預設 15"},
            },
            "execute": lambda kind="industry", limit=15: dumps_result(market_sectors(kind=kind, limit=limit)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_portfolio",
            "description": "多標的組合。method：equal_weight／risk_parity／vol_target／kelly／mvo／max_div／anti_corr／regime／frontier／dynamic／degradation。",
            "parameters": {
                "symbols": {"type": "string", "description": "如 600519,000001 或 AAPL,MSFT"},
                "range": {"type": "string", "description": "區間，預設 1y"},
                "method": {"type": "string", "description": "組合方法，預設 equal_weight"},
            },
            "execute": lambda symbols, range="1y", method="equal_weight": dumps_result(
                market_portfolio(symbols, range=range, method=method)
            ),
            "timeout_seconds": 40.0,
        },
        {
            "name": "market_minutes",
            "description": "A 股分鐘 K 線（1m/5m/15m/30m/60m），東方財富。",
            "parameters": {
                "symbol": {"type": "string", "description": "A 股代碼"},
                "interval": {"type": "string", "description": "預設 5m"},
                "limit": {"type": "integer", "description": "根數，預設 80"},
            },
            "execute": lambda symbol, interval="5m", limit=80: dumps_result(
                market_minutes(symbol, interval=interval, limit=limit)
            ),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_realtime",
            "description": "即時盤口：A 股優先新浪，其餘走 market_quote 備援鏈。",
            "parameters": {"symbol": {"type": "string", "description": "標的代碼或簡稱"}},
            "execute": lambda symbol: dumps_result(market_realtime(symbol)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_flow",
            "description": "大盤（上證）資金流向，對齊 stock-quant 市場資金。",
            "parameters": {"days": {"type": "integer", "description": "天數，預設 15"}},
            "execute": lambda days=15: dumps_result(market_flow(days=days)),
            "timeout_seconds": 20.0,
        },
        {
            "name": "market_benchmark",
            "description": "相對滬深300（或指定基準）的超額收益、Alpha／Beta。",
            "parameters": {
                "symbol": {"type": "string", "description": "標的代碼"},
                "range": {"type": "string", "description": "區間，預設 1y"},
                "benchmark": {"type": "string", "description": "基準，預設 000300"},
            },
            "execute": lambda symbol, range="1y", benchmark="000300": dumps_result(
                market_benchmark(symbol, range=range, benchmark=benchmark)
            ),
            "timeout_seconds": 35.0,
        },
        {
            "name": "market_returns",
            "description": "多標的區間收益對比（逗號分隔）。",
            "parameters": {
                "symbols": {"type": "string", "description": "如 600519,000001,AAPL"},
                "range": {"type": "string", "description": "區間，預設 1y"},
            },
            "execute": lambda symbols, range="1y": dumps_result(market_returns(symbols, range=range)),
            "timeout_seconds": 40.0,
        },
        {
            "name": "fx_rate",
            "description": "查詢外匯匯率（Frankfurter 主源，currency-api 備援）。",
            "parameters": {
                "base": {"type": "string", "description": "基準幣，預設 USD"},
                "quote": {"type": "string", "description": "報價幣，預設 CNY"},
                "date": {"type": "string", "description": "可選 YYYY-MM-DD；空白為最新"},
            },
            "execute": lambda base="USD", quote="CNY", date="": dumps_result(fx_rate(base, quote, date)),
            "timeout_seconds": 15.0,
        },
        {
            "name": "crypto_quote",
            "description": "查詢加密貨幣美元報價（CoinPaprika → CoinGecko → Binance）。",
            "parameters": {"symbol": {"type": "string", "description": "BTC、ETH 或 coinpaprika id"}},
            "execute": lambda symbol="BTC": dumps_result(crypto_quote(symbol)),
            "timeout_seconds": 15.0,
        },
        {
            "name": "market_sources",
            "description": "列出已接通與僅目錄的免費數據源、可回測策略與工具，供角色選擇呼叫。",
            "parameters": {},
            "execute": lambda: dumps_result(market_sources()),
            "timeout_seconds": 5.0,
        },
        {
            "name": "market_strategy_catalog",
            "description": "stock-quant 策略庫目錄（分類／搜尋）。未篩選回引擎清單；listing=true 或 category／query 列出目錄。wired 可回測，catalog 為規劃項。",
            "parameters": {
                "category": {"type": "string", "description": "ma／momentum／mean_reversion／volatility／trend／pattern／breakout／composite／ml，空白為摘要"},
                "query": {"type": "string", "description": "關鍵字，如 海龜、rsi、突破"},
                "status": {"type": "string", "description": "wired 或 catalog，空白為全部"},
                "listing": {"type": "boolean", "description": "true 時回完整分類樹（groups），給瀏覽用"},
            },
            "execute": lambda category="", query="", status="", listing=False: dumps_result(
                market_strategy_catalog(
                    category=category, query=query, status=status, listing=listing
                )
            ),
            "timeout_seconds": 5.0,
        },
    ]
    for spec in specs:
        registry.register(
            name=spec["name"],
            description=spec["description"],
            parameters=spec["parameters"],
            execute=spec["execute"],
            allowed_roles=roles,
            readonly=False,
            timeout_seconds=float(spec["timeout_seconds"]),
        )
