"""量化行情抓取：HTTP helper、標的別名正規化、Yahoo／東方財富／Stooq／外匯／加密行情。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線 = 21）不變；子模組：
- http：HTTP headers 與 JSON／text GET（_http_get_json／_http_get_text 為 patch 目標）
- symbols：標的別名正規化與交易所代碼推導
- bars：Yahoo／東方財富／Stooq K 線解析與來源降級鏈
- market：行情總覽、報價、K 線、分鐘線與即時行情
- fx：外匯匯率
- crypto：加密貨幣報價
- util：共用小工具（JSON 輸出、數值轉換、錯誤 payload）
- _compat：延遲解析套件層 _http_get_json／_http_get_text，維持 monkeypatch 語意
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from ..constants import (
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
from .bars import (
    _bars_from_stooq,
    _bars_from_yahoo,
    _eastmoney_bars,
    _load_bars,
    _yahoo_chart,
)
from .crypto import (
    _crypto_from_binance,
    _crypto_from_coingecko,
    crypto_quote,
)
from .fx import fx_rate
from .http import (
    _http_get_json,
    _http_get_text,
    _http_headers,
)
from .market import (
    market_kline,
    market_minutes,
    market_quote,
    market_realtime,
    market_sources,
)
from .symbols import (
    _a_share_code,
    _eastmoney_secid,
    _stooq_ticker,
    normalize_symbol,
)
from .util import (
    _fail,
    _num,
    dumps_result,
)

__all__ = [
    "COINGECKO_IDS",
    "CRYPTO_IDS",
    "QUANT_TOOL_NAMES",
    "STRATEGY_NAMES",
    "SYMBOL_ALIASES",
    "_HTTP_TIMEOUT",
    "_KLT_MAP",
    "_MAX_BARS",
    "_RANGE_MAP",
    "_SH_INDEX_CODES",
    "_UA",
    "Any",
    "_a_share_code",
    "_bars_from_stooq",
    "_bars_from_yahoo",
    "_crypto_from_binance",
    "_crypto_from_coingecko",
    "_eastmoney_bars",
    "_eastmoney_secid",
    "_fail",
    "_http_get_json",
    "_http_get_text",
    "_http_headers",
    "_load_bars",
    "_num",
    "_stooq_ticker",
    "_yahoo_chart",
    "annotations",
    "crypto_quote",
    "datetime",
    "dumps_result",
    "fx_rate",
    "httpx",
    "json",
    "market_kline",
    "market_minutes",
    "market_quote",
    "market_realtime",
    "market_sources",
    "normalize_symbol",
    "re",
    "timezone",
]

# 移除子模組在套件上的屬性，維持 dir() 非底線名稱與原單檔模組一致（21 個）。
for _submodule in ("bars", "crypto", "fx", "http", "market", "symbols", "util"):
    globals().pop(_submodule, None)
del _submodule
