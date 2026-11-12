"""雲控制台核心服務。

提供四大模組：
- CloudBilling: 費用計算（本地 Docker 按時計費 + 阿里雲 BSS 帳目）
- CloudMonitor: 資源監控（定期輪詢 Docker stats，內存存儲最近 24h）
- CloudAlerts: 告警系統（CPU/內存閾值規則，JSON 文件持久化）
- CloudEvents: 容器事件（操作時間線記錄）

所有服務透過 DockerManager 獲取底層數據，Docker 不可用時優雅降級。

套件化：本模組已拆為 backend/services/cloud_console/ 套件，公開 import 路徑不變。
billing／monitor／alerts／events／singletons 各自持有領域內容；common 提供共用 logger。
既有 lazy import（agent_monitor、monitor_hub、budget manager）以套件層 get_cloud_* 取得，對 backend.services.cloud_console.get_cloud_billing 的 monkeypatch 語意不變。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.company.docker_tools import get_service_hourly_rate
from backend.services.aliyun_bss import get_aliyun_bss
from backend.services.docker_manager import DockerManager, get_docker_manager

from .alerts import CloudAlerts
from .billing import CloudBilling
from .common import logger
from .events import CloudEvents
from .monitor import CloudMonitor
from .singletons import (
    get_cloud_alerts,
    get_cloud_billing,
    get_cloud_events,
    get_cloud_monitor,
)

__all__ = [
    "Any",
    "CloudAlerts",
    "CloudBilling",
    "CloudEvents",
    "CloudMonitor",
    "DockerManager",
    "Path",
    "datetime",
    "get_aliyun_bss",
    "get_cloud_alerts",
    "get_cloud_billing",
    "get_cloud_events",
    "get_cloud_monitor",
    "get_docker_manager",
    "get_service_hourly_rate",
    "json",
    "logger",
    "logging",
    "os",
    "threading",
    "time",
    "timezone",
    "uuid",
]


# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.services.cloud_console) 的公開名稱與原模組一致（24 個）。
for _submodule in (
    "alerts",
    "billing",
    "common",
    "events",
    "monitor",
    "singletons",
):
    globals().pop(_submodule, None)
del _submodule
