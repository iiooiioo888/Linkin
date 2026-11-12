"""Docker 管理服務：網路吞吐取樣與操作審計日誌 helpers。"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("backend.services.docker_manager")

# 與 CPU 取樣同一段等待，算出這段時間的網路吞吐。
_NET_SAMPLE_SEC = 0.15
# 雲主機虛擬網卡常回報 speed=0。沒有速率時用 100 Mbps 當上限，避免把「沒讀到」顯示成 0%。
_NET_ASSUMED_LINK_MBPS = 100

def _nic_totals(psutil: Any) -> tuple[int, int, int] | None:
    """非 loopback 的收發位元組與網卡速率（Mbps）。沒有計數器時回 None。"""
    reader = getattr(psutil, "net_io_counters", None)
    if reader is None:
        return None
    try:
        counters = reader(pernic=True) or {}
    except Exception:
        return None
    if_stats: Mapping[str, Any] = {}
    stats_reader = getattr(psutil, "net_if_stats", None)
    if stats_reader is not None:
        try:
            if_stats = stats_reader() or {}
        except Exception:
            if_stats = {}
    rx = tx = speed = 0
    for name, row in counters.items():
        if name == "lo" or str(name).startswith("lo"):
            continue
        rx += int(getattr(row, "bytes_recv", 0) or 0)
        tx += int(getattr(row, "bytes_sent", 0) or 0)
        st = if_stats.get(name)
        spd = int(getattr(st, "speed", 0) or 0) if st is not None else 0
        up = bool(getattr(st, "isup", True)) if st is not None else True
        if up and spd > 0:
            speed += spd
    return rx, tx, speed


def _network_rates(before: tuple[int, int, int] | None, psutil: Any, *, sample_sec: float) -> dict[str, Any]:
    empty = {
        "net_rx_bps": 0.0,
        "net_tx_bps": 0.0,
        "net_percent": None,
        "net_link_mbps": 0,
        "net_link_assumed": False,
    }
    after = _nic_totals(psutil)
    if before is None or after is None or sample_sec <= 0:
        return empty
    rx_bps = max(0.0, (after[0] - before[0]) / sample_sec)
    tx_bps = max(0.0, (after[1] - before[1]) / sample_sec)
    link = before[2] or after[2]
    assumed = link <= 0
    link_mbps = link if link > 0 else _NET_ASSUMED_LINK_MBPS
    util = (rx_bps + tx_bps) * 8 / (link_mbps * 1_000_000) * 100
    return {
        "net_rx_bps": round(rx_bps, 1),
        "net_tx_bps": round(tx_bps, 1),
        "net_percent": round(min(100.0, util), 1),
        "net_link_mbps": link_mbps,
        "net_link_assumed": assumed,
    }

# ── 審計日誌 ──
def _audit_log(operation: str, detail: dict[str, Any]) -> None:
    """寫入 Docker 操作審計日誌（追加到 audit_logs 目錄）。"""
    try:
        import json
        from pathlib import Path

        log_dir = Path(
            os.getenv("DOCKER_AUDIT_LOG_DIR", Path(__file__).resolve().parents[3] / "opc_service" / "audit_logs")
        )
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "docker_audit.jsonl"
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            **detail,
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.debug("無法寫入 Docker 審計日誌", exc_info=True)
