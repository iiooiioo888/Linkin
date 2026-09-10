"""量化公司工具測試（不連外網）。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend.company.quant_tools import (
    QUANT_ROLES,
    QUANT_TOOL_NAMES,
    STRATEGY_NAMES,
    crypto_quote,
    fx_rate,
    market_backtest,
    market_benchmark,
    market_capital_flow,
    market_compare,
    market_dragon_tiger,
    market_flow,
    market_fundamentals,
    market_heatmap,
    market_kline,
    market_leaderboard,
    market_minutes,
    market_north_flow,
    market_optimize,
    market_portfolio,
    market_quote,
    market_realtime,
    market_returns,
    market_screener,
    market_search,
    market_sectors,
    market_signals,
    market_sources,
    market_strategy_catalog,
    market_walkforward,
    market_watch,
    normalize_symbol,
)
from backend.company.tools import ToolCallRequest, tool_registry


def _yahoo_payload(closes: list[float], start: datetime | None = None, volumes: list[float] | None = None) -> dict:
    origin = start or datetime(2024, 1, 2, tzinfo=timezone.utc)
    timestamps = [int((origin + timedelta(days=i)).timestamp()) for i in range(len(closes))]
    vols = volumes if volumes is not None else [1_000_000] * len(closes)
    return {
        "chart": {
            "result": [
                {
                    "meta": {"symbol": "600519.SS", "currency": "CNY"},
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [c * 0.99 for c in closes],
                                "high": [c * 1.01 for c in closes],
                                "low": [c * 0.98 for c in closes],
                                "close": closes,
                                "volume": vols,
                            }
                        ]
                    },
                }
            ],
            "error": None,
        }
    }


def _up_then_down(n: int = 80) -> list[float]:
    """先漲後跌，讓 dual_ma 能產生買賣。"""
    values = []
    price = 100.0
    for i in range(n):
        price *= 1.012 if i < n // 2 else 0.988
        values.append(round(price, 4))
    return values


def test_normalize_symbol_aliases_and_a_share():
    assert normalize_symbol("茅台") == "600519.SS"
    assert normalize_symbol("600519") == "600519.SS"
    assert normalize_symbol("000001") == "000001.SZ"
    assert normalize_symbol("000300") == "000300.SS"
    assert normalize_symbol("AAPL") == "AAPL"


def test_market_quote_and_kline_from_yahoo(monkeypatch):
    closes = _up_then_down()
    payload = _yahoo_payload(closes)

    def fake_get(url, params=None):
        assert "finance.yahoo.com" in url
        return payload

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    quote = market_quote("茅台")
    assert quote["ok"] is True
    assert quote["symbol"] == "600519.SS"
    assert quote["source"] == "yahoo"
    assert quote["close"] == closes[-1]

    kline = market_kline("600519", range="1y")
    assert kline["ok"] is True
    assert kline["count"] == len(closes)
    assert kline["bars"][-1]["c"] == closes[-1]


def test_market_backtest_dual_ma_and_macd(monkeypatch):
    closes = _up_then_down(90)
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    dual = market_backtest("600519", strategy="dual_ma", short=5, long=20)
    assert dual["ok"] is True
    assert dual["strategy"] == "dual_ma"
    assert dual["trades"] >= 1
    assert dual["last_signal"] in {"long", "cash", "flat"}
    assert "disclaimer" in dual

    macd = market_backtest("AAPL", strategy="macd")
    assert macd["ok"] is True
    assert macd["strategy"] == "macd"
    assert "max_drawdown" in macd

    rsi = market_backtest("600519", strategy="rsi")
    assert rsi["ok"] is True
    assert rsi["strategy"] == "rsi"
    assert "chart" not in rsi

    drawn = market_backtest("600519", strategy="dual_ma", include_chart=True)
    assert drawn["ok"] is True
    assert drawn["chart"]["equity"]
    assert drawn["chart"]["hold"]
    assert drawn["chart"]["close"]
    assert len(drawn["chart"]["equity"]) >= 2


def test_market_compare_ranks_all_strategies(monkeypatch):
    closes = _up_then_down(90)
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    result = market_compare("600519")
    assert result["ok"] is True
    names = {row["strategy"] for row in result["ranking"]}
    assert {
        "dual_ma",
        "macd",
        "rsi",
        "bollinger",
        "momentum",
        "mean_reversion",
        "breakout",
        "kdj",
        "ema_cross",
        "turtle",
        "supertrend",
        "composite",
    } <= names
    assert result["best"]["strategy"] in names


def test_market_watch_alerts(monkeypatch):
    closes = [100.0] * 30 + [90.0]
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    watch = market_watch("000001", drop_pct=3)
    assert watch["ok"] is True
    assert any("下跌" in item for item in watch["alerts"])


def test_yahoo_fail_falls_back_to_eastmoney(monkeypatch):
    def fake_get(url, params=None):
        if "yahoo" in url:
            raise RuntimeError("yahoo down")
        assert "eastmoney" in url
        rows = []
        price = 10.0
        for i in range(40):
            price += 0.1
            rows.append(f"2024-01-{i+1:02d},{price:.2f},{price+0.2:.2f},{price+0.3:.2f},{price-0.1:.2f},1000")
        return {"data": {"klines": rows}}

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    quote = market_quote("600519")
    assert quote["ok"] is True
    assert quote["source"] == "eastmoney"


def test_fx_and_crypto(monkeypatch):
    def fake_get(url, params=None):
        if "frankfurter" in url:
            return {"amount": 1.0, "base": "USD", "date": "2024-06-01", "rates": {"CNY": 7.2}}
        if url.endswith("/tickers/btc-bitcoin"):
            return {
                "id": "btc-bitcoin",
                "symbol": "BTC",
                "name": "Bitcoin",
                "last_updated": "2024-06-01T00:00:00Z",
                "quotes": {"USD": {"price": 65000, "percent_change_24h": 1.2, "volume_24h": 1, "market_cap": 1}},
            }
        raise AssertionError(url)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    fx = fx_rate("USD", "CNY")
    assert fx["ok"] is True
    assert fx["rate"] == 7.2
    assert fx["source"] == "frankfurter"

    crypto = crypto_quote("BTC")
    assert crypto["ok"] is True
    assert crypto["price_usd"] == 65000


def test_network_error_is_structured(monkeypatch):
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_text",
        lambda url, params=None: (_ for _ in ()).throw(RuntimeError("timeout")),
    )
    quote = market_quote("AAPL")
    assert quote["ok"] is False
    assert "timeout" in quote["error"]


def test_market_sources_lists_free_feeds():
    info = market_sources()
    assert info["ok"] is True
    ids = {item["id"] for item in info["sources"]}
    assert {"yahoo", "frankfurter", "coinpaprika", "eastmoney", "stooq", "coingecko", "binance", "currency_api", "sina"} <= ids
    assert "market_backtest" in info["tools"]
    assert "market_optimize" in info["tools"]
    assert "market_walkforward" in info["tools"]
    assert "market_signals" in info["tools"]
    assert "market_minutes" in info["tools"]
    assert "market_benchmark" in info["tools"]
    assert "market_strategy_catalog" in info["tools"]
    assert {row["id"] for row in info["strategies"]} >= {
        "dual_ma",
        "rsi",
        "breakout",
        "turtle",
        "composite",
        "parabolic_sar",
        "atr_trail",
        "macd_rsi",
        "pullback_ma",
        "ema_volume",
    }
    assert "kelly" in info["portfolio_methods"]
    sina = next(item for item in info["sources"] if item["id"] == "sina")
    assert sina["wired"] is True


def test_company_registry_has_quant_tools_and_role_filter():
    names = {t.name for t in tool_registry.list_tools()}
    for expected in QUANT_TOOL_NAMES:
        assert expected in names

    quote = tool_registry.get("market_quote")
    assert quote is not None
    assert tool_registry._role_permitted(quote, "quant_analyst") is True
    assert tool_registry._role_permitted(quote, "finance_lead") is True
    assert tool_registry._role_permitted(quote, "developer") is False
    for role in QUANT_ROLES:
        assert tool_registry._role_permitted(quote, role) is True

    denied = tool_registry.execute(
        ToolCallRequest(tool="market_quote", args={"symbol": "AAPL"}),
        role="developer",
    )
    assert denied.success is False


def test_registry_execute_quote_json(monkeypatch):
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload([10, 11, 12, 13, 14]),
    )
    result = tool_registry.execute(
        ToolCallRequest(tool="market_quote", args={"symbol": "茅台"}),
        role="quant_analyst",
    )
    assert result.success is True
    payload = json.loads(str(result.result))
    assert payload["ok"] is True
    assert payload["symbol"] == "600519.SS"


def _route_json(url, params=None):
    if "ulist" in url:
        return {
            "data": {
                "diff": [
                    {
                        "f12": "600519",
                        "f14": "贵州茅台",
                        "f2": 1400.0,
                        "f3": 1.2,
                        "f9": 28.5,
                        "f23": 8.1,
                        "f20": 1.7e12,
                        "f21": 1.7e12,
                        "f37": 32.1,
                    }
                ]
            }
        }
    if "clist/get" in url:
        return {
            "data": {
                "diff": [
                    {"f12": "600519", "f14": "贵州茅台", "f2": 1400, "f3": 2.1, "f9": 28, "f20": 1, "f23": 8, "f62": 100}
                ]
            }
        }
    if "fflow/kline" in url:
        return {"data": {"klines": ["2024-06-01,1000000,-200000,300000,400000,500000"]}}
    if "datacenter-web.eastmoney.com" in url:
        report = (params or {}).get("reportName", "")
        if "MUTUAL" in report:
            return {"result": {"data": [{"TRADE_DATE": "2024-06-01", "NORTH_NET_INFLOW": 80.5, "BUY_AMT": 100, "SELL_AMT": 19.5}]}}
        return {
            "result": {
                "data": [
                    {
                        "SECURITY_CODE": "600519",
                        "SECURITY_NAME_ABBR": "贵州茅台",
                        "TRADE_DATE": "2024-06-01",
                        "CHANGE_RATE": 2.1,
                        "BILLBOARD_NET_AMT": 1.2e8,
                    }
                ]
            }
        }
    if "finance/search" in url:
        return {"quotes": [{"symbol": "600519.SS", "shortname": "Kweichow Moutai", "quoteType": "EQUITY"}]}
    if "coingecko" in url:
        return {"bitcoin": {"usd": 64000, "usd_24h_change": 1.1, "usd_24h_vol": 1, "usd_market_cap": 1}}
    raise AssertionError(url)


def test_eastmoney_research_tools(monkeypatch):
    monkeypatch.setattr("backend.company.quant_tools._http_get_json", _route_json)
    fund = market_fundamentals("茅台")
    assert fund["ok"] is True
    assert fund["pe"] == 28.5
    assert fund["name"] == "贵州茅台"

    screen = market_screener(sort="pct", limit=10)
    assert screen["ok"] is True
    assert screen["items"][0]["code"] == "600519"

    flow = market_capital_flow("600519")
    assert flow["ok"] is True
    assert flow["latest"]["main_net"] == 1000000

    north = market_north_flow(10)
    assert north["ok"] is True
    assert north["latest"]["north_net"] == 80.5

    board = market_dragon_tiger(10)
    assert board["ok"] is True
    assert board["items"][0]["code"] == "600519"

    sectors = market_sectors("industry")
    assert sectors["ok"] is True
    assert sectors["items"][0]["name"] == "贵州茅台"


def test_market_search_and_portfolio(monkeypatch):
    closes = _up_then_down(40)
    payload = _yahoo_payload(closes)

    def fake_get(url, params=None):
        if "finance/search" in url:
            return {"quotes": [{"symbol": "AAPL", "shortname": "Apple", "quoteType": "EQUITY"}]}
        if "yahoo.com" in url and "chart" in url:
            return payload
        return _route_json(url, params)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    search = market_search("茅台")
    assert search["ok"] is True
    symbols = {item["symbol"] for item in search["hits"]}
    assert "600519.SS" in symbols

    port = market_portfolio("600519,000001")
    assert port["ok"] is True
    assert port["method"] == "equal_weight"
    assert len(port["symbols"]) == 2
    rp = market_portfolio("600519,000001", method="risk_parity")
    assert rp["ok"] is True
    assert rp["method"] == "risk_parity"
    assert abs(sum(rp["weights"].values()) - 1.0) < 0.02


def test_us_yahoo_fail_falls_back_to_stooq(monkeypatch):
    def fake_json(url, params=None):
        if "yahoo" in url:
            raise RuntimeError("yahoo down")
        raise AssertionError(url)

    csv = "Date,Open,High,Low,Close,Volume\n2024-01-01,10,11,9,10.5,100\n2024-01-02,10.5,12,10,11,100\n2024-01-03,11,12,10,10.8,100\n"

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_json)
    monkeypatch.setattr("backend.company.quant_tools._http_get_text", lambda url, params=None: csv)
    quote = market_quote("AAPL")
    assert quote["ok"] is True
    assert quote["source"] == "stooq"
    assert quote["close"] == 10.8


def test_crypto_coingecko_fallback(monkeypatch):
    def fake_get(url, params=None):
        if "coinpaprika" in url:
            raise RuntimeError("paprika down")
        if "coingecko" in url:
            return {"bitcoin": {"usd": 64000, "usd_24h_change": 1.1}}
        raise AssertionError(url)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    crypto = crypto_quote("BTC")
    assert crypto["ok"] is True
    assert crypto["source"] == "coingecko"
    assert crypto["price_usd"] == 64000


def test_extra_strategies_optimize_walkforward_and_signals(monkeypatch):
    closes = _up_then_down(90)
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    turtle = market_backtest("600519", strategy="turtle")
    assert turtle["ok"] is True
    assert turtle["strategy"] == "turtle"
    assert "sortino" in turtle

    ema = market_backtest("600519", strategy="ema_cross", slippage_pct=0.1, stop_loss_pct=8)
    assert ema["ok"] is True
    assert ema["params"]["slippage_pct"] == 0.1

    opt = market_optimize("600519", strategy="dual_ma")
    assert opt["ok"] is True
    assert opt["best"]["params"]["short"] < opt["best"]["params"]["long"]

    wf = market_walkforward("600519", strategy="dual_ma", windows=3)
    assert wf["ok"] is True
    assert len(wf["windows"]) >= 2

    heat = market_heatmap("600519")
    assert heat["ok"] is True
    assert heat["cells"]

    sig = market_signals("600519")
    assert sig["ok"] is True
    assert sig["consensus"] in {"long", "cash"}
    assert len(sig["strategies"]) == len(STRATEGY_NAMES)

    board = market_leaderboard("600519,000001")
    assert board["ok"] is True
    assert board["best"]["strategy"] in STRATEGY_NAMES


def test_fx_currency_api_fallback(monkeypatch):
    def fake_get(url, params=None):
        if "frankfurter" in url:
            raise RuntimeError("frankfurter down")
        if "currency-api" in url:
            return {"date": "2024-06-01", "usd": {"cny": 7.21}}
        raise AssertionError(url)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    fx = fx_rate("USD", "CNY")
    assert fx["ok"] is True
    assert fx["source"] == "currency_api"
    assert fx["rate"] == 7.21


def test_crypto_binance_fallback(monkeypatch):
    def fake_get(url, params=None):
        if "coinpaprika" in url or "coingecko" in url:
            raise RuntimeError("down")
        if "binance" in url:
            return {"lastPrice": "65000.1", "priceChangePercent": "1.2", "quoteVolume": "10"}
        raise AssertionError(url)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    crypto = crypto_quote("BTC")
    assert crypto["ok"] is True
    assert crypto["source"] == "binance"
    assert crypto["price_usd"] == 65000.1


def test_parabolic_sar_t1_and_extra_portfolio(monkeypatch):
    closes = _up_then_down(90)
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    sar = market_backtest("600519", strategy="parabolic_sar", enable_t1=True, trailing_stop_pct=8)
    assert sar["ok"] is True
    assert sar["strategy"] == "parabolic_sar"
    assert sar["params"]["enable_t1"] is True

    kelly = market_portfolio("600519,000001", method="kelly")
    assert kelly["ok"] is True
    assert kelly["method"] == "kelly"
    assert abs(sum(kelly["weights"].values()) - 1.0) < 0.02

    mvo = market_portfolio("600519,000001", method="mvo")
    assert mvo["ok"] is True
    assert mvo["method"] == "mvo"

    frontier = market_portfolio("600519,000001", method="frontier")
    assert frontier["ok"] is True
    assert frontier["frontier"]


def test_minutes_flow_benchmark_returns_and_sina(monkeypatch):
    closes = _up_then_down(40)
    payload = _yahoo_payload(closes)

    def fake_get(url, params=None):
        if "fflow/kline" in url:
            return {"data": {"klines": ["2024-06-01,1000000,-200000,300000,400000,500000"]}}
        if "kline/get" in url:
            rows = []
            price = 10.0
            for i in range(40):
                price += 0.1
                rows.append(f"2024-01-01 09:{i:02d},{price:.2f},{price+0.2:.2f},{price+0.3:.2f},{price-0.1:.2f},1000")
            return {"data": {"klines": rows}}
        if "yahoo.com" in url and "chart" in url:
            return payload
        raise AssertionError(url)

    monkeypatch.setattr("backend.company.quant_tools._http_get_json", fake_get)
    minutes = market_minutes("600519", interval="5m")
    assert minutes["ok"] is True
    assert minutes["source"] == "eastmoney"
    assert minutes["count"] == 40

    flow = market_flow(10)
    assert flow["ok"] is True
    assert flow["latest"]["main_net"] == 1000000

    bench = market_benchmark("600519")
    assert bench["ok"] is True
    assert bench["beta"] is not None

    rets = market_returns("600519,000001")
    assert rets["ok"] is True
    assert len(rets["ranking"]) == 2

    from backend.company.quant_feeds import sina_realtime

    monkeypatch.setattr(
        "backend.company.quant_feeds._get_bytes",
        lambda url, params=None: 'var hq_str_sh600519="贵州茅台,1390,1400,1410,1420,1380,1410,1411,1000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2024-06-01,15:00:00,00";'.encode("gbk"),
    )
    snap = sina_realtime("600519.SS")
    assert snap["ok"] is True
    assert snap["source"] == "sina"
    assert snap["close"] == 1410

    monkeypatch.setattr("backend.company.quant_feeds.sina_realtime", lambda symbol: snap)
    live = market_realtime("茅台")
    assert live["ok"] is True
    assert live["source"] == "sina"


def test_keyed_feeds_require_tokens(monkeypatch):
    from backend.company.quant_feeds import (
        alphavantage_quote,
        finnhub_quote,
        keyed_status,
        tushare_bars,
    )

    monkeypatch.setattr("backend.company.quant_feeds.env_tokens", lambda: {"tushare": "", "finnhub": "", "alphavantage": "", "itick": ""})
    status = keyed_status()
    assert status["tushare"] is False
    try:
        tushare_bars("600519.SS")
        raise AssertionError("expected missing token")
    except RuntimeError as exc:
        assert "TUSHARE" in str(exc)
    try:
        finnhub_quote("AAPL")
        raise AssertionError("expected missing token")
    except RuntimeError as exc:
        assert "FINNHUB" in str(exc)
    try:
        alphavantage_quote("AAPL")
        raise AssertionError("expected missing token")
    except RuntimeError as exc:
        assert "ALPHAVANTAGE" in str(exc)


def test_finnhub_quote_with_token(monkeypatch):
    from backend.company.quant_feeds import finnhub_quote

    monkeypatch.setattr(
        "backend.company.quant_feeds.env_tokens",
        lambda: {"tushare": "", "finnhub": "tok", "alphavantage": "", "itick": ""},
    )
    monkeypatch.setattr(
        "backend.company.quant_feeds._get_json",
        lambda url, params=None, referer="": {"c": 190.5, "d": 1.2, "dp": 0.6, "o": 189, "h": 191, "l": 188, "pc": 189.3},
    )
    quote = finnhub_quote("AAPL")
    assert quote["ok"] is True
    assert quote["source"] == "finnhub"
    assert quote["close"] == 190.5


def test_strategy_catalog_and_engine_aliases(monkeypatch):
    catalog = market_strategy_catalog()
    assert catalog["ok"] is True
    assert catalog["engine_count"] == len(STRATEGY_NAMES)
    assert catalog["catalog_count"] >= 300
    engine_ids = {row["id"] for row in catalog["engines"]}
    assert {"atr_trail", "ema_volume", "macd_rsi", "pullback_ma", "dual_ma"} <= engine_ids
    trend = market_strategy_catalog(category="trend")
    assert trend["ok"] is True
    assert trend["matched"] >= 1
    assert all(row["category"] == "trend" for row in trend["items"])
    turtle = market_strategy_catalog(query="海龜")
    assert any(row["engine"] == "turtle" for row in turtle["items"])
    ml = market_strategy_catalog(category="ml", status="catalog")
    assert ml["ok"] is True
    assert ml["items"]
    assert all(row["status"] == "catalog" for row in ml["items"])
    listing = market_strategy_catalog(listing=True)
    assert listing["groups"]
    assert listing["matched"] == listing["catalog_count"]
    assert {g["id"] for g in listing["groups"]} >= {"ma", "trend", "ml"}

    closes = _up_then_down(90)
    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(closes),
    )
    alias = market_backtest("600519", strategy="sma_cross_5_20")
    assert alias["ok"] is True
    assert alias["strategy"] == "dual_ma"
    assert alias["requested_strategy"] == "sma_cross_5_20"

    atr = market_backtest("600519", strategy="atr_trail")
    assert atr["ok"] is True
    assert atr["strategy"] == "atr_trail"

    macd_rsi = market_backtest("600519", strategy="macd_rsi")
    assert macd_rsi["ok"] is True
    assert macd_rsi["strategy"] == "macd_rsi"

    pull = market_backtest("600519", strategy="pullback_ma")
    assert pull["ok"] is True

    ema_vol = market_backtest("600519", strategy="ema_volume")
    assert ema_vol["ok"] is True

    missing = market_backtest("600519", strategy="lstm_predictor")
    assert missing["ok"] is False
    assert "market_strategy_catalog" in missing["error"]


def test_stock_quant_volume_strategies(monkeypatch):
    """對齊博客：EnhancedVolumeStrategy／SingleVolumeStrategy 可回測。"""
    prices: list[float] = []
    vols: list[float] = []
    price = 100.0
    for i in range(90):
        if i < 40:
            price *= 0.992
            vols.append(700_000.0)
        elif i < 55:
            price *= 1.018
            vols.append(2_800_000.0)
        else:
            price *= 0.982
            vols.append(3_200_000.0)
        prices.append(round(price, 4))

    monkeypatch.setattr(
        "backend.company.quant_tools._http_get_json",
        lambda url, params=None: _yahoo_payload(prices, volumes=vols),
    )
    catalog = market_strategy_catalog(listing=True)
    ids = {row["id"] for row in catalog["items"]}
    assert {"single_volume", "enhanced_volume"} <= ids
    assert catalog["engine_count"] == len(STRATEGY_NAMES)

    single = market_backtest("600519", strategy="SingleVolumeStrategy")
    assert single["ok"] is True
    assert single["strategy"] == "single_volume"
    assert single["requested_strategy"] == "singlevolumestrategy"
    assert single["trades"] >= 1
    assert single.get("inspired_by")

    enhanced = market_backtest("600519", strategy="enhanced_volume")
    assert enhanced["ok"] is True
    assert enhanced["strategy"] == "enhanced_volume"
    assert enhanced["grade"] in {"enhanced", "ordinary", "none"}
    assert enhanced.get("inspired_by")
    opt = market_optimize("600519", strategy="single_volume")
    assert opt["ok"] is True
    assert opt["best"]
