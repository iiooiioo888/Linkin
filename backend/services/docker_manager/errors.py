"""Docker SDK 例外：SDK 未安裝時以佔位類別維持可 import。"""

from __future__ import annotations

try:
    from docker.errors import NotFound
except ImportError:  # pragma: no cover — 可選依賴

    class _NotFoundStub(Exception):
        """Docker SDK 未安裝時的替代例外（stub 模式不會拋出）。"""

    NotFound = _NotFoundStub

__all__ = ["NotFound"]
