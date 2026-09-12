"""Minecraft 可觀測性：結構化事件、監控摘要與 AI 上下文。

事件以 append-only JSONL 持久化於 ``EVOL_LINKIN_DATA_DIR/minecraft_events.jsonl``。
人類監控面板與 AI snapshot/context 共用同一資料源。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_lock = threading.Lock()
_EVENT_FILE: Path | None = None


def _data_dir() -> Path:
    root = os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin")
    return Path(root)


def _event_path() -> Path:
    global _EVENT_FILE
    if _EVENT_FILE is None:
        _EVENT_FILE = _data_dir() / "minecraft_events.jsonl"
    return _EVENT_FILE


def reset_minecraft_events() -> None:
    """測試用：清空事件檔。"""
    global _EVENT_FILE
    path = _event_path()
    with _lock:
        if path.exists():
            path.unlink()
    _EVENT_FILE = None


def append_minecraft_event(
    *,
    domain: str,
    action: str,
    status: str,
    summary: str,
    details: dict[str, Any] | None = None,
    entity_refs: dict[str, Any] | None = None,
    dry_run: bool = False,
    bridge_offline: bool = False,
) -> dict[str, Any]:
    """追加一筆 Minecraft 側動作事件（結構化、可被查詢）。"""
    record = {
        "id": f"mcevt-{uuid.uuid4().hex[:12]}",
        "ts": time.time(),
        "domain": str(domain),
        "action": str(action),
        "status": str(status),
        "summary": str(summary).strip(),
        "dry_run": bool(dry_run),
        "bridge_offline": bool(bridge_offline),
        "details": dict(details or {}),
        "entity_refs": dict(entity_refs or {}),
    }
    path = _event_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _lock, path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return record


def _read_all_events() -> list[dict[str, Any]]:
    path = _event_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with _lock:
        text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def list_minecraft_events(
    *,
    since: float | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """分頁列出事件（時間正序）。cursor 為上一頁最後一筆 id。"""
    limit = max(1, min(int(limit or 50), 200))
    rows = _read_all_events()
    if since is not None:
        rows = [r for r in rows if float(r.get("ts") or 0) >= float(since)]
    rows.sort(key=lambda r: float(r.get("ts") or 0))

    start_idx = 0
    if cursor:
        for idx, row in enumerate(rows):
            if str(row.get("id")) == cursor:
                start_idx = idx + 1
                break

    page = rows[start_idx : start_idx + limit]
    next_cursor = str(page[-1]["id"]) if page and start_idx + limit < len(rows) else None
    return {
        "events": page,
        "count": len(page),
        "total": len(rows),
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    }


def _count_by_status(entities: list[dict[str, Any]], field: str = "world_status") -> dict[str, int]:
    counts: dict[str, int] = {}
    for ent in entities:
        key = str(ent.get(field) or ent.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _last_event(*domains: str) -> dict[str, Any] | None:
    rows = _read_all_events()
    for row in reversed(rows):
        if not domains or str(row.get("domain")) in domains:
            return row
    return None


def _recent_errors(limit: int = 5) -> list[dict[str, Any]]:
    rows = _read_all_events()
    bad_status = {"failed", "partial", "bridge_offline", "error", "cancelled"}
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        status = str(row.get("status") or "")
        if status in bad_status or row.get("bridge_offline"):
            out.append(row)
        if len(out) >= limit:
            break
    return out


def build_monitor_summary() -> dict[str, Any]:
    """監控總覽 KPI（供 UI hub 單次請求）。"""
    from backend.linkin.knowledge import list_entities
    from backend.linkin.minecraft import monitor_status
    from backend.linkin.narrative_world_apply import list_pending_intents

    bridge = monitor_status()
    briefs = list_entities("build_briefs")
    map_plans = list_entities("map_plans")
    npcs = list_entities("npcs")
    quests = list_entities("quests")
    items = list_entities("items")
    pending = list_pending_intents()

    pending_briefs = [b for b in briefs if str(b.get("status") or "") in {"pending_builder", "planned"}]
    pipeline_evt = _last_event("narrative", "pipeline")

    return {
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
            "token_configured": bridge.get("token_configured"),
            "world": bridge.get("world"),
        },
        "kpis": {
            "pending_build_briefs": len(pending_briefs),
            "pending_world_intents": pending.get("count", 0),
            "map_plan_count": len(map_plans),
            "npc_count": len(npcs),
            "quest_count": len(quests),
            "item_count": len(items),
        },
        "world_status": {
            "npcs": _count_by_status(npcs),
            "quests": _count_by_status(quests),
            "items": _count_by_status(items),
            "build_briefs": _count_by_status(briefs, "status"),
            "map_plans": _count_by_status(map_plans, "status"),
        },
        "last_pipeline": pipeline_evt,
        "recent_errors": _recent_errors(5),
        "generated_at": time.time(),
    }


def build_ai_snapshot() -> dict[str, Any]:
    """當前 Minecraft/RPG 狀態摘要（供 prompt 注入）。"""
    from backend.linkin.knowledge import list_entities
    from backend.linkin.minecraft import monitor_status
    from backend.linkin.narrative_registry import get_narrative_registry
    from backend.linkin.narrative_world_apply import list_pending_intents

    bridge = monitor_status()
    summary = build_monitor_summary()
    map_plans = list_entities("map_plans")
    latest_map = sorted(map_plans, key=lambda p: str(p.get("id") or ""), reverse=True)
    workspaces = [ws.to_dict() for ws in get_narrative_registry().list_for_task(include_terminal=True)]
    recent = list_minecraft_events(limit=10)

    return {
        "bridge": summary["bridge"],
        "kpis": summary["kpis"],
        "world_status": summary["world_status"],
        "pending_intents": list_pending_intents(),
        "latest_map_plan": latest_map[0] if latest_map else None,
        "active_workspaces": [w for w in workspaces if w.get("state") == "active"],
        "last_pipeline": summary.get("last_pipeline"),
        "recent_events": recent.get("events") or [],
        "recent_errors": summary.get("recent_errors") or [],
        "generated_at": time.time(),
    }


def build_ai_context(*, max_chars: int = 8000, fmt: str = "markdown") -> dict[str, Any]:
    """token-budget 感知的 LLM 注入 blob。"""
    max_chars = max(500, min(int(max_chars or 8000), 32000))
    snap = build_ai_snapshot()
    lines: list[str] = [
        "# Minecraft 伺服器可觀測狀態",
        "",
        "## 橋接",
        (
            f"- enabled={snap['bridge'].get('enabled')} connected={snap['bridge'].get('connected')} "
            f"dry_run={snap['bridge'].get('dry_run')} world={snap['bridge'].get('world')}"
        ),
        "",
        "## KPI",
    ]
    for key, val in (snap.get("kpis") or {}).items():
        lines.append(f"- {key}: {val}")

    ws = snap.get("world_status") or {}
    lines.append("\n## 實體狀態")
    for kind, counts in ws.items():
        if counts:
            parts = ", ".join(f"{k}={v}" for k, v in counts.items())
            lines.append(f"- {kind}: {parts}")

    pending = snap.get("pending_intents") or {}
    if pending.get("count"):
        lines.append(f"\n## 待落地世界意圖：{pending['count']} 筆")

    last = snap.get("last_pipeline")
    if last:
        lines.append(
            f"\n## 最近管線步驟\n- [{last.get('domain')}/{last.get('action')}] "
            f"{last.get('status')}: {last.get('summary')}"
        )

    events = snap.get("recent_events") or []
    if events:
        lines.append("\n## 近期動作")
        for evt in events[-8:]:
            flag = ""
            if evt.get("dry_run"):
                flag = " [dry-run]"
            if evt.get("bridge_offline"):
                flag += " [bridge_offline]"
            lines.append(
                f"- {evt.get('domain')}/{evt.get('action')} → {evt.get('status')}{flag}: {evt.get('summary')}"
            )

    errors = snap.get("recent_errors") or []
    if errors:
        lines.append("\n## 近期錯誤／異常")
        for evt in errors[:5]:
            lines.append(f"- {evt.get('summary')} ({evt.get('status')})")

    text = "\n".join(lines).strip()
    truncated = False
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n…(truncated)"
        truncated = True

    if fmt == "json":
        payload = snap
        blob = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(blob) > max_chars:
            blob = blob[: max_chars - 20] + "…(truncated)"
            truncated = True
        return {"format": "json", "context": blob, "chars": len(blob), "truncated": truncated, "snapshot": snap}

    return {"format": "markdown", "context": text, "chars": len(text), "truncated": truncated, "snapshot": snap}


def safe_append_minecraft_event(**kwargs: Any) -> None:
    """不中斷主流程的事件寫入。"""
    try:
        append_minecraft_event(**kwargs)
    except Exception:
        pass


__all__ = [
    "append_minecraft_event",
    "build_ai_context",
    "build_ai_snapshot",
    "build_monitor_summary",
    "list_minecraft_events",
    "reset_minecraft_events",
    "safe_append_minecraft_event",
]
