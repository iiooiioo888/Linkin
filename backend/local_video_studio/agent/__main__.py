"""Daemon 入口：``python -m backend.local_video_studio.agent``。"""

from backend.local_video_studio.agent.daemon import main

if __name__ == "__main__":
    raise SystemExit(main())
