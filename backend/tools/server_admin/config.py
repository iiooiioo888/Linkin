"""ServerAdmin 設定與常數（自 backend.tools.server_admin 抽出）。

ServerAdminError／ServerAdminConfig／環境變數載入與白名單／上限／危險模式常數。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── 默认值与常量 ──
DEFAULT_STORAGE_ROOT = "/data/mmorpg"


DEFAULT_SERVICES = ("linkin-api", "mysql", "redis-server", "nginx")


MAX_DELETE_PER_CALL = 5000          # 单次清理删除文件数上限（防误删爆炸）


MAX_BACKUP_BYTES = 2 * 1024**3      # 单次备份字节上限（2 GiB）


MAX_LOG_BYTES = 64 * 1024**2        # 单日志轮转上限（64 MiB）


MAX_SCAN_FILES = 20_000             # 磁盘增长分析扫描文件数上限


SUBPROCESS_TIMEOUT = 60             # systemd 调用超时（秒）


LOG_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")


_TRUE = {"1", "true", "yes", "on", "y"}


# 服务名：仅允许 systemd 单元名的安全字符
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")


# 危险模式兜底：即便我们不接受自由 shell，也对所有字符串参数做一层防御
DANGEROUS_RE = re.compile(
    r"("
    r"rm\s+-[rf]{1,2}\s+/(\s|$)|rm\s+-rf\s+\*|mkfs(\.|\s)|dd\s+if=|:\(\)\s*\{|"
    r">\s*/dev/[sh]d|chmod\s+-R\s+0?777\s+/|chown\s+-R\s+.*\s+/(\s|$)|"
    r"shutdown|reboot|halt\b|poweroff|init\s+0|init\s+6|"
    r"format\s+[a-z]:|del\s+/[sfq]|rmdir\s+/s"
    r")",
    re.IGNORECASE,
)


class ServerAdminError(ValueError):
    """运维工具参数或安全护栏校验失败。"""

    def __init__(self, message: str, *, code: str = "invalid", extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


@dataclass
class ServerAdminConfig:
    enabled: bool = False
    storage_root: Path = field(default_factory=lambda: Path(DEFAULT_STORAGE_ROOT))
    backup_dir: Path = field(default_factory=lambda: Path(DEFAULT_STORAGE_ROOT) / "backups")
    audit_path: Path = field(default_factory=lambda: Path("backend/data/linkin/server_audit.jsonl"))
    allow_services: tuple[str, ...] = DEFAULT_SERVICES

    @property
    def dry_run(self) -> bool:
        """未显式启用即视为乾跑（只模拟，不落盘）——与 Minecraft MCP 一致。"""
        return not self.enabled


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def load_config() -> ServerAdminConfig:
    """每次读取环境变量（测试用 monkeypatch.setenv 即时生效）。"""
    enabled = _env_bool("EVOL_SA_ENABLED", False)
    root_raw = os.getenv("EVOL_SA_STORAGE_ROOT", "").strip() or DEFAULT_STORAGE_ROOT
    storage_root = Path(root_raw).expanduser()
    backup_raw = os.getenv("EVOL_SA_BACKUP_DIR", "").strip()
    backup_dir = Path(backup_raw).expanduser() if backup_raw else storage_root / "backups"
    audit_raw = os.getenv("EVOL_SA_AUDIT_PATH", "").strip()
    audit_path = (
        Path(audit_raw).expanduser()
        if audit_raw
        else Path("backend/data/linkin/server_audit.jsonl")
    )
    services_raw = os.getenv("EVOL_SA_SERVICES", "").strip()
    allow_services = (
        tuple(s.strip() for s in services_raw.split(",") if s.strip())
        if services_raw
        else DEFAULT_SERVICES
    )
    return ServerAdminConfig(
        enabled=enabled,
        storage_root=storage_root,
        backup_dir=backup_dir,
        audit_path=audit_path,
        allow_services=allow_services,
    )
