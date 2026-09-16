"""臨時容器執行：功能開關、映像白名單與硬上限。"""

from __future__ import annotations

import os

LABEL_TASK_ID = "linkin.ephemeral.task_id"
LABEL_MANAGED = "linkin.ephemeral.managed"

DEFAULT_ALLOWLIST = (
    "python:3.12-slim",
    "node:20-slim",
    "alpine:3.20",
)

REDIS_KEY_PREFIX = "evoloop:ectask:"
TASK_TTL_SECONDS = 7 * 86400
MAX_LOG_CHARS = 512_000
MAX_LOG_LINES_STORED = 8000


def ephemeral_containers_enabled() -> bool:
    return os.getenv("EVOL_EPHEMERAL_CONTAINERS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def image_allowlist() -> frozenset[str]:
    raw = os.getenv("EVOL_EPHEMERAL_IMAGE_ALLOWLIST", "").strip()
    if raw:
        return frozenset(i.strip() for i in raw.split(",") if i.strip())
    return frozenset(DEFAULT_ALLOWLIST)


def max_timeout_sec() -> int:
    return max(30, int(os.getenv("EVOL_EPHEMERAL_MAX_TIMEOUT_SEC", "600")))


def default_timeout_sec() -> int:
    return min(120, max_timeout_sec())


def max_memory_mb() -> int:
    return max(32, int(os.getenv("EVOL_EPHEMERAL_MAX_MEMORY_MB", "512")))


def max_cpu() -> float:
    return max(0.1, float(os.getenv("EVOL_EPHEMERAL_MAX_CPU", "2.0")))


def max_pids() -> int:
    return max(64, int(os.getenv("EVOL_EPHEMERAL_MAX_PIDS", "256")))


def artifacts_dir() -> str:
    return os.getenv(
        "EVOL_EPHEMERAL_ARTIFACTS_DIR",
        os.path.join(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin"), "ephemeral_artifacts"),
    )
