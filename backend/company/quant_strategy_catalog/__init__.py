"""stock-quant 策略庫目錄 — 分類／搜尋給角色引用。

對齊 https://github.com/iiooiioo888/stock-quant 的 strategies/strategy_library.py
與 src/core/strategies/ 引擎。不引入 backtrader。

- wired：本倉庫可交給 market_backtest 實際回測（31 種引擎 + 目錄別名）
- catalog：目錄項，角色可查閱；尚未接通引擎時不可回測

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- data：分類表、別名表與引擎列
- rows：STRATEGY_LIBRARY 大型目錄列
- queries：目錄查詢與 market_strategy_catalog
"""

from __future__ import annotations

from typing import Any

from .data import CATALOG_CATEGORIES, ENGINE_ALIASES
from .queries import market_strategy_catalog, resolve_strategy

__all__ = [
    "CATALOG_CATEGORIES",
    "ENGINE_ALIASES",
    "Any",
    "annotations",
    "market_strategy_catalog",
    "resolve_strategy",
]
