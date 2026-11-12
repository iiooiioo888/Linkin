"""call_llm 的間接層：讓測試 monkeypatch backend.hub.service.call_llm 在子模組生效。

套件 facade（__init__.py）保留 from backend.core.llm import call_llm 作為 patch 表面；
probe／complete 經此函式在呼叫時才解析套件層 call_llm，既有 2 處測試 patch 不需修改。
"""

from __future__ import annotations

from typing import Any


def call_llm(*args: Any, **kwargs: Any) -> Any:
    from backend.hub import service as _package

    return _package.call_llm(*args, **kwargs)
