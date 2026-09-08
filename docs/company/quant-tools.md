# 量化行情工具（角色引用）

對齊 [stock-quant](https://github.com/iiooiioo888/stock-quant) 的角色側能力：報價、K 線／分鐘線、31 種策略回測（含博客內建增強成交量／單成交量；滑點／T+1／漲跌停／移動止損）、策略庫分類目錄、網格優化、Walk-Forward、熱力圖、訊號投票、策略排行、11 種組合方法、盯盤、選股、基本面、個股／大盤資金流、北向、龍虎榜、板塊、基準對比。  
以公司 `tool_registry` 的 ReAct `tool_call` 交給量化研究桌角色呼叫，**不**嵌入其完整 Web 工作站。人類可在實驗室 **策略庫**（`#/monitor/lab/quant`）瀏覽分類樹，勾選可回測項並複製 `market_backtest` 呼叫，頁面中間會用 [Archify](https://github.com/tt-a1i/archify) CLI 畫工作流，並顯示權益曲線與收盤價；**策略圖**（`#/monitor/lab/maps`）同樣呼叫 Archify 把全部策略畫成總覽、分類拓撲與工作流。量化角色監控頁有同一入口。

Hub 的 `StocksX_get_price` 仍為沙箱測試工具；真實公開行情走下列免費 API（`httpx`，無 yfinance／akshare 依賴）。

## 資料源

| 市場 | 已接通 | 備援 | 金鑰 |
|------|--------|------|------|
| A 股／美股／指數 | Yahoo Finance chart | 東方財富／新浪（A 股）、Stooq（美股） | 不需 |
| A 股基本面／資金流／板塊／龍虎榜／分鐘線 | 東方財富公開接口 | 新浪即時盤口 | 不需 |
| 外匯 | Frankfurter（歐洲央行） | fawazahmed0/currency-api | 不需 |
| 加密貨幣 | CoinPaprika | CoinGecko Demo → Binance 24h ticker | 不需 |
| A 股日線（可選） | Tushare | — | `EVOL_TUSHARE_TOKEN` |
| 美股（可選） | Finnhub／Alpha Vantage | — | `EVOL_FINNHUB_TOKEN`／`EVOL_ALPHAVANTAGE_KEY` |

`market_sources` 另列出 BaoStock、iTick、QOS、AKShare 等目錄項（`wired=false` 或僅 Token 就緒時為 true）。不引入 akshare／yfinance 套件。

## 工具

| 工具 | 說明 |
|------|------|
| `market_quote` | 最新行情（可傳 `茅台`、`600519`、`AAPL`） |
| `market_kline` | 歷史 K 線 |
| `market_minutes` | A 股分鐘線（1m/5m/15m/30m/60m） |
| `market_realtime` | A 股優先新浪盤口 |
| `market_backtest` | 31 種引擎（含 `enhanced_volume`／`single_volume`）；可用策略庫別名（如 `sma_cross_5_20`、`EnhancedVolumeStrategy`）；可設 `slippage_pct`／`stop_loss_pct`／`take_profit_pct`／`trailing_stop_pct`／`enable_t1`／`enable_limit` |
| `market_strategy_catalog` | 分類／搜尋策略庫。未篩選回可回測引擎；`category`／`query`／`status` 列出目錄。`wired` 可回測，`catalog` 為規劃項 |
| `archify_strategies` | 把策略庫編成 Archify IR。`view=overview｜data_flow｜lifecycle｜group｜strategy`，`id` 為分類或策略 |
| `market_compare` | 同一標的跑全部策略並依夏普排序 |
| `market_optimize` | 網格搜尋參數 |
| `market_walkforward` | 樣本內優化、樣本外驗證 |
| `market_heatmap` | dual_ma 短／長均線夏普熱力圖 |
| `market_signals` | 全部策略最新多空與投票共識 |
| `market_leaderboard` | 多標的策略平均夏普排行 |
| `market_watch` | 盯盤：漲跌幅、MA20、雙均線訊號 |
| `market_search` | 關鍵字搜尋標的 |
| `market_screener` | A 股漲跌／PE／市值快照 |
| `market_fundamentals` | A 股 PE／PB／ROE／市值 |
| `market_capital_flow` | 個股資金流向 |
| `market_flow` | 大盤（上證）資金流向 |
| `market_north_flow` | 北向資金 |
| `market_dragon_tiger` | 龍虎榜 |
| `market_sectors` | 行業／概念板塊 |
| `market_benchmark` | 相對滬深300 的 Alpha／Beta |
| `market_returns` | 多標的區間收益對比 |
| `market_portfolio` | `equal_weight`／`risk_parity`／`vol_target`／`kelly`／`mvo`／`max_div`／`anti_corr`／`regime`／`frontier`／`dynamic`／`degradation` |
| `fx_rate` | 外匯匯率 |
| `crypto_quote` | 加密貨幣美元報價 |
| `market_sources` | 列出資料源與可回測策略 |

引擎策略 id：`dual_ma`、`macd`、`rsi`、`bollinger`、`momentum`、`mean_reversion`、`breakout`、`kdj`、`ema_cross`、`triple_ma`、`turtle`、`donchian`、`williams_r`、`cci`、`volume_price`、`envelope`、`obv`、`bollinger_squeeze`、`supertrend`、`adx_trend`、`dual_thrust`、`grid`、`vwap`、`parabolic_sar`、`atr_trail`、`ema_volume`、`macd_rsi`、`pullback_ma`、`composite`、`single_volume`、`enhanced_volume`。

`single_volume` 對齊博客 **SingleVolumeStrategy**（現量 vs 5／20 日均量、成交量標準差閾值、連續陰陽線）。`enhanced_volume` 對齊 **EnhancedVolumeStrategy**：普通訊號（量能＋K 線）再經 RSI／布林／KDJ 至少兩項確認後升級為增強訊號，降低假訊號。別名：`SingleVolumeStrategy`、`EnhancedVolumeStrategy`。

策略庫對齊 stock-quant `strategies/strategy_library.py`（均線／動量／均值回歸／波動率／趨勢／形態／突破／組合／ML 規劃）。

- 瀏覽：實驗室 → **策略庫**，或 `GET /lab/quant/strategies`；圖表預覽 `GET /lab/quant/preview?strategy=dual_ma&symbol=600519`；**資金流三視圖** `GET /lab/quant/capital-flow?strategy=dual_ma&symbol=600519&initial_capital=1000000`（瀑布 Mermaid、狀態機、時間軸表）
- 可視化：實驗室 → **策略圖**，或 `GET /lab/archify/strategies`；單策略 `GET /lab/archify/strategies/dual_ma`；正式圖 `GET /lab/archify/html?view=overview`（`view=group&id=ma`／`view=strategy&id=dual_ma`），由前端依賴 `archify`（`file:../vendor/archify`，上游 [tt-a1i/archify](https://github.com/tt-a1i/archify)）CLI 渲染；亦可 `GET /lab/archify/artifact` 直接取 HTML
- 角色：先呼叫：

```tool_call
{"tool": "market_strategy_catalog", "args": {"category": "trend"}}
```

```tool_call
{"tool": "archify_strategies", "args": {"view": "strategy", "id": "dual_ma"}}
```

呼叫格式與其他公司工具相同：

```tool_call
{"tool": "market_quote", "args": {"symbol": "茅台"}}
```

```tool_call
{"tool": "market_compare", "args": {"symbol": "600519", "range": "1y"}}
```

```tool_call
{"tool": "market_backtest", "args": {"symbol": "600519", "strategy": "enhanced_volume"}}
```

```tool_call
{"tool": "market_walkforward", "args": {"symbol": "600519", "strategy": "dual_ma"}}
```

## 可引用角色

`finance_lead`、`quant_analyst`、`risk_analyst`、`market_data_eng`、`portfolio_mgr`、`sentiment_analyst`、`analyst`、`researcher`、`manager`。

量化研究桌（`create_quant_desk`）會指派上述金融角色；輸出必須標明來源、時間戳與不確定性，禁止保證報酬。

實作：`backend/company/quant_tools.py`、`quant_strategy_catalog.py`、`quant_strategy_maps.py`，於 `_register_builtin_tools` 註冊。
