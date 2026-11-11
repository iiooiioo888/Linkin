"""測試 patch 相容層：呼叫時解析套件層 call_llm（backend.company.decomposer.call_llm）。

套件化後實作搬到 service.py，但既有測試以 patch("backend.company.decomposer.call_llm")
替換套件層屬性；此包裝函式每次呼叫都重新讀取套件屬性，維持原本 patch 語意。
"""

from __future__ import annotations

from typing import Any


def call_llm(*args: Any, **kwargs: Any) -> Any:
    """轉呼叫套件層 call_llm（可能已被 monkeypatch 替換）。"""
    from backend.company import decomposer as _pkg

    return _pkg.call_llm(*args, **kwargs)
