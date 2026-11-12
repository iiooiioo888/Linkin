"""行情對外介面：來源總覽、報價、K 線、分鐘線與即時行情。"""

from __future__ import annotations

from typing import Any

from ..constants import _KLT_MAP, _MAX_BARS, _RANGE_MAP, QUANT_TOOL_NAMES, STRATEGY_NAMES
from .bars import _eastmoney_bars, _load_bars
from .symbols import _a_share_code, normalize_symbol
from .util import _fail


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
