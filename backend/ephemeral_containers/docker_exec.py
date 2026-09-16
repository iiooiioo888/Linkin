"""Docker 執行層：可注入假客戶端供單元測試。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from backend.ephemeral_containers.config import LABEL_MANAGED, LABEL_TASK_ID
from backend.ephemeral_containers.models import ContainerTaskCreate

logger = logging.getLogger(__name__)


class LogCallback(Protocol):
    def __call__(self, chunk: str) -> None: ...


@dataclass
class RunResult:
    exit_code: int
    container_id: str
    error: str = ""


class DockerExecutor:
    """在隔離容器中執行單次任務並串流日誌。"""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client
        self._owns_client = client is None

    def _ensure_client(self) -> Any:
        if self._client is not None:
            return self._client
        import docker

        self._client = docker.from_env()
        self._client.ping()
        return self._client

    def available(self) -> bool:
        try:
            self._ensure_client()
            return True
        except Exception:
            return False

    def _create_kwargs(self, spec: ContainerTaskCreate) -> dict[str, Any]:
        mem = f"{spec.memory_mb}m"
        nano_cpus = int(spec.cpu * 1_000_000_000)
        kw: dict[str, Any] = {
            "mem_limit": mem,
            "nano_cpus": nano_cpus,
            "pids_limit": spec.runtime_limits()["pids_limit"],
            "read_only": True,
            "tmpfs": {"/tmp": "size=64m,mode=1777"},
            "security_opt": ["no-new-privileges:true"],
            "cap_drop": ["ALL"],
        }
        if not spec.network:
            kw["network_mode"] = "none"
        return kw

    def run(
        self,
        task_id: str,
        spec: ContainerTaskCreate,
        on_log: LogCallback,
        stop_event: threading.Event | None = None,
    ) -> RunResult:
        client = self._ensure_client()
        name = f"linkin-ect-{task_id}"[:63]
        container = None
        exit_code = 124
        err_msg = ""

        try:
            container = client.containers.create(
                image=spec.image,
                command=spec.command,
                name=name,
                detach=True,
                user="65534:65534",
                working_dir=spec.workdir,
                environment=spec.env or None,
                labels={
                    LABEL_MANAGED: "true",
                    LABEL_TASK_ID: task_id,
                },
                **self._create_kwargs(spec),
            )
            cid = container.id if hasattr(container, "id") else str(container)
            container.start()

            deadline = time.monotonic() + spec.timeout_sec
            log_thread = threading.Thread(
                target=self._stream_logs,
                args=(container, on_log, stop_event),
                daemon=True,
            )
            log_thread.start()

            while True:
                if stop_event and stop_event.is_set():
                    try:
                        container.kill()
                    except Exception:
                        pass
                    exit_code = 130
                    err_msg = "cancelled"
                    break
                container.reload()
                status = container.status
                if status not in {"created", "running", "restarting"}:
                    exit_code = int(container.attrs.get("State", {}).get("ExitCode", 1))
                    break
                if time.monotonic() > deadline:
                    try:
                        container.kill()
                    except Exception:
                        pass
                    exit_code = 124
                    err_msg = "timeout"
                    break
                time.sleep(0.25)

            log_thread.join(timeout=2.0)
            return RunResult(exit_code=exit_code, container_id=cid, error=err_msg)
        except Exception as exc:
            logger.exception("臨時容器執行失敗 task=%s", task_id)
            return RunResult(exit_code=1, container_id="", error=str(exc))
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as exc:
                    logger.warning("移除容器失敗 %s: %s", task_id, exc)

    def _stream_logs(
        self,
        container: Any,
        on_log: LogCallback,
        stop_event: threading.Event | None,
    ) -> None:
        try:
            for chunk in container.logs(stream=True, follow=True):
                if stop_event and stop_event.is_set():
                    break
                if isinstance(chunk, bytes):
                    on_log(chunk.decode("utf-8", errors="replace"))
                else:
                    on_log(str(chunk))
        except Exception as exc:
            logger.debug("日誌串流結束：%s", exc)


_default_executor: DockerExecutor | None = None


def get_docker_executor() -> DockerExecutor:
    global _default_executor
    if _default_executor is None:
        _default_executor = DockerExecutor()
    return _default_executor


def set_docker_executor(executor: DockerExecutor | None) -> None:
    global _default_executor
    _default_executor = executor
