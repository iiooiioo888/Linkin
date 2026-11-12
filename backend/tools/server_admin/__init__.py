"""服务器运维底层桥接：psutil / docker / systemd / 文件系统的安全封装。

设计遵循 Minecraft MCP 同款双层护栏哲学（AGENTS.md 铁律 #5）：

- **读操作**（磁盘/CPU/内存/Docker/systemd 状态）永远安全执行、跨平台降级
- **写操作**（清理/重启/轮转/备份）需 ``confirm``，且 ``dry_run`` 时只模拟不落盘
- **路径牢笼**：所有文件操作必须落在 ``STORAGE_ROOT`` 允许清单内（防路径穿越）
- **服务允许清单**：只能操作白名单内的 systemd 服务（防重启任意服务）
- **危险模式兜底**：任何字符串参数命中 ``rm -rf /`` 等一律拒绝（defense-in-depth）
- **审计**：所有写操作（含模拟）写入 JSONL 审计日志

配置经环境变量，``load_config()`` 每次读取（与 minecraft_mcp 一致）：
    EVOL_SA_ENABLED        默认 false → dry_run（只模拟，不落盘）
    EVOL_SA_STORAGE_ROOT   默认 /data/mmorpg（Windows 回退到工作区）
    EVOL_SA_BACKUP_DIR     默认 STORAGE_ROOT/backups
    EVOL_SA_AUDIT_PATH     默认 backend/data/linkin/server_audit.jsonl
    EVOL_SA_SERVICES       逗号分隔允许清单（默认 linkin-api,mysql,redis-server,nginx）

**绝不接受自由 shell 命令**——只暴露具名工具，参数强类型校验。

本檔案已於第九輪重構拆為套件：對外仍以
from backend.tools.server_admin import load_config, ServerAdminConfig 等名稱匯入；
實作分散在 config／guards／system／operations 等模組，內容與行為逐字不變。
"""

from __future__ import annotations

# 以下名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import fnmatch  # noqa: F401
import gzip  # noqa: F401
import json  # noqa: F401
import logging
import os  # noqa: F401
import re  # noqa: F401
import shutil  # noqa: F401
import subprocess  # noqa: F401
import time  # noqa: F401
from collections.abc import Iterable  # noqa: F401
from dataclasses import dataclass, field  # noqa: F401
from pathlib import Path, PurePosixPath  # noqa: F401
from typing import Any  # noqa: F401

# 舊模組私有 helper：外部與測試會直接取用，保留 re-export
from .config import (  # noqa: F401  # noqa: F401
    _TRUE,
    DANGEROUS_RE,
    DEFAULT_SERVICES,
    DEFAULT_STORAGE_ROOT,
    LOG_NAME_RE,
    MAX_BACKUP_BYTES,
    MAX_DELETE_PER_CALL,
    MAX_LOG_BYTES,
    MAX_SCAN_FILES,
    SERVICE_NAME_RE,
    SUBPROCESS_TIMEOUT,
    ServerAdminConfig,
    ServerAdminError,
    _env_bool,
    load_config,
)
from .guards import (  # noqa: F401
    _append_audit,
    _check_service,
    _guard_dangerous,
    _human_bytes,
    _resolve_under_root,
    _scan_old_files,
)
from .operations import (  # noqa: F401
    ALL_TOOLS,
    READONLY_TOOLS,
    WRITE_TOOLS,
    _pending,
    backup_incremental,
    clean_old_packages,
    clean_temp_files,
    execute_named_tool,
    restart_service,
    rotate_logs,
)
from .system import (  # noqa: F401
    analyze_disk_growth,
    check_service,
    get_disk_usage,
    get_docker_status,
    get_memory_usage,
    get_system_load,
    psutil,
    tail_log,
)

logger = logging.getLogger(__name__)

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in (
    "config", "guards", "operations", "system"
):
    globals().pop(_submodule, None)
del _submodule
