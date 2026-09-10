"""Docker 容器管理服務。

封裝 Docker SDK 操作，供公司編排器調用，實現對整個容器化部署的
完整控制權：查詢狀態、讀取日誌、重啟服務、資源監控、健康檢查。

所有操作均帶有安全檢查：
- 僅允許操作 evoloop 項目容器（透過 COMPOSE_PROJECT 標籤過濾）
- 寫操作（重啟）記錄審計日誌
- Docker socket 不可用時優雅降級
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Docker SDK 為可選依賴：容器環境外（如本機開發）優雅降級
try:
    import docker
    from docker.errors import NotFound
    DOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover — 可選依賴
    DOCKER_AVAILABLE = False
    logger.info("docker SDK 未安裝，DockerManager 將以 stub 模式運行")


# ── 審計日誌 ──
def _audit_log(operation: str, detail: dict[str, Any]) -> None:
    """寫入 Docker 操作審計日誌（追加到 audit_logs 目錄）。"""
    try:
        import json
        from pathlib import Path

        log_dir = Path(
            os.getenv("DOCKER_AUDIT_LOG_DIR", Path(__file__).resolve().parents[2] / "opc_service" / "audit_logs")
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


class DockerManager:
    """Docker 容器管理服務。

    供公司編排器調用，實現對容器化部署的查詢、監控與控制。
    在 Docker SDK 不可用時自動降級為 stub 模式（回傳空結果）。
    """

    def __init__(self, project: str | None = None) -> None:
        """初始化 Docker 客戶端。

        Args:
            project: Compose 項目名稱，用於過濾容器（預設從環境變數讀取）
        """
        self._project = project or os.getenv("DOCKER_COMPOSE_PROJECT", "evoloop")
        self._client: Any = None
        self._available = DOCKER_AVAILABLE

        if self._available:
            try:
                self._client = docker.from_env()
                # 快速驗證連線
                self._client.ping()
                logger.info("Docker 連線成功（project=%s）", self._project)
            except Exception as exc:
                logger.warning("Docker 連線失敗，降級為 stub 模式：%s", exc)
                self._available = False
                self._client = None

    @property
    def available(self) -> bool:
        """Docker 是否可用。"""
        return self._available and self._client is not None

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
            containers = self._client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={self._project}"},
            )
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
            containers = self._client.containers.list(
                filters={"label": f"com.docker.compose.project={self._project}"},
            )
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

    # ═══════════════════════════════════════════════════════════
    # 容器控制（寫操作）
    # ═══════════════════════════════════════════════════════════

    def restart_service(self, service: str) -> dict[str, Any]:
        """重啟指定服務。

        此為寫操作，會記錄審計日誌。

        Args:
            service: 服務名稱

        Returns:
            {success: bool, service: str, message: str}
        """
        if not self.available:
            return {"success": False, "service": service, "message": "Docker 不可用"}

        # 安全檢查：僅允許 evoloop 項目內的服務
        allowed = self._get_allowed_services()
        if service not in allowed:
            msg = f"服務 '{service}' 不在允許列表中（{allowed}）"
            logger.warning(msg)
            _audit_log("restart_blocked", {"service": service, "reason": "不在允許列表"})
            return {"success": False, "service": service, "message": msg}

        container_name = f"{self._project}-{service}-1"
        try:
            container = self._client.containers.get(container_name)
            container.restart()
            _audit_log("restart_success", {"service": service, "container": container_name})
            logger.info("服務 %s 已重啟", service)
            return {"success": True, "service": service, "message": f"服務 {service} 已重啟"}
        except NotFound:
            msg = f"容器 {container_name} 不存在"
            _audit_log("restart_failed", {"service": service, "reason": "容器不存在"})
            return {"success": False, "service": service, "message": msg}
        except Exception as exc:
            msg = f"重啟 {service} 失敗：{exc}"
            logger.error(msg)
            _audit_log("restart_failed", {"service": service, "error": str(exc)})
            return {"success": False, "service": service, "message": msg}

    def stop_service(self, service: str) -> dict[str, Any]:
        """停止指定服務。

        Args:
            service: 服務名稱

        Returns:
            {success: bool, service: str, message: str}
        """
        if not self.available:
            return {"success": False, "service": service, "message": "Docker 不可用"}

        allowed = self._get_allowed_services()
        if service not in allowed:
            msg = f"服務 '{service}' 不在允許列表中"
            _audit_log("stop_blocked", {"service": service, "reason": "不在允許列表"})
            return {"success": False, "service": service, "message": msg}

        container_name = f"{self._project}-{service}-1"
        try:
            container = self._client.containers.get(container_name)
            container.stop()
            _audit_log("stop_success", {"service": service, "container": container_name})
            logger.info("服務 %s 已停止", service)
            return {"success": True, "service": service, "message": f"服務 {service} 已停止"}
        except NotFound:
            return {"success": False, "service": service, "message": f"容器 {container_name} 不存在"}
        except Exception as exc:
            return {"success": False, "service": service, "message": str(exc)}

    def start_service(self, service: str) -> dict[str, Any]:
        """啟動指定服務。

        Args:
            service: 服務名稱

        Returns:
            {success: bool, service: str, message: str}
        """
        if not self.available:
            return {"success": False, "service": service, "message": "Docker 不可用"}

        allowed = self._get_allowed_services()
        if service not in allowed:
            return {"success": False, "service": service, "message": f"服務 '{service}' 不在允許列表中"}

        container_name = f"{self._project}-{service}-1"
        try:
            container = self._client.containers.get(container_name)
            container.start()
            _audit_log("start_success", {"service": service, "container": container_name})
            return {"success": True, "service": service, "message": f"服務 {service} 已啟動"}
        except NotFound:
            return {"success": False, "service": service, "message": f"容器 {container_name} 不存在"}
        except Exception as exc:
            return {"success": False, "service": service, "message": str(exc)}

    # ═══════════════════════════════════════════════════════════
    # 輔助方法
    # ═══════════════════════════════════════════════════════════

    def _get_allowed_services(self) -> list[str]:
        """獲取允許操作的服務列表（從運行中的容器動態獲取）。"""
        if not self.available:
            return []
        try:
            containers = self._client.containers.list(
                filters={"label": f"com.docker.compose.project={self._project}"},
            )
            return [self._extract_service(c.name) for c in containers]
        except Exception:
            return []

    def _extract_service(self, container_name: str) -> str:
        """從容器名稱提取服務名。

        例如: evoloop-backend-1 → backend
              evoloop-frontend-1 → frontend
        """
        # 移除項目前綴和副本編號後綴
        prefix = f"{self._project}-"
        name = container_name
        name = name.removeprefix(prefix)
        # 移除 -N 後綴（副本編號）
        parts = name.rsplit("-", 1)
        if len(parts) == 2 and parts[1].isdigit():
            return parts[0]
        return name

    @staticmethod
    def _calc_cpu_percent(stats: dict) -> float:
        """計算 CPU 使用百分比。"""
        cpu_delta = stats.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
        system_delta = stats.get("cpu_stats", {}).get("system_cpu_usage", 0)
        precpu_delta = stats.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
        presystem_delta = stats.get("precpu_stats", {}).get("system_cpu_usage", 0)

        if system_delta == 0 or presystem_delta == 0 or system_delta == presystem_delta:
            return 0.0

        cpu_usage = cpu_delta - precpu_delta
        system_usage = system_delta - presystem_delta
        num_cpus = stats.get("cpu_stats", {}).get("online_cpus", 1)

        if system_usage <= 0 or num_cpus <= 0:
            return 0.0

        return (cpu_usage / system_usage) * num_cpus * 100.0

    @staticmethod
    def _format_ports(ports: list[dict]) -> list[str]:
        """格式化端口列表為可讀字串。"""
        if not ports:
            return []
        formatted = []
        for p in ports:
            if p.get("PublicPort"):
                formatted.append(f"{p['PublicPort']}:{p['PrivatePort']}/{p.get('Type', 'tcp')}")
            elif "PrivatePort" in p:
                formatted.append(f"{p['PrivatePort']}/{p.get('Type', 'tcp')}")
        return formatted

    def _stub_list_containers(self) -> list[dict[str, Any]]:
        """Stub 模式：回傳空列表並附帶不可用標記。"""
        return [{
            "name": "_docker_unavailable",
            "status": "Docker SDK 不可用",
            "image": "",
            "ports": [],
            "health": "unknown",
            "uptime": "",
            "uptime_seconds": 0,
            "service": "_docker_unavailable",
        }]

    @staticmethod
    def _calc_uptime_seconds(started_at: str) -> float:
        """從 Docker StartedAt 時間戳計算已運行秒數。

        Docker 返回的 StartedAt 格式如 "2024-01-01T00:00:00.000000000Z"
        """
        if not started_at:
            return 0.0
        try:
            # 嘗試解析 ISO 8601 格式
            ts = started_at.replace("Z", "+00:00")
            started = datetime.fromisoformat(ts)
            now = datetime.now(timezone.utc)
            return (now - started).total_seconds()
        except (ValueError, TypeError):
            return 0.0


# ── 模組級單例（供公司編排器與 API 端點共享）──
_docker_manager: DockerManager | None = None


def get_docker_manager() -> DockerManager:
    """獲取 DockerManager 單例。"""
    global _docker_manager
    if _docker_manager is None:
        _docker_manager = DockerManager()
    return _docker_manager