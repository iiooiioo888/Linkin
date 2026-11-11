"""測試相容層：維持 backend.company.orchestrator.call_llm 這個 patch 表面。

重構前 orchestrator 是單一模組，測試直接替換模組屬性 call_llm；拆分後若各 mixin
各自 from backend.core.llm import call_llm，patch 套件層屬性不會影響已綁定的參照。
因此 mixin 一律從本模組取 call_llm，呼叫時才解析回套件層的 call_llm。
"""

from __future__ import annotations

from typing import Any


def call_llm(*args: Any, **kwargs: Any) -> Any:
    """延遲解析：永遠呼叫 backend.company.orchestrator.call_llm（可被測試 patch）。"""
    from backend.company import orchestrator as _package

    return _package.call_llm(*args, **kwargs)
