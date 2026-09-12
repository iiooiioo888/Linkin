"""Docker 管理與公司 Docker 工具單元測試。

驗證：
1. DockerManager stub 模式（docker SDK 不可用時的降級行為）
2. DockerManager 方法（monkeypatch 模擬 docker SDK）
3. docker_tools 工具函數與權限檢查
4. CompanyOrchestrator Docker 整合
5. FastAPI Docker 端點
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# ═══════════════════════════════════════════════════════════════
# DockerManager stub 模式測試
# ═══════════════════════════════════════════════════════════════

class TestDockerManagerStub:
    """測試 Docker SDK 不可用時的降級行為。"""

    def test_stub_list_containers(self, monkeypatch):
        """Stub 模式應回傳不可用標記。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        assert dm.available is False

        containers = dm.list_containers()
        assert len(containers) == 1
        assert containers[0]["service"] == "_docker_unavailable"

    def test_stub_get_logs(self, monkeypatch):
        """Stub 模式讀取日誌應回傳提示。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        logs = dm.get_container_logs("backend", tail=50)
        assert "Docker 不可用" in logs

    def test_stub_get_stats(self, monkeypatch):
        """Stub 模式資源統計應回傳空字典。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        stats = dm.get_stats()
        assert stats == {}

    def test_stub_health_check(self, monkeypatch):
        """Stub 模式健康檢查應回傳錯誤。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        health = dm.health_check()
        assert "_error" in health

    def test_stub_restart_service(self, monkeypatch):
        """Stub 模式重啟應回傳失敗。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        result = dm.restart_service("backend")
        assert result["success"] is False
        assert "Docker 不可用" in result["message"]

    def test_stub_start_stop(self, monkeypatch):
        """Stub 模式啟動/停止應回傳失敗。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        assert dm.start_service("backend")["success"] is False
        assert dm.stop_service("backend")["success"] is False


# ═══════════════════════════════════════════════════════════════
# DockerManager mock 測試
# ═══════════════════════════════════════════════════════════════

class TestDockerManagerMock:
    """使用 mock 測試 DockerManager 的實際邏輯。"""

    @pytest.fixture
    def mock_client(self):
        """建立 mock Docker 客戶端。"""
        client = MagicMock()
        client.ping.return_value = True
        return client

    @pytest.fixture
    def docker_manager(self, mock_client, monkeypatch):
        """建立帶 mock 客戶端的 DockerManager。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", True
        )
        with patch("backend.services.docker_manager.docker") as mock_docker:
            mock_docker.from_env.return_value = mock_client
            from backend.services.docker_manager import DockerManager
            dm = DockerManager(project="test_project")
            return dm

    def test_available_with_mock_client(self, docker_manager):
        """Mock 客戶端應標記為可用。"""
        assert docker_manager.available is True

    def test_list_containers(self, docker_manager, mock_client):
        """測試列出容器。"""
        mock_container = MagicMock()
        mock_container.name = "test_project-backend-1"
        mock_container.status = "running"
        mock_container.image.tags = ["evoloop-backend:latest"]
        mock_container.ports = []
        mock_container.attrs = {
            "State": {
                "Health": {"Status": "healthy"},
                "StartedAt": "2024-01-01T00:00:00Z",
            }
        }
        mock_client.containers.list.return_value = [mock_container]

        containers = docker_manager.list_containers()
        assert len(containers) == 1
        assert containers[0]["service"] == "backend"
        assert containers[0]["status"] == "running"
        assert containers[0]["health"] == "healthy"

    def test_list_containers_empty(self, docker_manager, mock_client):
        """空容器列表。"""
        mock_client.containers.list.return_value = []
        containers = docker_manager.list_containers()
        assert containers == []

    def test_get_container_logs(self, docker_manager, mock_client):
        """測試讀取日誌。"""
        mock_container = MagicMock()
        mock_container.logs.return_value = b"2024-01-01T00:00:00Z log line 1\n"
        mock_client.containers.get.return_value = mock_container

        logs = docker_manager.get_container_logs("backend", tail=50)
        assert "log line 1" in logs

    def test_get_container_logs_not_found(self, docker_manager, mock_client):
        """測試容器不存在時的日誌讀取。"""
        from docker.errors import NotFound as DockerNotFound
        mock_client.containers.get.side_effect = DockerNotFound("not found")

        logs = docker_manager.get_container_logs("nonexistent")
        assert "找不到" in logs

    def test_restart_service(self, docker_manager, mock_client):
        """測試重啟服務。"""
        mock_container = MagicMock()
        mock_client.containers.get.return_value = mock_container
        # 模擬允許的服務列表（需要正確的 name 屬性）
        mock_backend = MagicMock()
        mock_backend.configure_mock(name="test_project-backend-1")
        mock_frontend = MagicMock()
        mock_frontend.configure_mock(name="test_project-frontend-1")
        mock_client.containers.list.return_value = [mock_backend, mock_frontend]

        result = docker_manager.restart_service("backend")
        assert result["success"] is True
        mock_container.restart.assert_called_once()

    def test_restart_service_not_allowed(self, docker_manager, mock_client):
        """測試重啟不允許的服務。"""
        mock_backend = MagicMock()
        mock_backend.configure_mock(name="test_project-backend-1")
        mock_client.containers.list.return_value = [mock_backend]

        result = docker_manager.restart_service("external_service")
        assert result["success"] is False
        assert "不在允許列表" in result["message"]

    def test_health_check(self, docker_manager, mock_client):
        """測試健康檢查。"""
        mock_container = MagicMock()
        mock_container.name = "test_project-backend-1"
        mock_container.status = "Up 2 hours"
        mock_container.image.tags = ["evoloop-backend:latest"]
        mock_container.ports = []
        mock_container.attrs = {
            "State": {
                "Health": {"Status": "healthy"},
                "StartedAt": "2024-01-01T00:00:00Z",
            }
        }
        mock_client.containers.list.return_value = [mock_container]

        health = docker_manager.health_check()
        assert health["all_healthy"] is True
        assert "backend" in health["services"]

    def test_get_stats(self, docker_manager, mock_client):
        """測試資源統計。"""
        mock_container = MagicMock()
        mock_container.name = "test_project-backend-1"
        mock_container.stats.return_value = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 100000},
                "system_cpu_usage": 500000,
                "online_cpus": 4,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 50000},
                "system_cpu_usage": 400000,
            },
            "memory_stats": {"usage": 100 * 1024 * 1024, "limit": 512 * 1024 * 1024},
            "networks": {"eth0": {"rx_bytes": 1000, "tx_bytes": 500}},
        }
        mock_client.containers.list.return_value = [mock_container]

        stats = docker_manager.get_stats()
        assert "backend" in stats
        assert stats["backend"]["memory_usage"] == 100 * 1024 * 1024

    def test_extract_service_name(self, docker_manager):
        """測試從容器名稱提取服務名。"""
        assert docker_manager._extract_service("test_project-backend-1") == "backend"
        assert docker_manager._extract_service("test_project-frontend-1") == "frontend"
        assert docker_manager._extract_service("test_project-opc-1") == "opc"

    def test_calc_cpu_percent(self, docker_manager):
        """測試 CPU 百分比計算。"""
        stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 200000},
                "system_cpu_usage": 1000000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 100000},
                "system_cpu_usage": 800000,
            },
        }
        cpu = docker_manager._calc_cpu_percent(stats)
        assert cpu > 0  # (200000-100000) / (1000000-800000) * 2 * 100 = 100%


