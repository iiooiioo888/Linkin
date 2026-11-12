"""Docker 容器管理服務。

封裝 Docker SDK 操作，供公司編排器調用，實現對整個容器化部署的
完整控制權：查詢狀態、讀取日誌、重啟服務、資源監控、健康檢查。

所有操作均帶有安全檢查：
- 監控層列出本機全部容器（跨 compose project）；寫操作以運行中容器為準
- 寫操作（重啟）記錄審計日誌
- Docker socket 不可用時優雅降級

第十三輪重構：實作已拆至本套件子模組；此 __init__ 保留原模組層公開名稱
（DockerManager／get_docker_manager／DOCKER_AVAILABLE／docker／NotFound 等）
與 get_docker_manager 單例，既有 import 路徑不變。
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import time
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .errors import NotFound
from .manager import DockerManager

logger = logging.getLogger(__name__)

# Docker SDK 為可選依賴：容器環境外（如本機開發）優雅降級
try:
    import docker
    DOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover — 可選依賴
    DOCKER_AVAILABLE = False
    logger.info("docker SDK 未安裝，DockerManager 將以 stub 模式運行")

# ── 模組級單例（供公司編排器與 API 端點共享）──
_docker_manager: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    """獲取 DockerManager 單例。"""
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager


# 保留原 docker_manager.py 的模組層公開名稱基線（dir() 非底線）：
# 既有程式碼只 import DockerManager／get_docker_manager；其餘為原模組
# import 副作用留下的名稱，這裡一併列出以維持 re-export 相容。
__all__ = [
    "DOCKER_AVAILABLE",
    "Any",
    "DockerManager",
    "Mapping",
    "NotFound",
    "datetime",
    "docker",
    "get_docker_manager",
    "logger",
    "logging",
    "os",
    "platform",
    "shutil",
    "time",
    "timezone",
]
