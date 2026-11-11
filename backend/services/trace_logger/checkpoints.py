"""檢查點讀寫（自 backend.services.trace_logger 抽出）。

save／load／delete／list checkpoint。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .paths import checkpoint_dir, checkpoint_path, utc_now_iso

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 檢查點管理
# ═══════════════════════════════════════════════════════════


def save_checkpoint(task_id: str, checkpoint_data: dict[str, Any]) -> Path | None:
    """保存任務檢查點到本地 JSON 檔案。

    Args:
        task_id: 任務 ID
        checkpoint_data: 檢查點數據（orchestrator.to_checkpoint() 的結果）

    Returns:
        寫入的檔案路徑；失敗時回傳 None
    """
    try:
        directory = checkpoint_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = checkpoint_path(task_id)
        data = {
            "task_id": task_id,
            "saved_at": utc_now_iso(),
            "version": 1,
            **checkpoint_data,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.info("檢查點已保存：task_id=%s", task_id)
        return path
    except OSError as exc:
        logger.warning("檢查點保存失敗：task_id=%s, %s", task_id, exc)
        return None


def load_checkpoint(task_id: str) -> dict[str, Any] | None:
    """載入任務檢查點。

    Args:
        task_id: 任務 ID

    Returns:
        檢查點數據；不存在或讀取失敗時回傳 None
    """
    path = checkpoint_path(task_id)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("檢查點載入失敗：task_id=%s, %s", task_id, exc)
        return None


def delete_checkpoint(task_id: str) -> bool:
    """刪除任務檢查點（任務完成後清理）。"""
    path = checkpoint_path(task_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def list_checkpoints() -> list[dict[str, Any]]:
    """列出所有可恢復的檢查點。

    Returns:
        檢查點摘要列表（task_id, saved_at, goal, phase）
    """
    directory = checkpoint_dir()
    if not directory.exists():
        return []
    results = []
    for path in directory.glob("checkpoint_*.json"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            results.append({
                "task_id": data.get("task_id", ""),
                "saved_at": data.get("saved_at", ""),
                "goal": data.get("goal", ""),
                "phase": data.get("phase", ""),
                "config_name": data.get("config_name", ""),
                "work_item_count": len(data.get("work_items", [])),
            })
        except (OSError, json.JSONDecodeError):
            continue
    results.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return results
