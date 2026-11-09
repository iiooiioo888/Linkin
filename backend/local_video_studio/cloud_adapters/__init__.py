"""Phase 2 雲端適配器 stub（MVP 不實作；CLOUD_ENABLED=false）。"""

from backend.local_video_studio.cloud_adapters.base import CloudAdapter, CloudAdapterError
from backend.local_video_studio.cloud_adapters.cloud_gpu import CloudGPUAdapter
from backend.local_video_studio.cloud_adapters.vidu import ViduAdapter

__all__ = ["CloudAdapter", "CloudAdapterError", "CloudGPUAdapter", "ViduAdapter"]
