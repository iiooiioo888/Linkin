"""Docker 管理服務：容器控制（寫操作）與允許服務清單。"""

from __future__ import annotations

import logging
from typing import Any

from .errors import NotFound
from .format_mixin import DockerFormatMixin
from .metrics import _audit_log

logger = logging.getLogger("backend.services.docker_manager")


class DockerControlMixin(DockerFormatMixin):
    """容器控制（重啟／停止／啟動）與允許服務檢查（寫操作）。"""

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
            containers = self._client.containers.list()
            return [self._extract_service(c.name) for c in containers]
        except Exception:
            return []
