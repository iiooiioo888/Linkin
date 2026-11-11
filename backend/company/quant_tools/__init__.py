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

自單檔模組拆為套件，對外 import 路徑不變；子模組分工：
- constants：角色／策略／資料源常數
- data：HTTP helper、標的別名、Yahoo／東方財富／Stooq／外匯／加密行情
- indicators：技術指標與績效統計
- strategies：部位序列引擎、核心策略 runner、績效打包
- strategies_advanced：進階策略 runner（SAR／ATR／MACD 系列等）
- backtest：策略派發、回測、網格優化、Walk-Forward、熱力圖、訊號、排行
- analysis：多標的對比、搜尋、基本面、資金流、板塊、盯盤、基準比較
- portfolio：多標的組合權重
- tools：register_company_tools 工具註冊
"""

from __future__ import annotations

from backend.company.quant_strategy_catalog import market_strategy_catalog, resolve_strategy

from .analysis import (
    market_benchmark,
    market_capital_flow,
    market_compare,
    market_dragon_tiger,
    market_flow,
    market_fundamentals,
    market_north_flow,
    market_returns,
    market_screener,
    market_search,
    market_sectors,
    market_watch,
)
from .backtest import (
    market_backtest,
    market_heatmap,
    market_leaderboard,
    market_optimize,
    market_signals,
    market_walkforward,
)
from .constants import (
    COINGECKO_IDS,
    CRYPTO_IDS,
    QUANT_ROLES,
    QUANT_TOOL_NAMES,
    STRATEGY_NAMES,
    SYMBOL_ALIASES,
)
from .data import (
    crypto_quote,
    dumps_result,
    fx_rate,
    market_kline,
    market_minutes,
    market_quote,
    market_realtime,
    market_sources,
    normalize_symbol,
)
from .portfolio import market_portfolio
from .tools import register_company_tools

__all__ = [
    "COINGECKO_IDS",
    "CRYPTO_IDS",
    "QUANT_ROLES",
    "QUANT_TOOL_NAMES",
    "STRATEGY_NAMES",
    "SYMBOL_ALIASES",
    "crypto_quote",
    "dumps_result",
    "fx_rate",
    "market_backtest",
    "market_benchmark",
    "market_capital_flow",
    "market_compare",
    "market_dragon_tiger",
    "market_flow",
    "market_fundamentals",
    "market_heatmap",
    "market_kline",
    "market_leaderboard",
    "market_minutes",
    "market_north_flow",
    "market_optimize",
    "market_portfolio",
    "market_quote",
    "market_realtime",
    "market_returns",
    "market_screener",
    "market_search",
    "market_sectors",
    "market_signals",
    "market_sources",
    "market_strategy_catalog",
    "market_walkforward",
    "market_watch",
    "normalize_symbol",
    "register_company_tools",
    "resolve_strategy",
]
