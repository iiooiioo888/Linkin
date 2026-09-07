"""stock-quant 策略庫目錄 — 分類／搜尋給角色引用。

對齊 https://github.com/iiooiioo888/stock-quant 的 strategies/strategy_library.py
與 src/core/strategies/ 引擎。不引入 backtrader。

- wired：本倉庫可交給 market_backtest 實際回測（31 種引擎 + 目錄別名）
- catalog：目錄項，角色可查閱；尚未接通引擎時不可回測
"""

from __future__ import annotations

from typing import Any

CATALOG_CATEGORIES: dict[str, str] = {
    "ma": "移動平均線",
    "momentum": "動量／震盪指標",
    "mean_reversion": "均值回歸",
    "volatility": "波動率",
    "trend": "趨勢跟蹤",
    "pattern": "形態識別",
    "breakout": "突破",
    "composite": "組合",
    "ml": "機器學習輔助（規劃）",
}

# id → 引擎策略 id。目錄別名與引擎同名者不需列出。
ENGINE_ALIASES: dict[str, str] = {
    "sma_cross_5_20": "dual_ma",
    "ema_cross_12_26": "ema_cross",
    "ma_envelope": "envelope",
    "vwap_cross": "vwap",
    "golden_death": "dual_ma",
    "trend_ma": "dual_ma",
    "rsi_momentum": "rsi",
    "macd_signal": "macd",
    "stochastic": "kdj",
    "cci_commodity": "cci",
    "momentum_roc": "momentum",
    "bollinger_mr": "bollinger",
    "rsi_mr": "rsi",
    "bb_squeeze": "bollinger_squeeze",
    "z_score": "mean_reversion",
    "vol_breakout": "breakout",
    "atr_trailing": "atr_trail",
    "keltner": "envelope",
    "turtle_trading": "turtle",
    "channel_breakout": "breakout",
    "adx_trend_follow": "adx_trend",
    "donchian_breakout": "donchian",
    "turtle_breakout": "turtle",
    "bollinger_breakout": "bollinger_squeeze",
    "squeeze_momentum": "bollinger_squeeze",
    "volume_breakout": "volume_price",
    "ma_rsi_combo": "composite",
    "macd_bb_combo": "macd_rsi",
    "vote_system": "composite",
    "composite_master": "composite",
    "vwap_momentum": "vwap",
    "supertrend_adx": "supertrend",
    "volume_confirmed": "volume_price",
    "breakout_pullback": "pullback_ma",
    "enhancedvolumestrategy": "enhanced_volume",
    "singlevolumestrategy": "single_volume",
    "enhanced_volume_strategy": "enhanced_volume",
    "single_volume_strategy": "single_volume",
}

_ENGINE_ROWS: tuple[tuple[str, str, str], ...] = (
    ("dual_ma", "雙均線金叉/死叉", "ma"),
    ("ema_cross", "EMA 金叉/死叉", "ma"),
    ("triple_ma", "三重均線", "ma"),
    ("envelope", "均線通道", "ma"),
    ("ema_volume", "EMA 量價確認", "ma"),
    ("pullback_ma", "趨勢回調均線", "ma"),
    ("macd", "MACD 金叉/死叉", "momentum"),
    ("rsi", "RSI 超買超賣", "momentum"),
    ("kdj", "KDJ 隨機指標", "momentum"),
    ("williams_r", "威廉指標", "momentum"),
    ("cci", "CCI 順勢", "momentum"),
    ("momentum", "動量 ROC", "momentum"),
    ("adx_trend", "ADX 趨勢", "momentum"),
    ("parabolic_sar", "拋物線 SAR", "momentum"),
    ("volume_price", "量價齊升", "momentum"),
    ("obv", "OBV 能量潮", "momentum"),
    ("bollinger", "布林帶均值回歸", "mean_reversion"),
    ("mean_reversion", "Z-score 均值回歸", "mean_reversion"),
    ("bollinger_squeeze", "布林帶收窄突破", "mean_reversion"),
    ("grid", "網格偏離", "mean_reversion"),
    ("atr_trail", "ATR 移動止損趨勢", "volatility"),
    ("donchian", "唐奇安通道", "volatility"),
    ("turtle", "海龜趨勢", "trend"),
    ("dual_thrust", "DualThrust 突破", "trend"),
    ("supertrend", "SuperTrend", "trend"),
    ("breakout", "N 日高點突破", "breakout"),
    ("vwap", "VWAP 偏離", "ma"),
    ("macd_rsi", "MACD+RSI 過濾", "composite"),
    ("composite", "多策略投票", "composite"),
    ("single_volume", "單成交量", "momentum"),
    ("enhanced_volume", "增強成交量（RSI／布林／KDJ）", "composite"),
)

