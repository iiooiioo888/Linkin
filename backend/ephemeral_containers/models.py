"""臨時容器任務的請求／回應模型與驗證。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from backend.ephemeral_containers.config import (
    default_timeout_sec,
    image_allowlist,
    max_cpu,
    max_memory_mb,
    max_pids,
    max_timeout_sec,
)


class ContainerTaskCreate(BaseModel):
    image: str = Field(..., description="Docker 映像（须在白名單内）")
    command: list[str] = Field(..., min_length=1, description="容器內 argv 命令")
    timeout_sec: int = Field(default_factory=default_timeout_sec, ge=1)
    cpu: float = Field(default=0.5, gt=0)
    memory_mb: int = Field(default=128, ge=16)
    network: bool = Field(default=False, description="是否允許網路（預設關閉）")
    env: dict[str, str] = Field(default_factory=dict)
    workdir: str = Field(default="/workspace")

    @field_validator("image")
    @classmethod
    def _validate_image(cls, v: str) -> str:
        img = v.strip()
        if not img or ":" not in img:
            raise ValueError("映像须包含 tag，例如 python:3.12-slim")
        if img not in image_allowlist():
            raise ValueError(f"映像不在白名單：{img}")
        return img

    @field_validator("command")
    @classmethod
    def _validate_command(cls, v: list[str]) -> list[str]:
        cmd = [str(x) for x in v if str(x).strip()]
        if not cmd:
            raise ValueError("command 不可為空")
        if len(cmd) > 64:
            raise ValueError("command 參數過多")
        return cmd

    @field_validator("timeout_sec")
    @classmethod
    def _cap_timeout(cls, v: int) -> int:
        return min(v, max_timeout_sec())

    @field_validator("cpu")
    @classmethod
    def _cap_cpu(cls, v: float) -> float:
        return min(float(v), max_cpu())

    @field_validator("memory_mb")
    @classmethod
    def _cap_memory(cls, v: int) -> int:
        return min(int(v), max_memory_mb())

    @field_validator("env")
    @classmethod
    def _validate_env(cls, v: dict[str, str]) -> dict[str, str]:
        if len(v) > 32:
            raise ValueError("env 鍵過多")
        out: dict[str, str] = {}
        for k, val in v.items():
            key = str(k).strip()
            if not key or "=" in key:
                raise ValueError(f"非法 env 鍵：{k!r}")
            if key.upper().startswith("EVOL_") or key.upper() in {"PATH", "HOME", "HOSTNAME"}:
                raise ValueError(f"禁止覆寫環境變數：{key}")
            out[key] = str(val)[:4096]
        return out

    @field_validator("workdir")
    @classmethod
    def _validate_workdir(cls, v: str) -> str:
        wd = v.strip() or "/workspace"
        if not wd.startswith("/") or ".." in wd:
            raise ValueError("workdir 须為絕對路徑且不可含 ..")
        return wd

    def runtime_limits(self) -> dict[str, Any]:
        return {
            "timeout_sec": self.timeout_sec,
            "cpu": self.cpu,
            "memory_mb": self.memory_mb,
            "network": self.network,
            "pids_limit": max_pids(),
        }


class ContainerTaskPublic(BaseModel):
    task_id: str
    status: str
    image: str
    command: list[str]
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    error: str = ""
    logs_tail: str = ""
    logs_truncated: bool = False
    container_id: str = ""
    limits: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
