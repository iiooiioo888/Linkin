"""Docker 管理服務：mixin 共用狀態與可用性判斷。"""

from __future__ import annotations

from typing import Any


class DockerManagerBase:
    """mixin 共用狀態：compose project、docker client 與可用性判斷。"""

    _project: str
    _client: Any
    _available: bool

    @property
    def available(self) -> bool:
        """Docker 是否可用。"""
        return self._available and self._client is not None
