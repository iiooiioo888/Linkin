"""CloudMonitor — 雲資源監控（自 cloud_console 抽出）。"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any

from backend.services.docker_manager import DockerManager, get_docker_manager

from .common import logger

# ═══════════════════════════════════════════════════════════════
# CloudMonitor — 資源監控
# ═══════════════════════════════════════════════════════════════


class CloudMonitor:
    """資源監控服務。

    定期輪詢 Docker stats，內存存儲最近 24 小時的歷史數據點。
    提供按時間範圍查詢的歷史數據接口。
    """

    # 數據點保留策略
    MAX_DATA_POINTS = 1440  # 24h × 60min
    POLL_INTERVAL_SECONDS = 60  # 每分鐘採集一次

    def __init__(self, docker: DockerManager | None = None) -> None:
        self._docker = docker or get_docker_manager()
        self._history: list[dict[str, Any]] = []  # [{ts, services: {svc: {cpu, mem, net}}}]
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """啟動後台監控線程。"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        logger.info("CloudMonitor 後台監控已啟動（間隔 %ds）", self.POLL_INTERVAL_SECONDS)

    def stop(self) -> None:
        """停止後台監控線程。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("CloudMonitor 後台監控已停止")

    def _poll_loop(self) -> None:
        """後台輪詢迴圈。"""
        while self._running:
            try:
                self._collect()
            except Exception:
                logger.debug("CloudMonitor 採集異常", exc_info=True)
            time.sleep(self.POLL_INTERVAL_SECONDS)

    def _collect(self) -> None:
        """採集一次資源數據。"""
        if not self._docker.available:
            return

        stats = self._docker.get_stats()
        if not stats:
            return

        point: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "services": {},
        }

        for svc, s in stats.items():
            if "error" in s:
                continue
            point["services"][svc] = {
                "cpu": s.get("cpu_percent", 0),
                "mem_mb": round(s.get("memory_usage", 0) / (1024 * 1024), 1),
                "mem_limit_mb": round(s.get("memory_limit", 0) / (1024 * 1024), 1),
                "net_rx_mb": round(s.get("network_rx", 0) / (1024 * 1024), 2),
                "net_tx_mb": round(s.get("network_tx", 0) / (1024 * 1024), 2),
            }

        with self._lock:
            self._history.append(point)
            # 保持 MAX_DATA_POINTS 上限
            if len(self._history) > self.MAX_DATA_POINTS:
                self._history = self._history[-self.MAX_DATA_POINTS:]

    def get_history(self, range_hours: float = 1.0) -> dict[str, Any]:
        """獲取指定時間範圍的監控歷史數據。

        Args:
            range_hours: 查詢範圍（小時），預設最近 1 小時

        Returns:
            {
                "points": [{ts, services: {svc: {cpu, mem_mb, net_rx_mb, net_tx_mb}}}],
                "range_hours": float,
                "latest": {svc: {...}} | None,
            }
        """
        cutoff = time.time() - range_hours * 3600

        with self._lock:
            filtered = []
            for p in self._history:
                try:
                    pt = datetime.fromisoformat(p["ts"])
                    if pt.timestamp() >= cutoff:
                        filtered.append(p)
                except (ValueError, TypeError):
                    continue

            latest = filtered[-1] if filtered else None

        return {
            "points": filtered,
            "range_hours": range_hours,
            "latest": latest,
        }

    def get_latest(self) -> dict[str, Any] | None:
        """獲取最新一次採集數據。"""
        with self._lock:
            if not self._history:
                # 若無歷史數據，立即採集一次
                self._collect()
            return self._history[-1] if self._history else None
