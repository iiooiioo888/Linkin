"""Cloud adapter 介面 stub。"""

from __future__ import annotations

from typing import Any, Protocol


class CloudAdapterError(RuntimeError):
    pass


class CloudAdapter(Protocol):
    name: str

    def submit(self, job: dict[str, Any]) -> dict[str, Any]:
        """提交 cloud_allowed 任務；MVP 不呼叫。"""
        ...
