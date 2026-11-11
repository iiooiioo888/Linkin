"""量化工具常數：角色清單、標的別名、資料源參數與策略名稱對照。

自 backend.company.quant_tools 抽出的模組層常數；子模組與外部皆由套件
__init__ re-export，名稱與內容不變。
"""

from __future__ import annotations

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
