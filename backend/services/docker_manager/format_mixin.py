"""Docker 管理服務：容器名稱、連接埠、CPU 與運行時間格式化 helpers。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from .base import DockerManagerBase


class DockerFormatMixin(DockerManagerBase):
    """格式化 helpers：容器名稱／連接埠／CPU／運行時間。"""

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
    def normalize_docker_ports(ports: Any) -> list[str]:
        """將 docker-py 端口結構（dict 或 list）統一為可讀字串列表。"""
        if not ports:
            return []
        if isinstance(ports, Mapping):
            return DockerFormatMixin._format_ports_dict(ports)
        if isinstance(ports, list):
            return DockerFormatMixin._format_ports_list(ports)
        return []

    @staticmethod
    def _format_ports(ports: Any) -> list[str]:
        """格式化端口為可讀字串（相容 docker-py ``Container.ports`` dict 與 API list）。"""
        return DockerFormatMixin.normalize_docker_ports(ports)

    @staticmethod
    def _format_ports_list(ports: list[dict]) -> list[str]:
        """``docker ps`` 風格 list：``PublicPort`` / ``PrivatePort`` / ``IP``。"""
        formatted: list[str] = []
        for p in ports:
            if not isinstance(p, dict):
                continue
            proto = p.get("Type", "tcp")
            private = p.get("PrivatePort")
            public = p.get("PublicPort")
            ip = (p.get("IP") or "").strip()
            if public and private is not None:
                if ip and ip not in ("0.0.0.0", "::"):
                    formatted.append(f"{ip}:{public}:{private}/{proto}")
                else:
                    formatted.append(f"{public}:{private}/{proto}")
            elif private is not None:
                formatted.append(f"{private}/{proto}")
        return formatted

    @staticmethod
    def _format_ports_dict(ports: Mapping[str, Any]) -> list[str]:
        """``NetworkSettings.Ports`` dict：``3000/tcp`` → host bindings。"""
        formatted: list[str] = []
        for key, bindings in ports.items():
            key_s = str(key)
            if "/" in key_s:
                private_s, proto = key_s.split("/", 1)
            else:
                private_s, proto = key_s, "tcp"
            if not bindings:
                formatted.append(f"{private_s}/{proto}")
                continue
            binding_list = bindings if isinstance(bindings, list) else [bindings]
            for binding in binding_list:
                if not isinstance(binding, dict):
                    continue
                host_ip = (binding.get("HostIp") or "").strip()
                host_port = (binding.get("HostPort") or "").strip()
                if not host_port:
                    formatted.append(f"{private_s}/{proto}")
                    continue
                if host_ip and host_ip not in ("0.0.0.0", "", "::"):
                    formatted.append(f"{host_ip}:{host_port}:{private_s}/{proto}")
                else:
                    formatted.append(f"{host_port}:{private_s}/{proto}")
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
