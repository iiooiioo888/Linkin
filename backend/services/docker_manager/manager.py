"""Docker 管理服務：DockerManager 本體（mixin 組合）。"""

from __future__ import annotations

import logging
import os
from typing import Any

from .control_mixin import DockerControlMixin
from .query_mixin import DockerQueryMixin

logger = logging.getLogger("backend.services.docker_manager")


def _runtime() -> Any:
    """延遲取得套件模組，讓測試 monkeypatch 的 DOCKER_AVAILABLE／docker 即時生效。"""
    from backend.services import docker_manager

    return docker_manager


class DockerManager(DockerQueryMixin, DockerControlMixin):
    """Docker 容器管理服務。

    供公司編排器調用，實現對容器化部署的查詢、監控與控制。
    在 Docker SDK 不可用時自動降級為 stub 模式（回傳空結果）。
    """

    def __init__(self, project: str | None = None) -> None:
        """初始化 Docker 客戶端。

        Args:
            project: Compose 項目名稱，用於過濾容器（預設從環境變數讀取）
        """
        self._project = project or os.environ.get("DOCKER_COMPOSE_PROJECT", "evoloop")
        self._client: Any = None
        runtime = _runtime()
        self._available = bool(runtime.DOCKER_AVAILABLE)

        if self._available:
            try:
                self._client = runtime.docker.from_env()
                # 快速驗證連線
                self._client.ping()
                logger.info("Docker 連線成功（project=%s）", self._project)
            except Exception as exc:
                logger.warning("Docker 連線失敗，降級為 stub 模式：%s", exc)
                self._available = False
                self._client = None
