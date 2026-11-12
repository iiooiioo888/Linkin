"""CloudEvents — 容器事件記錄（自 cloud_console 抽出）。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import logger

# ═══════════════════════════════════════════════════════════════
# CloudEvents — 容器事件
# ═══════════════════════════════════════════════════════════════


class CloudEvents:
    """容器事件記錄器。

    記錄容器 start/stop/restart 操作，形成操作時間線。
    """

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.getenv(
                "CLOUD_EVENTS_DIR",
                # 套件化後多一層目錄：parents[3] 仍指向 repo 根，維持原 backend/data/cloud_events。
                str(Path(__file__).resolve().parents[3] / "backend" / "data" / "cloud_events"),
            )
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._events_file = self._data_dir / "events.jsonl"

    def record(self, event_type: str, service: str, detail: str = "") -> None:
        """記錄容器事件。

        Args:
            event_type: 事件類型（restart / stop / start）
            service: 服務名稱
            detail: 詳細信息
        """
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "service": service,
            "detail": detail,
        }
        try:
            with open(self._events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.debug("記錄容器事件失敗", exc_info=True)

    def get_events(self, limit: int = 50) -> list[dict[str, Any]]:
        """獲取最近的容器事件。

        Args:
            limit: 返回數量

        Returns:
            事件列表（按時間倒序）
        """
        if not self._events_file.exists():
            return []
        try:
            lines = self._events_file.read_text(encoding="utf-8").strip().split("\n")
            records = [json.loads(line) for line in lines if line.strip()]
            records.sort(key=lambda x: x.get("ts", ""), reverse=True)
            return records[:limit]
        except Exception:
            return []
