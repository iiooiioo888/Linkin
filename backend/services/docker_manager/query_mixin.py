"""Docker 管理服務：容器查詢、資源統計與健康檢查。"""

from __future__ import annotations

import logging
import platform
import shutil
import time
from typing import Any

from .errors import NotFound
from .format_mixin import DockerFormatMixin
from .metrics import _NET_SAMPLE_SEC, _network_rates, _nic_totals

logger = logging.getLogger("backend.services.docker_manager")


class DockerQueryMixin(DockerFormatMixin):
    """容器查詢、資源統計與健康檢查（唯讀操作）。"""

    # ═══════════════════════════════════════════════════════════
    # 容器查詢
    # ═══════════════════════════════════════════════════════════

    def list_containers(self) -> list[dict[str, Any]]:
        """列出所有 evoloop 項目容器及其狀態。

        Returns:
            容器列表，每項包含 name, status, image, ports, health, uptime
        """
        if not self.available:
            return self._stub_list_containers()

        try:
            containers = self._client.containers.list(all=True)
        except Exception as exc:
            logger.error("查詢容器列表失敗：%s", exc)
            return []

        result = []
        for c in containers:
            name = c.name
            # 檢查健康狀態
            health = "unknown"
            if c.attrs.get("State", {}).get("Health"):
                health = c.attrs["State"]["Health"]["Status"]

            result.append({
                "name": name,
                "status": c.status,
                "image": ", ".join(c.image.tags) if c.image.tags else c.image.short_id,
                "ports": self._format_ports(c.ports),
                "health": health,
                "uptime": c.attrs.get("State", {}).get("StartedAt", ""),
                "uptime_seconds": self._calc_uptime_seconds(
                    c.attrs.get("State", {}).get("StartedAt", "")
                ),
                "service": self._extract_service(name),
            })

        return result

    def get_container_logs(self, service: str, tail: int = 100) -> str:
        """獲取指定服務的最近日誌。

        Args:
            service: 服務名稱（如 backend, frontend, opc, redis）
            tail: 返回最近 N 行日誌

        Returns:
            日誌文字內容，若服務不存在則回傳錯誤訊息
        """
        if not self.available:
            return "[Docker 不可用] 無法讀取日誌"

        container_name = f"{self._project}-{service}-1"
        # 也嘗試不帶 -1 後綴的名稱
        alt_name = f"{self._project}-{service}"

        container = None
        for name in (container_name, alt_name):
            try:
                container = self._client.containers.get(name)
                break
            except NotFound:
                continue
            except Exception as exc:
                logger.warning("查詢容器 %s 失敗：%s", name, exc)

        if container is None:
            return f"找不到服務 '{service}' 的容器"

        try:
            logs = container.logs(tail=tail, timestamps=True)
            return logs.decode("utf-8", errors="replace")
        except Exception as exc:
            error_msg = f"讀取 {service} 日誌失敗：{exc}"
            logger.error(error_msg)
            return error_msg

    def get_stats(self) -> dict[str, Any]:
        """獲取所有容器的資源使用統計。

        Returns:
            {service_name: {cpu_percent, memory_usage, memory_limit, network_rx, network_tx}}
        """
        if not self.available:
            return {}

        stats = {}
        try:
            containers = self._client.containers.list()
        except Exception as exc:
            logger.error("查詢資源統計失敗：%s", exc)
            return {}

        for c in containers:
            service = self._extract_service(c.name)
            try:
                raw = c.stats(stream=False)
                cpu = self._calc_cpu_percent(raw)
                mem = raw.get("memory_stats", {})
                net = raw.get("networks", {})

                rx = 0
                tx = 0
                for iface in net.values():
                    rx += iface.get("rx_bytes", 0)
                    tx += iface.get("tx_bytes", 0)

                stats[service] = {
                    "cpu_percent": round(cpu, 2),
                    "memory_usage": mem.get("usage", 0),
                    "memory_limit": mem.get("limit", 0),
                    "network_rx": rx,
                    "network_tx": tx,
                }
            except Exception as exc:
                logger.debug("獲取容器 %s 統計失敗：%s", c.name, exc)
                stats[service] = {"error": str(exc)}

        return stats

    def host_stats(self) -> dict[str, Any]:
        """主機資源總覽（psutil）：CPU / 記憶體 / 磁碟 / 網路吞吐 / swap / load。

        Returns:
            {available, hostname, cpu_percent, cpu_count, mem_*, disk_*,
             net_*, swap_*, load, uptime_seconds}；psutil 缺失或採集失敗時 available=False
        """
        try:
            import psutil
        except ImportError:
            return {"available": False, "error": "psutil 未安裝"}
        try:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            disk = shutil.disk_usage("/")
            try:
                load = [round(v, 2) for v in psutil.getloadavg()]
            except OSError:
                load = []
            net_before = _nic_totals(psutil)
            cpu_percent = round(psutil.cpu_percent(interval=_NET_SAMPLE_SEC), 1)
            net = _network_rates(net_before, psutil, sample_sec=_NET_SAMPLE_SEC)
            return {
                "available": True,
                "hostname": platform.node(),
                "cpu_percent": cpu_percent,
                "cpu_count": psutil.cpu_count(),
                "mem_total": mem.total,
                "mem_used": mem.used,
                "mem_available": mem.available,
                "mem_percent": round(mem.percent, 1),
                "disk_total": disk.total,
                "disk_used": disk.used,
                "disk_free": disk.free,
                "disk_percent": round(disk.used / max(disk.total, 1) * 100.0, 1),
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_percent": round(swap.percent, 1),
                "load": load,
                "uptime_seconds": int(max(0.0, time.time() - psutil.boot_time())),
                **net,
            }
        except Exception as exc:  # pragma: no cover — 採集失敗降級
            logger.warning("主機資源採集失敗：%s", exc)
            return {"available": False, "error": str(exc)}

    def health_check(self) -> dict[str, Any]:
        """檢查所有服務的健康狀態。

        Returns:
            {service_name: {healthy: bool, status: str, details: str}}
        """
        if not self.available:
            return {"_error": "Docker 不可用"}

        containers = self.list_containers()
        result: dict[str, Any] = {
            "all_healthy": True,
            "services": {},
        }

        for c in containers:
            service = c.get("service", c["name"])
            is_healthy = c["health"] == "healthy" or (
                c["health"] == "unknown" and "Up" in c["status"]
            )
            if not is_healthy:
                result["all_healthy"] = False

            result["services"][service] = {
                "healthy": is_healthy,
                "status": c["status"],
                "health_detail": c["health"],
            }

        return result
