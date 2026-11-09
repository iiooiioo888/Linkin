"""Local Video Studio（local-video-studio）：本機優先 AI 影片生成模組。

M0：骨架與 health；M1+ 見根目錄 ``PROJECT_SPEC.md``。
"""

from backend.local_video_studio.api import register_local_video_studio

__all__ = ["register_local_video_studio"]
