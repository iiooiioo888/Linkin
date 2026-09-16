"""臨時容器執行：白名單、上限、清理與 worker 邏輯（假 Docker 客戶端）。"""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
from pydantic import ValidationError

from backend.ephemeral_containers.docker_exec import DockerExecutor, set_docker_executor
from backend.ephemeral_containers.models import ContainerTaskCreate
from backend.ephemeral_containers.store import ContainerTaskStore
from backend.ephemeral_containers.worker import ContainerTaskWorker


class _FakeContainer:
    def __init__(self, task_id: str, on_log: Any):
        self.id = f"cid-{task_id}"
        self.name = f"linkin-ect-{task_id}"
        self.status = "created"
        self.attrs: dict[str, Any] = {"State": {"ExitCode": 0}}
        self._on_log = on_log
        self._started = False
        self._removed = False

    def start(self) -> None:
        self._started = True
        self.status = "running"
        self._on_log("hello from fake\n")

    def reload(self) -> None:
        if self._started and self.status == "running":
            self.status = "exited"

    def kill(self) -> None:
        self.status = "exited"
        self.attrs["State"]["ExitCode"] = 137

    def remove(self, force: bool = False) -> None:
        self._removed = True

    def logs(self, stream: bool = False, follow: bool = False):
        yield b"stream line\n"


class _FakeContainersAPI:
    def __init__(self) -> None:
        self.created: list[_FakeContainer] = []

    def create(self, **kwargs: Any) -> _FakeContainer:
        task_id = kwargs.get("labels", {}).get("linkin.ephemeral.task_id", "x")
        c = _FakeContainer(task_id, lambda _: None)
        self.created.append(c)
        return c


class _FakeDockerClient:
    def __init__(self) -> None:
        self.containers = _FakeContainersAPI()

    def ping(self) -> None:
        return None


@pytest.fixture(autouse=True)
def _enable_flag(monkeypatch):
    monkeypatch.setenv("EVOL_EPHEMERAL_CONTAINERS", "1")


class TestAllowlistAndLimits:
    def test_rejects_unknown_image(self):
        with pytest.raises(ValidationError):
            ContainerTaskCreate(image="evil:latest", command=["echo"])

    def test_caps_timeout_and_memory(self):
        spec = ContainerTaskCreate(
            image="python:3.12-slim",
            command=["python", "-c", "print(1)"],
            timeout_sec=99999,
            memory_mb=99999,
            cpu=99.0,
        )
        assert spec.timeout_sec <= 600
        assert spec.memory_mb <= 512
        assert spec.cpu <= 2.0

    def test_network_defaults_false(self):
        spec = ContainerTaskCreate(image="python:3.12-slim", command=["echo"])
        assert spec.network is False

    def test_forbids_evol_env(self):
        with pytest.raises(ValidationError):
            ContainerTaskCreate(
                image="python:3.12-slim",
                command=["echo"],
                env={"EVOL_SECRET": "x"},
            )


class TestDockerExecutor:
    def test_run_streams_and_removes(self):
        fake = _FakeDockerClient()
        executor = DockerExecutor(client=fake)
        logs: list[str] = []

        result = executor.run(
            "ect-test01",
            ContainerTaskCreate(image="python:3.12-slim", command=["echo", "hi"]),
            on_log=logs.append,
        )
        assert result.exit_code == 0
        assert fake.containers.created[0]._removed is True
        assert any("stream" in x or logs for x in logs)

    def test_timeout_kills(self, monkeypatch):
        class _SlowContainer(_FakeContainer):
            def reload(self) -> None:
                self.status = "running"

        class _SlowAPI(_FakeContainersAPI):
            def create(self, **kwargs: Any) -> _SlowContainer:
                task_id = kwargs.get("labels", {}).get("linkin.ephemeral.task_id", "x")
                c = _SlowContainer(task_id, lambda _: None)
                self.created.append(c)
                return c

        client = _FakeDockerClient()
        client.containers = _SlowAPI()
        executor = DockerExecutor(client=client)
        spec = ContainerTaskCreate(
            image="python:3.12-slim",
            command=["sleep", "999"],
            timeout_sec=1,
        )
        result = executor.run("ect-timeout", spec, on_log=lambda _: None)
        assert result.exit_code == 124
        assert result.error == "timeout"
        assert client.containers.created[0]._removed is True

    def test_create_kwargs_no_network_by_default(self):
        executor = DockerExecutor(client=_FakeDockerClient())
        kw = executor._create_kwargs(
            ContainerTaskCreate(image="python:3.12-slim", command=["echo"])
        )
        assert kw.get("network_mode") == "none"
        assert kw.get("read_only") is True
        assert kw.get("cap_drop") == ["ALL"]


class TestWorker:
    def test_worker_marks_succeeded(self, monkeypatch):
        set_docker_executor(DockerExecutor(client=_FakeDockerClient()))
        store = ContainerTaskStore()
        worker = ContainerTaskWorker()
        spec = ContainerTaskCreate(image="python:3.12-slim", command=["echo", "ok"])
        rec = store.create(spec)
        monkeypatch.setattr(
            "backend.ephemeral_containers.worker.container_task_store",
            store,
        )
        worker._execute_sync(rec.task_id)
        saved = store.get(rec.task_id)
        assert saved is not None
        assert saved.status == "succeeded"
        assert saved.exit_code == 0
        set_docker_executor(None)


@pytest.mark.skipif(
    not os.getenv("EVOL_EPHEMERAL_INTEGRATION_DOCKER"),
    reason="需 EVOL_EPHEMERAL_INTEGRATION_DOCKER=1 與本機 Docker",
)
def test_real_docker_hello():
    """可選整合測試：本機 Docker 跑 echo。"""
    executor = DockerExecutor()
    if not executor.available():
        pytest.skip("Docker 不可用")
    chunks: list[str] = []
    result = executor.run(
        "ect-integration",
        ContainerTaskCreate(
            image="python:3.12-slim",
            command=["python", "-c", "print('linkin-ect')"],
            timeout_sec=60,
        ),
        on_log=chunks.append,
    )
    assert result.exit_code == 0
    assert "linkin-ect" in "".join(chunks)


class TestApi:
    def test_config_and_create_when_enabled(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.ephemeral_containers.docker_exec import DockerExecutor, set_docker_executor
        from backend.main import app

        set_docker_executor(DockerExecutor(client=_FakeDockerClient()))
        monkeypatch.setenv("EVOL_EPHEMERAL_CONTAINERS", "1")
        with TestClient(app) as client:
            cfg = client.get("/linkin/containers/config")
            assert cfg.status_code == 200
            assert cfg.json()["enabled"] is True
            resp = client.post(
                "/linkin/containers/tasks",
                json={
                    "image": "python:3.12-slim",
                    "command": ["echo", "hi"],
                },
            )
            assert resp.status_code == 200
            task_id = resp.json()["task_id"]
            time.sleep(0.5)
            detail = client.get(f"/linkin/containers/tasks/{task_id}")
            assert detail.status_code == 200
            assert detail.json()["status"] in {"succeeded", "running", "queued", "failed"}
        set_docker_executor(None)

    def test_disabled_returns_503(self, monkeypatch):
        from fastapi.testclient import TestClient

        from backend.main import app

        monkeypatch.setenv("EVOL_EPHEMERAL_CONTAINERS", "0")
        with TestClient(app) as client:
            resp = client.post(
                "/linkin/containers/tasks",
                json={"image": "python:3.12-slim", "command": ["echo"]},
            )
            assert resp.status_code == 503
