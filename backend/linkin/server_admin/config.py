"""伺服器運維的環境變數 helper、pending 檔路徑與預設值（自 backend.linkin.server_admin 抽出）。"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("backend.linkin.server_admin")


_TRUE = {"1", "true", "yes", "on", "y"}
DEFAULT_PENDING_PATH = Path("backend/data/linkin/server_pending.json")
DEFAULT_TTL_MIN = 30
PENDING_KEEP_DAYS = 7  # 已完成記錄保留天數（防止文件膨脹）


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _env_int(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.getenv(name, "").strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, value))


def pending_path() -> Path:
    raw = os.getenv("EVOL_SA_PENDING_PATH", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PENDING_PATH