# stock-quant STRATEGY_LIBRARY 目錄項（不含已列入引擎的同名 id）
_CATALOG_ROWS: tuple[tuple[str, str, str], ...] = (
    ("sma_cross_5_20", "經典雙均線交叉 5/20", "ma"),
    ("ema_cross_12_26", "EMA 交叉 12/26", "ma"),
    ("ma_envelope", "均線包絡線", "ma"),
    ("guppy_mma", "古皮多週期均線", "ma"),
    ("vwap_cross", "VWAP 交叉", "ma"),
    ("hma_trend", "赫爾移動平均趨勢", "ma"),
    ("kama_adaptive", "考夫曼自適應均線", "ma"),
    ("mama_fama", "MESA 自適應均線", "ma"),
    ("alma_trend", "Arnaud Legoux 均線", "ma"),
    ("sma_ribbon", "均線帶", "ma"),
    ("ema_wave", "EMA 波浪", "ma"),
    ("dema_cross", "雙指數均線交叉", "ma"),
    ("tema_trend", "三重指數均線", "ma"),
    ("wma_momentum", "加權均線動量", "ma"),
    ("smma_trend", "平滑均線趨勢", "ma"),
    ("lsma_regression", "最小二乘均線", "ma"),
    ("mcginley_dynamic", "McGinley 動態指標", "ma"),
    ("zlema_zero_lag", "零滯後 EMA", "ma"),
    ("vpid_volume", "成交量加權價格", "ma"),
    ("ma_slope", "均線斜率", "ma"),
    ("ma_channel", "均線通道突破", "ma"),
    ("dual_ema_filter", "雙 EMA 過濾", "ma"),
    ("triple_ema", "三重 EMA", "ma"),
    ("ma_bounce", "均線反彈", "ma"),
    ("adaptive_ma", "自適應均線交叉", "ma"),
    ("ma_divergence", "均線背離", "ma"),
    ("multi_tf_ma", "多時間框架均線", "ma"),
    ("ma_exhaustion", "均線極值", "ma"),
    ("golden_death", "黃金／死亡交叉確認", "ma"),
    ("rsi_momentum", "RSI 動量", "momentum"),
    ("macd_signal", "MACD 信號線交叉", "momentum"),
    ("stochastic", "隨機震盪器", "momentum"),
    ("cci_commodity", "商品通道指標", "momentum"),
    ("momentum_roc", "動量變化率", "momentum"),
    ("awesome_oscillator", "Awesome Oscillator", "momentum"),
    ("aroon", "Aroon 震盪器", "momentum"),
    ("trix", "TRIX 動量", "momentum"),
    ("ultimate_oscillator", "Ultimate Oscillator", "momentum"),
    ("kst", "Know Sure Thing", "momentum"),
    ("ichimoku", "一目均衡表", "momentum"),
    ("dm_index", "DM 指數", "momentum"),
    ("mass_index", "Mass Index 反轉", "momentum"),
    ("vortex", "Vortex Indicator", "momentum"),
    ("coppock", "Coppock Curve", "momentum"),
    ("fisher_transform", "Fisher Transform", "momentum"),
    ("ehlers_fisher", "Ehlers Fisher", "momentum"),
    ("bollinger_mr", "布林帶均值回歸", "mean_reversion"),
    ("rsi_mr", "RSI 均值回歸", "mean_reversion"),
    ("bb_squeeze", "布林帶擠壓突破", "mean_reversion"),
    ("pairs_trading", "配對交易", "mean_reversion"),
    ("stat_arb", "統計套利", "mean_reversion"),
    ("ornstein_uhlenbeck", "OU 過程均值回歸", "mean_reversion"),
    ("kalman_filter", "卡爾曼濾波追蹤", "mean_reversion"),
    ("hurst_exponent", "Hurst 指數", "mean_reversion"),
    ("cointegration", "共整合測試", "mean_reversion"),
    ("gap_fill", "缺口回補", "mean_reversion"),
    ("overnight_gap", "隔夜缺口反轉", "mean_reversion"),
    ("intraday_reversion", "日內均值回歸", "mean_reversion"),
    ("vw_mr", "成交量加權均值回歸", "mean_reversion"),
    ("standardized_price", "標準化價格", "mean_reversion"),
    ("detrended_osc", "去趨勢震盪器", "mean_reversion"),
    ("channel_reversion", "通道回歸", "mean_reversion"),
    ("percentile_channel", "百分位通道", "mean_reversion"),
    ("range_bound", "區間震盪", "mean_reversion"),
    ("mr_atr", "ATR 均值回歸", "mean_reversion"),
    ("z_score", "Z-Score 交易", "mean_reversion"),
    ("vol_breakout", "波動率突破", "volatility"),
    ("atr_trailing", "ATR 追蹤止損", "volatility"),
    ("keltner", "肯特納通道", "volatility"),
    ("vol_contraction", "波動率收縮", "volatility"),
    ("historical_vol", "歷史波動率", "volatility"),
    ("implied_vol", "隱含波動率代理", "volatility"),
    ("vol_targeting", "波動率目標配置", "volatility"),
    ("parkinson_vol", "Parkinson 波動率", "volatility"),
    ("garman_klass", "Garman-Klass 波動率", "volatility"),
    ("yang_zhang", "Yang-Zhang 波動率", "volatility"),
    ("tr_expansion", "真實波幅擴張", "volatility"),
    ("vol_ratio", "波動率比率", "volatility"),
    ("choppiness", "Choppiness Index", "volatility"),
    ("ulcer_index", "Ulcer Index", "volatility"),
    ("natr", "標準化 ATR", "volatility"),
    ("vol_clustering", "波動率聚集", "volatility"),
    ("beta_weighted", "Beta 加權", "volatility"),
    ("corr_breakdown", "相關性崩潰", "volatility"),
    ("regime_switching", "體制轉換", "volatility"),
    ("trend_ma", "趨勢跟蹤均線", "trend"),
    ("turtle_trading", "海龜交易法則", "trend"),
    ("channel_breakout", "通道突破", "trend"),
    ("adx_trend_follow", "ADX 趨勢跟蹤", "trend"),
    ("chandelier_exit", "Chandelier Exit", "trend"),
    ("linear_regression", "線性回歸趨勢", "trend"),
    ("ts_forecast", "時間序列預測", "trend"),
    ("vortex_trend", "Vortex 趨勢", "trend"),
    ("gator_osc", "Gator Oscillator", "trend"),
    ("frama", "FRAMA 自適應均線", "trend"),
    ("kaufman_efficiency", "Kaufman 效率比率", "trend"),
    ("price_oscillator", "價格震盪器", "trend"),
    ("qstick", "QStick", "trend"),
    ("rainbow_osc", "Rainbow Oscillator", "trend"),
    ("schaff_trend", "Schaff Trend Cycle", "trend"),
    ("smi_ergodic", "SMI Ergodic", "trend"),
    ("t3_trend", "T3 趨勢", "trend"),
    ("vidya", "VIDYA 自適應均線", "trend"),
    ("doji_pattern", "十字星", "pattern"),
    ("hammer_pattern", "錘頭", "pattern"),
    ("engulfing_pattern", "吞噬", "pattern"),
    ("harami_pattern", "孕線", "pattern"),
    ("morning_star", "晨星", "pattern"),
    ("evening_star", "暮星", "pattern"),
    ("shooting_star", "射擊之星", "pattern"),
    ("three_white_soldiers", "三白兵", "pattern"),
    ("three_black_crows", "三烏鴉", "pattern"),
    ("dark_cloud_cover", "烏雲蓋頂", "pattern"),
    ("piercing_line", "刺透", "pattern"),
    ("tweezer_top", "鑷子頂", "pattern"),
    ("tweezer_bottom", "鑷子底", "pattern"),
    ("abandoned_baby", "棄嬰", "pattern"),
    ("dragonfly_doji", "蜻蜓十字", "pattern"),
    ("gravestone_doji", "墓碑十字", "pattern"),
    ("marubozu", "光頭光腳", "pattern"),
    ("spinning_top", "紡錘", "pattern"),
    ("rising_three_methods", "上升三法", "pattern"),
    ("falling_three_methods", "下降三法", "pattern"),
    ("bullish_flag", "看漲旗形", "pattern"),
    ("bearish_flag", "看跌旗形", "pattern"),
    ("bullish_pennant", "看漲三角旗", "pattern"),
    ("bearish_pennant", "看跌三角旗", "pattern"),
    ("head_shoulders", "頭肩頂", "pattern"),
    ("inverse_head_shoulders", "頭肩底", "pattern"),
    ("double_top", "雙頂", "pattern"),
    ("double_bottom", "雙底", "pattern"),
    ("triple_top", "三重頂", "pattern"),
    ("triple_bottom", "三重底", "pattern"),
    ("ascending_triangle", "上升三角", "pattern"),
    ("descending_triangle", "下降三角", "pattern"),
    ("symmetrical_triangle", "對稱三角", "pattern"),
    ("wedge_rising", "上升楔形", "pattern"),
    ("wedge_falling", "下降楔形", "pattern"),
    ("rectangle_pattern", "矩形", "pattern"),
    ("diamond_top", "鑽石頂", "pattern"),
    ("diamond_bottom", "鑽石底", "pattern"),
    ("cup_and_handle", "杯柄", "pattern"),
    ("inverse_cup_handle", "倒杯柄", "pattern"),
    ("rounding_bottom", "圓弧底", "pattern"),
    ("rounding_top", "圓弧頂", "pattern"),
    ("v_bottom", "V 底", "pattern"),
    ("v_top", "V 頂", "pattern"),
    ("island_reversal", "島形反轉", "pattern"),
    ("key_reversal", "關鍵反轉", "pattern"),
    ("outside_bar", "外包線", "pattern"),
    ("inside_bar", "內包線", "pattern"),
    ("fakey_pattern", "假突破回抽", "pattern"),
    ("pin_bar", "Pin Bar", "pattern"),
    ("engulfing_combo", "吞噬組合", "pattern"),
    ("railroad_tracks", "鐵軌", "pattern"),
    ("kicker_pattern", "反沖", "pattern"),
    ("mat_hold", "鋪墊", "pattern"),
    ("separating_lines", "分手線", "pattern"),
    ("unusual_volume", "異常量能", "pattern"),
    ("volume_climax", "量能高潮", "pattern"),
    ("exhaustion_gap", "竭盡缺口", "pattern"),
    ("breakaway_gap", "突破缺口", "pattern"),
    ("runaway_gap", "持續缺口", "pattern"),
    ("opening_range_breakout", "開盤區間突破", "breakout"),
    ("volatility_breakout_atr", "ATR 波動突破", "breakout"),
    ("donchian_breakout", "唐奇安突破", "breakout"),
    ("bollinger_breakout", "布林帶突破", "breakout"),
    ("keltner_breakout", "肯特納突破", "breakout"),
    ("box_breakout", "箱體突破", "breakout"),
    ("consolidation_breakout", "盤整突破", "breakout"),
    ("squeeze_momentum", "擠壓動量突破", "breakout"),
    ("turtle_breakout", "海龜突破", "breakout"),
    ("channel_surge", "通道急升", "breakout"),
    ("momentum_breakout", "動量突破", "breakout"),
    ("volume_breakout", "量能突破", "breakout"),
    ("gap_breakout", "缺口突破", "breakout"),
    ("premarket_breakout", "盤前突破", "breakout"),
    ("after_hours_breakout", "盤後突破", "breakout"),
    ("support_resistance_break", "支撐阻力突破", "breakout"),
    ("pivot_point_breakout", "樞軸點突破", "breakout"),
    ("fibonacci_breakout", "斐波那契突破", "breakout"),
    ("moving_average_breakout", "均線突破", "breakout"),
    ("ema_band_breakout", "EMA 帶突破", "breakout"),
    ("volatility_expansion", "波動擴張", "breakout"),
    ("range_expansion", "區間擴張", "breakout"),
    ("true_breakout", "真突破", "breakout"),
    ("false_breakout_filter", "假突破過濾", "breakout"),
    ("breakout_pullback", "突破回調", "breakout"),
    ("breakout_retest", "突破回測", "breakout"),
    ("multi_timeframe_breakout", "多週期突破", "breakout"),
    ("session_breakout", "時段突破", "breakout"),
    ("london_breakout", "倫敦時段突破", "breakout"),
    ("ny_breakout", "紐約時段突破", "breakout"),
    ("tokyo_breakout", "東京時段突破", "breakout"),
    ("asian_range_breakout", "亞洲區間突破", "breakout"),
    ("euro_session_breakout", "歐洲時段突破", "breakout"),
    ("overnight_breakout", "隔夜突破", "breakout"),
    ("intraday_breakout", "日內突破", "breakout"),
    ("swing_breakout", "波段突破", "breakout"),
    ("position_breakout", "部位突破", "breakout"),
    ("earnings_breakout", "財報突破", "breakout"),
    ("news_breakout", "新聞突破", "breakout"),
    ("catalyst_breakout", "催化劑突破", "breakout"),
    ("sector_breakout", "板塊突破", "breakout"),
    ("market_breakout", "大盤突破", "breakout"),
    ("index_breakout", "指數突破", "breakout"),
    ("correlation_breakout", "相關性突破", "breakout"),
    ("spread_breakout", "價差突破", "breakout"),
    ("ratio_breakout", "比率突破", "breakout"),
    ("pairs_breakout", "配對突破", "breakout"),
    ("basket_breakout", "籃子突破", "breakout"),
    ("portfolio_breakout", "組合突破", "breakout"),
    ("adaptive_breakout", "自適應突破", "breakout"),
    ("dynamic_breakout", "動態突破", "breakout"),
    ("static_breakout", "靜態突破", "breakout"),
    ("hybrid_breakout", "混合突破", "breakout"),
    ("confirmation_breakout", "確認突破", "breakout"),
    ("divergence_breakout", "背離突破", "breakout"),
    ("convergence_breakout", "聚合突破", "breakout"),
    ("momentum_confirmed", "動量確認突破", "breakout"),
    ("volume_confirmed", "量能確認突破", "breakout"),
    ("trend_confirmed", "趨勢確認突破", "breakout"),
    ("breakout_master", "突破總策略", "breakout"),
    ("ma_rsi_combo", "均線+RSI 組合", "composite"),
    ("macd_bb_combo", "MACD+布林組合", "composite"),
    ("triple_screen", "三重濾網", "composite"),
    ("elder_ray", "Elder Ray", "composite"),
    ("alligator_stochastic", "鱷魚+隨機指標", "composite"),
    ("ichimoku_rsi", "一目+RSI", "composite"),
    ("supertrend_adx", "SuperTrend+ADX", "composite"),
    ("vwap_momentum", "VWAP 動量", "composite"),
    ("fibonacci_retracement", "斐波那契回撤", "composite"),
    ("pivot_fibonacci", "樞軸+斐波那契", "composite"),
    ("gann_fan", "江恩扇", "composite"),
    ("gann_box", "江恩箱", "composite"),
    ("gann_square", "江恩正方形", "composite"),
    ("time_price_opportunity", "時間價格機會", "composite"),
    ("market_profile", "市場輪廓", "composite"),
    ("volume_profile", "成交量輪廓", "composite"),
    ("order_flow", "訂單流", "composite"),
    ("footprint_chart", "足跡圖", "composite"),
    ("delta_divergence", "Delta 背離", "composite"),
    ("cumulative_delta", "累積 Delta", "composite"),
    ("smart_money", "聰明錢", "composite"),
    ("institutional_flow", "機構資金流", "composite"),
    ("dark_pool", "暗池", "composite"),
    ("block_trade", "大宗交易", "composite"),
    ("tape_reading", "盤口解讀", "composite"),
    ("level2_data", "Level2", "composite"),
    ("market_depth", "市場深度", "composite"),
    ("bid_ask_spread", "買賣價差", "composite"),
    ("liquidity_hunt", "流動性獵取", "composite"),
    ("stop_hunt", "止損獵殺", "composite"),
    ("wyckoff_accumulation", "威科夫吸籌", "composite"),
    ("wyckoff_distribution", "威科夫派發", "composite"),
    ("elliott_wave", "艾略特波浪", "composite"),
    ("harmonic_pattern", "諧波形態", "composite"),
    ("bat_pattern", "蝙蝠形態", "composite"),
    ("gartley_pattern", "加特利形態", "composite"),
    ("butterfly_pattern", "蝴蝶形態", "composite"),
    ("crab_pattern", "螃蟹形態", "composite"),
    ("cypher_pattern", "賽福形態", "composite"),
    ("shark_pattern", "鯊魚形態", "composite"),
    ("abcd_pattern", "ABCD 形態", "composite"),
    ("three_drives", "三驅", "composite"),
    ("alternate_bat", "交替蝙蝠", "composite"),
    ("deep_crab", "深潛螃蟹", "composite"),
    ("kieline", "基線", "composite"),
    ("tenkan_kijun_cross", "轉換線／基準線交叉", "composite"),
    ("cloud_breakout", "雲層突破", "composite"),
    ("lagging_span", "遲行線", "composite"),
    ("tk_cross_signal", "TK 交叉訊號", "composite"),
    ("full_ichimoku", "完整一目均衡表", "composite"),
    ("multi_indicator", "多指標", "composite"),
    ("indicator_fusion", "指標融合", "composite"),
    ("signal_aggregator", "訊號聚合", "composite"),
    ("vote_system", "投票系統", "composite"),
    ("weighted_signal", "加權訊號", "composite"),
    ("confidence_score", "信心分數", "composite"),
    ("risk_adjusted", "風險調整", "composite"),
    ("kelly_criterion", "凱利公式", "composite"),
    ("optimal_f", "Optimal F", "composite"),
    ("composite_master", "組合總策略", "composite"),
    ("ml_classifier", "ML 分類", "ml"),
    ("ml_regression", "ML 回歸", "ml"),
    ("random_forest", "隨機森林", "ml"),
    ("gradient_boosting", "梯度提升", "ml"),
    ("xgboost_signal", "XGBoost 訊號", "ml"),
    ("lightgbm_signal", "LightGBM 訊號", "ml"),
    ("catboost_signal", "CatBoost 訊號", "ml"),
    ("svm_classifier", "SVM 分類", "ml"),
    ("svm_regression", "SVM 回歸", "ml"),
    ("neural_network", "神經網路", "ml"),
    ("deep_learning", "深度學習", "ml"),
    ("lstm_predictor", "LSTM 預測", "ml"),
    ("gru_predictor", "GRU 預測", "ml"),
    ("cnn_pattern", "CNN 形態", "ml"),
    ("transformer_model", "Transformer", "ml"),
    ("attention_mechanism", "注意力機制", "ml"),
    ("ensemble_ml", "ML 集成", "ml"),
    ("stacking_model", "堆疊模型", "ml"),
    ("blending_model", "混合模型", "ml"),
    ("feature_engineering", "特徵工程", "ml"),
    ("feature_selection", "特徵選擇", "ml"),
    ("dimensionality_reduction", "降維", "ml"),
    ("pca_features", "PCA 特徵", "ml"),
    ("autoencoder", "自編碼器", "ml"),
    ("clustering_kmeans", "K-Means 分群", "ml"),
    ("clustering_dbscan", "DBSCAN 分群", "ml"),
    ("regime_detection", "體制偵測", "ml"),
    ("market_state", "市場狀態", "ml"),
    ("sentiment_analysis", "情緒分析", "ml"),
    ("nlp_news", "新聞 NLP", "ml"),
    ("social_sentiment", "社交情緒", "ml"),
    ("twitter_analysis", "Twitter 分析", "ml"),
    ("reddit_sentiment", "Reddit 情緒", "ml"),
    ("fear_greed_index", "恐懼貪婪指數", "ml"),
    ("alternative_data", "另類數據", "ml"),
    ("satellite_data", "衛星數據", "ml"),
    ("credit_card_data", "信用卡數據", "ml"),
    ("web_traffic", "網站流量", "ml"),
    ("app_downloads", "App 下載", "ml"),
    ("supply_chain", "供應鏈", "ml"),
    ("weather_impact", "天氣影響", "ml"),
    ("seasonal_pattern", "季節形態", "ml"),
    ("calendar_effect", "日曆效應", "ml"),
    ("anomaly_detection", "異常偵測", "ml"),
    ("outlier_detection", "離群偵測", "ml"),
    ("change_point", "變點偵測", "ml"),
    ("reinforcement_learning", "強化學習", "ml"),
    ("q_learning", "Q-Learning", "ml"),
    ("policy_gradient", "策略梯度", "ml"),
    ("actor_critic", "Actor-Critic", "ml"),
    ("deep_q_network", "Deep Q Network", "ml"),
    ("monte_carlo_tree", "蒙地卡羅樹搜尋", "ml"),
    ("bayesian_optimization", "貝葉斯優化", "ml"),
    ("hyperparameter_tune", "超參數調校", "ml"),
    ("genetic_algorithm", "遺傳演算法", "ml"),
    ("particle_swarm", "粒子群", "ml"),
    ("simulated_annealing", "模擬退火", "ml"),
    ("meta_learning", "元學習", "ml"),
    ("transfer_learning", "遷移學習", "ml"),
    ("ml_master", "ML 總策略", "ml"),
)


