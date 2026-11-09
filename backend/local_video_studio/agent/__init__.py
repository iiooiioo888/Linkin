"""Render agent：從 central API claim 任務並對 ComfyUI（或 mock）執行。"""

from backend.local_video_studio.agent.poller import run_once

__all__ = ["run_once"]
