"""手動觸發已取消任務過期清理。

用法：
    python -m backend.scripts.purge_cancelled_tasks
"""

from __future__ import annotations

import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> int:
    from backend.services.cancelled_task_cleanup import cleanup_enabled, run_cleanup
    from backend.services.task_manager import task_manager

    if not cleanup_enabled():
        print("清理已停用（LINKIN_CANCELLED_TASK_CLEANUP_ENABLED=false）", file=sys.stderr)
        return 1

    task_manager.rehydrate()
    summary = run_cleanup(task_manager)
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0 if not summary.errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
