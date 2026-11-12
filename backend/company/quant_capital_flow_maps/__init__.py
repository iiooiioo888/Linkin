"""量化策略資金流視覺化 — 瀑布／狀態機／時間軸（確定性，不經 LLM）。

三種維度：
1. 瀑布流向圖（桑基風格 Mermaid）— 資金當下分布
2. 循環狀態機 — 一筆資金從進場到出場的生命週期
3. 時間軸數值表 — 依回測成交序列模擬現金／持倉／權益變化

自單檔模組拆為套件，對外 import 路徑與公開名稱（dir() 非底線）不變；子模組：
- profiles：策略分類資金流參數與 profile 合併
- diagrams：瀑布流向圖與循環狀態機 Mermaid 建構
- timeline：時間軸數值表（回測成交／示範路徑）
- ir：strategy_capital_flow IR 組裝
"""

from __future__ import annotations

from typing import Any

from .ir import strategy_capital_flow

__all__ = [
    "Any",
    "annotations",
    "strategy_capital_flow",
]

# 移除子模組在套件上的屬性，維持 dir() 非底線名稱與原單檔模組一致（3 個）。
for _submodule in ("diagrams", "ir", "profiles", "timeline"):
    globals().pop(_submodule, None)
del _submodule
