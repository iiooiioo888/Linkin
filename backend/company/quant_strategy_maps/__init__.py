"""stock-quant 策略庫 → Archify IR（確定性，不經 LLM）。

對齊 tt-a1i/archify 的 architecture / workflow / data-flow / lifecycle，
把策略庫總覽、分類拓撲與單策略工作流編成 typed JSON IR，前端 SVG 渲染。

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- ir：IR／節點／邊 helper、策略庫列舉與分類資料表
- overview：總覽架構／資料流／通用生命週期
- strategies：分類拓撲、單策略工作流／生命週期、預覽與 Archify 檢視
"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_catalog import (
    CATALOG_CATEGORIES,
    market_strategy_catalog,
    resolve_strategy,
)

from .ir import ARCHIFY_SOURCE, CATALOG_SOURCE, _find_item, _listing
from .overview import generic_lifecycle, overview_architecture, overview_data_flow
from .strategies import (
    archify_strategies,
    group_architecture,
    strategy_catalog_maps,
    strategy_lifecycle,
    strategy_maps,
    strategy_preview,
    strategy_workflow,
)

__all__ = [
    "ARCHIFY_SOURCE",
    "CATALOG_CATEGORIES",
    "CATALOG_SOURCE",
    "Any",
    "_find_item",
    "_listing",
    "annotations",
    "archify_strategies",
    "generic_lifecycle",
    "group_architecture",
    "market_strategy_catalog",
    "overview_architecture",
    "overview_data_flow",
    "resolve_strategy",
    "strategy_catalog_maps",
    "strategy_lifecycle",
    "strategy_maps",
    "strategy_preview",
    "strategy_workflow",
]
