"""延遲解析 data 套件層屬性，維持既有 monkeypatch 語意。

測試以 monkeypatch.setattr("backend.company.quant_tools.data._http_get_json", fake)
替換套件層屬性；子模組一律經此 helper 取值，確保所有呼叫端都吃到 fake
（同 provider_pool.catalog 模式）。
"""

from __future__ import annotations

import sys
from typing import Any


def resolve(name: str) -> Any:
    """取 data 套件層屬性（呼叫時才解析，支援 monkeypatch）。"""
    return getattr(sys.modules[__package__], name)


def http_get_json(*args: Any, **kwargs: Any) -> Any:
    """轉呼叫套件層 _http_get_json（保留原呼叫 arity）。"""
    return resolve("_http_get_json")(*args, **kwargs)


def http_get_text(*args: Any, **kwargs: Any) -> str:
    """轉呼叫套件層 _http_get_text（保留原呼叫 arity）。"""
    return resolve("_http_get_text")(*args, **kwargs)