# ═══════════════════════════════════════════════════════════════
# docker_tools 測試
# ═══════════════════════════════════════════════════════════════

class TestDockerTools:
    """測試 Docker 工具函數與權限。"""

    def test_can_use_docker_tool_manager(self):
        """Manager 可以使用全部工具。"""
        from backend.company.docker_tools import (
            CONTROL_DOCKER_TOOLS,
            READONLY_DOCKER_TOOLS,
            can_use_docker_tool,
        )

        for tool in READONLY_DOCKER_TOOLS | CONTROL_DOCKER_TOOLS:
            assert can_use_docker_tool("manager", tool) is True

    def test_can_use_docker_tool_devops(self):
        """DevOps 可以使用全部工具。"""
        from backend.company.docker_tools import (
            CONTROL_DOCKER_TOOLS,
            READONLY_DOCKER_TOOLS,
            can_use_docker_tool,
        )

        for tool in READONLY_DOCKER_TOOLS | CONTROL_DOCKER_TOOLS:
            assert can_use_docker_tool("devops", tool) is True

    def test_can_use_docker_tool_reviewer(self):
        """Reviewer 只能使用只讀工具。"""
        from backend.company.docker_tools import (
            CONTROL_DOCKER_TOOLS,
            READONLY_DOCKER_TOOLS,
            can_use_docker_tool,
        )

        for tool in READONLY_DOCKER_TOOLS:
            assert can_use_docker_tool("reviewer", tool) is True

        for tool in CONTROL_DOCKER_TOOLS:
            assert can_use_docker_tool("reviewer", tool) is False

    def test_can_use_docker_tool_developer(self):
        """Developer 只能使用只讀工具。"""
        from backend.company.docker_tools import (
            can_use_docker_tool,
        )

        assert can_use_docker_tool("developer", "docker_ps") is True
        assert can_use_docker_tool("developer", "docker_restart") is False

    def test_execute_docker_tool_ps(self, monkeypatch):
        """測試 docker_ps 工具執行。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.docker_tools import execute_docker_tool
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        result = execute_docker_tool("docker_ps", manager=dm)
        assert "Docker SDK 不可用" in result

    def test_execute_docker_tool_unknown(self):
        """測試未知工具。"""
        from backend.company.docker_tools import execute_docker_tool
        result = execute_docker_tool("unknown_tool", manager=MagicMock())
        assert "未知的 Docker 工具" in result

    def test_execute_docker_tool_restart_missing_service(self, monkeypatch):
        """測試重啟工具缺少 service 參數。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.docker_tools import execute_docker_tool
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        result = execute_docker_tool("docker_restart", {}, manager=dm)
        assert "錯誤" in result

    def test_docker_tools_dict(self):
        """測試工具定義完整性。"""
        from backend.company.docker_tools import (
            CONTROL_DOCKER_TOOLS,
            DOCKER_TOOLS,
            READONLY_DOCKER_TOOLS,
        )

        assert len(DOCKER_TOOLS) == 7
        assert len(READONLY_DOCKER_TOOLS) == 4
        assert len(CONTROL_DOCKER_TOOLS) == 3
        assert READONLY_DOCKER_TOOLS | CONTROL_DOCKER_TOOLS == set(DOCKER_TOOLS.keys())


