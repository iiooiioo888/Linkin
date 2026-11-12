"""量化分析：多標的對比、搜尋、基本面、資金流、板塊、盯盤與基準比較。

第十四輪重構：實作已拆至本次套件子模組，對外 import 路徑
from backend.company.quant_tools.analysis import ... 與公開名稱（dir() 非底線 = 19）不變：
- eastmoney：東方財富資料端點（基本面／資金流／北向／龍虎榜／板塊／大盤流）
- watch：簡易盯盤
- compare：多策略對比、基準比較與區間收益排行
- screener：標的搜尋、盤面篩選與基本面
HTTP 仍經 data 套件模組屬性 _data._http_get_json，維持
backend.company.quant_tools.data._http_get_json 的 monkeypatch 相容。
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..constants import STRATEGY_NAMES, SYMBOL_ALIASES
from ..data import normalize_symbol
from .compare import market_benchmark, market_compare, market_returns
from .eastmoney import (
    market_capital_flow,
    market_dragon_tiger,
    market_flow,
    market_north_flow,
    market_sectors,
)
from .screener import market_fundamentals, market_screener, market_search
from .watch import market_watch

__all__ = [
    "STRATEGY_NAMES",
    "SYMBOL_ALIASES",
    "Any",
    "market_benchmark",
    "market_capital_flow",
    "market_compare",
    "market_dragon_tiger",
    "market_flow",
    "market_fundamentals",
    "market_north_flow",
    "market_returns",
    "market_screener",
    "market_search",
    "market_sectors",
    "market_watch",
    "math",
    "normalize_symbol",
    "re",
]
