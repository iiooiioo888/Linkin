"""Cloud GPU stub（Phase 2）。"""

from __future__ import annotations

from typing import Any

from backend.local_video_studio.cloud_adapters.base import CloudAdapterError
from backend.local_video_studio.config import load_config


class CloudGPUAdapter:
    name = "cloud_gpu"

    def submit(self, job: dict[str, Any]) -> dict[str, Any]:
        if not load_config().cloud_enabled:
            raise CloudAdapterError("CLOUD_ENABLED=false；禁止 CloudGPU")
        if job.get("data_class") != "cloud_allowed":
            raise CloudAdapterError("僅 cloud_allowed 可走 CloudGPU")
        raise CloudAdapterError("CloudGPUAdapter 為 Phase 2 stub，尚未實作")