# ═══════════════════════════════════════════════════════════════
# CompanyOrchestrator Docker 整合測試
# ═══════════════════════════════════════════════════════════════

class TestOrchestratorDockerIntegration:
    """測試 CompanyOrchestrator 的 Docker 工具集成。"""

    def test_orchestrator_accepts_docker_manager(self, monkeypatch):
        """Orchestrator 應接受 DockerManager 參數。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.services.docker_manager import DockerManager

        dm = DockerManager()
        orchestrator = CompanyOrchestrator(docker_manager=dm)
        assert orchestrator.docker is dm

    def test_get_docker_tools_for_manager(self, monkeypatch):
        """Manager 角色應獲得全部 Docker 工具說明。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.state import RoleType
        from backend.services.docker_manager import DockerManager

        orchestrator = CompanyOrchestrator(docker_manager=DockerManager())
        text = orchestrator._get_docker_tools_for_role(RoleType.MANAGER)
        assert "docker_ps" in text
        assert "docker_restart" in text
        assert "docker_start" in text

    def test_get_docker_tools_for_developer(self, monkeypatch):
        """Developer 角色應獲得只讀 Docker 工具說明（與 Reviewer 相同）。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.state import RoleType
        from backend.services.docker_manager import DockerManager

        orchestrator = CompanyOrchestrator(docker_manager=DockerManager())
        text = orchestrator._get_docker_tools_for_role(RoleType.DEVELOPER)
        # Developer 有只讀 Docker 工具權限
        assert "docker_ps" in text
        assert "docker_logs" in text
        assert "docker_restart" not in text  # 無控制權限

    def test_get_docker_tools_for_reviewer(self, monkeypatch):
        """Reviewer 角色應獲得只讀 Docker 工具說明。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.company.state import RoleType
        from backend.services.docker_manager import DockerManager

        orchestrator = CompanyOrchestrator(docker_manager=DockerManager())
        text = orchestrator._get_docker_tools_for_role(RoleType.REVIEWER)
        assert "docker_ps" in text
        assert "docker_restart" not in text

    def test_execute_docker_request(self, monkeypatch):
        """測試 execute_docker_request 方法。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.services.docker_manager import DockerManager

        orchestrator = CompanyOrchestrator(docker_manager=DockerManager())
        result = orchestrator.execute_docker_request("docker_ps")
        assert "Docker SDK 不可用" in result

    def test_get_docker_status(self, monkeypatch):
        """測試 get_docker_status 方法。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from backend.company.orchestrator import CompanyOrchestrator
        from backend.services.docker_manager import DockerManager

        orchestrator = CompanyOrchestrator(docker_manager=DockerManager())
        status = orchestrator.get_docker_status()
        assert status["available"] is False
        assert isinstance(status["containers"], list)


