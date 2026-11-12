"""測試 patch 相容層：呼叫當下才解析回 backend.core.nodes 套件層屬性。

重構前 nodes 是單一模組，測試以 patch(backend.core.nodes.<name>, fake) 替換模組屬性；
呼叫端在同模組 global 查找，因此立即生效。拆套件後子模組若直接 from .x import <name>
會綁定原始物件，patch 套件層屬性不會影響。因此 call_llm／_memory_store 一律經本模組，
於呼叫／取值當下解析回套件層屬性。
"""

from __future__ import annotations

from typing import Any


def _target() -> Any:
    """回傳 backend.core.nodes 套件模組（呼叫當下才匯入，避免循環）。"""
    from backend.core import nodes as _package

    return _package


def call_llm(*args: Any, **kwargs: Any) -> Any:
    """延遲解析 call_llm：永遠走套件層屬性（可被測試 patch）。"""
    return _target().call_llm(*args, **kwargs)


def get_memory_store() -> Any:
    """延遲解析 _memory_store：永遠走套件層屬性（測試可整顆 patch）。"""
    return _target()._memory_store
