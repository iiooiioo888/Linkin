"""公司工具註冊：register_company_tools 與量化工具規格表。"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_catalog import market_strategy_catalog

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
from .constants import QUANT_ROLES
from .data import (
    crypto_quote,
    dumps_result,
    fx_rate,
    market_kline,
    market_minutes,
    market_quote,
    market_realtime,
    market_sources,
)
from .portfolio import market_portfolio


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