# ═══════════════════════════════════════════════════════════════
# FastAPI Docker 端點測試
# ═══════════════════════════════════════════════════════════════

class TestDockerApiEndpoints:
    """測試 Docker 管理 API 端點。"""

    @pytest.fixture
    def client(self, monkeypatch):
        """建立 FastAPI 測試客戶端（禁用 Docker）。"""
        monkeypatch.setattr(
            "backend.services.docker_manager.DOCKER_AVAILABLE", False
        )
        from fastapi.testclient import TestClient

        from backend.main import app
        return TestClient(app)

    def test_docker_status_endpoint(self, client):
        """GET /docker/status 應回傳 JSON。"""
        response = client.get("/docker/status")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "containers" in data
        assert "health" in data

    def test_docker_containers_endpoint(self, client):
        """GET /docker/containers 應回傳 JSON。"""
        response = client.get("/docker/containers")
        assert response.status_code == 200
        data = response.json()
        assert "containers" in data

    def test_docker_logs_endpoint(self, client):
        """GET /docker/logs/{service} 應回傳 JSON。"""
        response = client.get("/docker/logs/backend?tail=50")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "backend"
        assert data["tail"] == 50
        assert "logs" in data

    def test_docker_stats_endpoint(self, client):
        """GET /docker/stats 應回傳 JSON。"""
        response = client.get("/docker/stats")
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data

    def test_docker_health_endpoint(self, client, monkeypatch):
        """GET /docker/health 應回傳 JSON。"""
        monkeypatch.setattr("backend.services.docker_manager.DOCKER_AVAILABLE", False)
        monkeypatch.setattr("backend.services.docker_manager._docker_manager", None)
        response = client.get("/docker/health")
        assert response.status_code == 200
        data = response.json()
        assert "_error" in data

    def test_docker_restart_endpoint(self, client):
        """POST /docker/restart/{service} 應回傳 JSON。"""
        response = client.post("/docker/restart/backend")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_docker_stop_endpoint(self, client):
        """POST /docker/stop/{service} 應回傳 JSON。"""
        response = client.post("/docker/stop/backend")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data

    def test_docker_start_endpoint(self, client):
        """POST /docker/start/{service} 應回傳 JSON。"""
        response = client.post("/docker/start/backend")
        assert response.status_code == 200
        data = response.json()
        assert "success" in data