def _engine_ids() -> set[str]:
    return {sid for sid, _name, _cat in _ENGINE_ROWS}


def resolve_strategy(name: str) -> str | None:
    """把目錄 id／別名解析成可回測引擎 id；無法回測則回 None。"""
    key = (name or "").strip().lower()
    if not key:
        return None
    engines = _engine_ids()
    if key in engines:
        return key
    mapped = ENGINE_ALIASES.get(key)
    if mapped in engines:
        return mapped
    return None


def _status_for(sid: str, engines: set[str]) -> str:
    if sid in engines or ENGINE_ALIASES.get(sid) in engines:
        return "wired"
    return "catalog"


def _all_items(engines: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for sid, name, cat in (*_ENGINE_ROWS, *_CATALOG_ROWS):
        if sid in seen:
            continue
        seen.add(sid)
        engine = resolve_strategy(sid) if sid in engines or sid in ENGINE_ALIASES else None
        if sid in engines:
            engine = sid
        items.append(
            {
                "id": sid,
                "name": name,
                "category": cat,
                "category_name": CATALOG_CATEGORIES.get(cat, cat),
                "status": _status_for(sid, engines),
                "engine": engine,
            }
        )
    return items


def _groups_for(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for cid, label in CATALOG_CATEGORIES.items():
        children = [row for row in items if row["category"] == cid]
        if not children:
            continue
        groups.append(
            {
                "id": cid,
                "name": label,
                "total": len(children),
                "wired": sum(1 for row in children if row["status"] == "wired"),
                "items": children,
            }
        )
    return groups


def market_strategy_catalog(
    category: str = "",
    query: str = "",
    status: str = "",
    listing: bool = False,
) -> dict[str, Any]:
    """列出策略庫。未篩選時回摘要＋可回測引擎，避免塞爆上下文。"""
    engines = _engine_ids()
    items = _all_items(engines)
    cat = (category or "").strip().lower()
    if cat in {"oscillator", "osc"}:
        cat = "momentum"
    q = (query or "").strip().lower()
    want_status = (status or "").strip().lower()
    want_listing = listing is True or str(listing).strip().lower() in {"1", "true", "yes"}
    filtered = items
    if cat:
        if cat not in CATALOG_CATEGORIES:
            allowed = " / ".join(CATALOG_CATEGORIES)
            return {
                "ok": False,
                "error": f"未知分類 {category}，可用 {allowed}",
                "tool": "market_strategy_catalog",
            }
        filtered = [row for row in filtered if row["category"] == cat]
    if q:
        filtered = [
            row
            for row in filtered
            if q in row["id"] or q in row["name"].lower() or q in row["category"]
        ]
    if want_status in {"wired", "catalog"}:
        filtered = [row for row in filtered if row["status"] == want_status]

    cat_stats: list[dict[str, Any]] = []
    for cid, label in CATALOG_CATEGORIES.items():
        group = [row for row in items if row["category"] == cid]
        cat_stats.append(
            {
                "id": cid,
                "name": label,
                "total": len(group),
                "wired": sum(1 for row in group if row["status"] == "wired"),
            }
        )

    show_list = bool(cat or q or want_status or want_listing)
    payload: dict[str, Any] = {
        "ok": True,
        "inspired_by": "https://github.com/iiooiioo888/stock-quant",
        "engine_count": len(engines),
        "catalog_count": len(items),
        "wired_count": sum(1 for row in items if row["status"] == "wired"),
        "categories": cat_stats,
        "disclaimer": "wired 可 market_backtest；catalog 僅目錄／規劃，禁止當收益保證。",
    }
    if show_list:
        payload["matched"] = len(filtered)
        payload["items"] = filtered
        payload["groups"] = _groups_for(filtered)
        payload["hint"] = "把 items[].engine 或 wired 的 id 傳給 market_backtest.strategy。"
    else:
        payload["engines"] = [
            {"id": sid, "name": name, "category": cat}
            for sid, name, cat in _ENGINE_ROWS
            if sid in engines
        ]
        payload["hint"] = (
            "預設只回可回測引擎與分類計數。傳 listing=true 或 category=ma／momentum／mean_reversion／"
            "volatility／trend／pattern／breakout／composite／ml，或 query／status=wired|catalog 列出目錄。"
        )
    return payload
