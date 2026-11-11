"""軌跡讀取與清理（自 backend.services.trace_logger 抽出）。

delete_trace／read_trace／trace_event_counts／list_traces。
"""

from __future__ import annotations

import json
from typing import Any

from .paths import trace_dir, trace_path


def delete_trace(task_id: str) -> bool:
    """刪除任務軌跡 JSONL（取消／過期清理）。"""
    path = trace_path(task_id)
    if path.exists():
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False


def read_trace(
    task_id: str,
    limit: int = 100,
    offset: int = 0,
    *,
    event: str | None = None,
    role: str | None = None,
    item_id: str | None = None,
) -> list[dict[str, Any]]:
    """讀取任務軌跡記錄。

    Args:
        task_id: 任務 ID
        limit: 返回條數上限
        offset: 跳過前 N 條（篩選後再分頁）
        event: 事件名篩選（逗號分隔多值，如 work_item_done,llm_call）
        role: 角色篩選（逗號分隔多值）
        item_id: 工作項篩選

    Returns:
        事件記錄列表（按時間順序）
    """
    path = trace_path(task_id)
    if not path.exists():
        return []
    events = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError:
        return []
    if event:
        wanted = {e.strip() for e in event.split(",") if e.strip()}
        if wanted:
            events = [ev for ev in events if ev.get("event") in wanted]
    if role:
        wanted_roles = {r.strip() for r in role.split(",") if r.strip()}
        if wanted_roles:
            events = [ev for ev in events if ev.get("role") in wanted_roles]
    if item_id:
        events = [ev for ev in events if ev.get("item_id") == item_id]
    return events[offset:offset + limit]


def trace_event_counts(task_id: str) -> dict[str, int]:
    """統計任務軌跡中各事件型的條數（前端篩選器計數用）。"""
    path = trace_path(task_id)
    counts: dict[str, int] = {}
    if not path.exists():
        return counts
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line).get("event", "?")
                except json.JSONDecodeError:
                    continue
                counts[ev] = counts.get(ev, 0) + 1
    except OSError:
        return {}
    return counts


def list_traces(limit: int = 50) -> list[dict[str, Any]]:
    """列出所有軌跡檔案摘要。

    Returns:
        軌跡摘要列表（task_id, event_count, first_ts, last_ts, file_size）
    """
    directory = trace_dir()
    if not directory.exists():
        return []
    results = []
    for path in directory.glob("trace_*.jsonl"):
        try:
            task_id = path.stem.replace("trace_", "")
            stat = path.stat()
            # 讀取首行和末行獲取時間範圍
            first_ts = ""
            last_ts = ""
            event_count = 0
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        event_count += 1
                        try:
                            data = json.loads(line)
                            if not first_ts:
                                first_ts = data.get("ts", "")
                            last_ts = data.get("ts", "")
                        except json.JSONDecodeError:
                            continue
            results.append({
                "task_id": task_id,
                "event_count": event_count,
                "first_ts": first_ts,
                "last_ts": last_ts,
                "file_size_kb": round(stat.st_size / 1024, 1),
            })
        except OSError:
            continue
    results.sort(key=lambda x: str(x.get("last_ts", "")), reverse=True)
    return results[:limit]
