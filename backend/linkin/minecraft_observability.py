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
    domain: str | None = None,
) -> dict[str, Any]:
    """分頁列出事件（時間正序）。cursor 為上一頁最後一筆 id。"""
    limit = max(1, min(int(limit or 50), 200))
    rows = _read_all_events()
    if since is not None:
        rows = [r for r in rows if float(r.get("ts") or 0) >= float(since)]
    if domain:
        rows = [r for r in rows if str(r.get("domain")) == domain]
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


_PIPELINE_DOMAINS = frozenset({"narrative", "pipeline", "map", "build", "world", "bridge"})


def recent_pipeline_events(limit: int = 10) -> list[dict[str, Any]]:
    """最近管線／落地相關事件（時間正序，供 UI 時間軸）。"""
    limit = max(1, min(int(limit or 10), 50))
    rows = _read_all_events()
    matched = [
        row
        for row in rows
        if str(row.get("domain")) in _PIPELINE_DOMAINS
        or str(row.get("action")) in {"run", "generate", "commit", "apply", "dispatch", "probe"}
    ]
    return matched[-limit:]


def _latest_successful_bridge_probe_ts(rows: list[dict[str, Any]]) -> float | None:
    """最新一次成功的橋接探測時間戳（用於壓掉其後已恢復的離線錯誤）。"""
    latest: float | None = None
    for row in rows:
        if str(row.get("domain") or "") != "bridge":
            continue
        if str(row.get("action") or "") != "probe":
            continue
        if row.get("dry_run") or row.get("bridge_offline"):
            continue
        if str(row.get("status") or "") != "ok":
            continue
        try:
            ts = float(row.get("ts") or 0)
        except (TypeError, ValueError):
            continue
        if latest is None or ts > latest:
            latest = ts
    return latest


def _recent_errors(limit: int = 5) -> list[dict[str, Any]]:
    rows = _read_all_events()
    bad_status = {"failed", "partial", "bridge_offline", "error", "cancelled"}
    recovered_after = _latest_successful_bridge_probe_ts(rows)
    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        if row.get("dry_run"):
            continue
        status = str(row.get("status") or "")
        if status in {"dry_run", "ok"}:
            continue
        # 已有更新的成功探測時，不再把舊的 bridge probe 離線事件當「近期錯誤」
        if (
            recovered_after is not None
            and str(row.get("domain") or "") == "bridge"
            and str(row.get("action") or "") == "probe"
            and (status == "bridge_offline" or row.get("bridge_offline"))
        ):
            try:
                ts = float(row.get("ts") or 0)
            except (TypeError, ValueError):
                ts = 0.0
            if ts < recovered_after:
                continue
        if status in bad_status or row.get("bridge_offline"):
            out.append(row)
        if len(out) >= limit:
            break
    return out


def count_minecraft_events_since(since_ts: float) -> int:
    """統計自 since_ts 以來的可觀測性事件筆數（供監控 KPI）。"""
    cutoff = float(since_ts)
    rows = _read_all_events()
    return sum(1 for row in rows if float(row.get("ts") or 0) >= cutoff)


def resolve_ai_gm_status(cfg: dict[str, Any]) -> str:
    """AI 主持人狀態：offline / dry-run / active / idle。"""
    if not cfg.get("enabled"):
        return "offline"
    if cfg.get("dry_run"):
        return "dry-run"
    if cfg.get("auto_apply"):
        return "active"
    return "idle"


def aggregate_ai_monitor_kpis(now: float | None = None) -> dict[str, Any]:
    """Monitor Hub：AI 可觀測性 KPI（GM、事件、情境提示）。不捏造玩家數。"""
    ts_now = float(now if now is not None else time.time())
    since_24h = ts_now - 86400.0

    events_24h = count_minecraft_events_since(since_24h)

    gm_cfg: dict[str, Any] = {}
    gm_last: dict[str, Any] | None = None
    gm_runs_24h = 0
    try:
        from backend.linkin.minecraft_ai_gm import get_gm_config, list_gm_runs

        gm_cfg = get_gm_config()
        runs_page = list_gm_runs(limit=200)
        runs = runs_page.get("runs") or []
        gm_last = runs[0] if runs else None
        gm_runs_24h = sum(1 for run in runs if float(run.get("ts") or 0) >= since_24h)
    except Exception:
        gm_cfg = {}

    last_actions = 0
    if gm_last:
        actions = gm_last.get("actions") or []
        last_actions = len([a for a in actions if str((a or {}).get("type") or "") != "noop"])

    situation_hint: str | None = None
    try:
        from backend.linkin.minecraft_situation import build_situation_snapshot

        snap = build_situation_snapshot()
        hints = snap.get("hints") or []
        if hints:
            situation_hint = str(hints[0]).strip()[:160] or None
    except Exception:
        situation_hint = None

    return {
        "events_24h": events_24h,
        "gm_status": resolve_ai_gm_status(gm_cfg),
        "gm_enabled": bool(gm_cfg.get("enabled")),
        "gm_dry_run": bool(gm_cfg.get("dry_run", True)),
        "gm_auto_apply": bool(gm_cfg.get("auto_apply")),
        "gm_cooldown_seconds": float(gm_cfg.get("cooldown_seconds") or 30),
        "gm_runs_24h": gm_runs_24h,
        "gm_last_run_ts": float(gm_last.get("ts") or 0) if gm_last else None,
        "gm_last_action_count": last_actions,
        "gm_last_applied": bool(gm_last.get("applied")) if gm_last else False,
        "gm_last_dry_run": bool(gm_last.get("dry_run")) if gm_last else None,
        "gm_last_trigger_action": (str(gm_last.get("trigger_action") or "").strip() or None) if gm_last else None,
        "situation_hint": situation_hint,
    }


def _bridge_setup_block(bridge: dict[str, Any]) -> dict[str, Any]:
    raw_probe = bridge.get("probe")
    probe: dict[str, Any] = raw_probe if isinstance(raw_probe, dict) else {}
    url = str(bridge.get("url") or "").strip()
    world = str(bridge.get("world") or "").strip()
    enabled = bool(bridge.get("enabled"))
    token_set = bool(bridge.get("token_configured"))
    url_set = bool(url)
    world_set = bool(world)
    probe_msg = str(probe.get("message") or probe.get("error") or "").strip()
    return {
        "enabled": enabled,
        "url_set": url_set,
        "token_set": token_set,
        "world_set": world_set,
        "all_ready": enabled and url_set and token_set,
        "connected": bool(bridge.get("connected")),
        "dry_run": bool(bridge.get("dry_run")),
        "probe_ok": probe.get("ok") if probe else None,
        "probe_message": probe_msg,
    }


def build_monitor_summary() -> dict[str, Any]:
    """監控總覽 KPI（供 UI hub 單次請求）。"""
    from backend.linkin.knowledge import list_entities
    from backend.linkin.minecraft import monitor_status
    from backend.linkin.minecraft_plugins import monitor_summary as plugin_summary
    from backend.linkin.narrative_world_apply import list_pending_intents

    bridge = monitor_status()
    plugins: dict[str, Any] = {}
    try:
        plugins = plugin_summary()
    except Exception:
        plugins = {}
    briefs = list_entities("build_briefs")
    map_plans = list_entities("map_plans")
    npcs = list_entities("npcs")
    quests = list_entities("quests")
    items = list_entities("items")
    pending = list_pending_intents()
    players_block: dict[str, Any] = {}
    try:
        from backend.linkin.minecraft_players import build_players_ai_block

        players_block = build_players_ai_block(max_players=12, max_events=0)
    except Exception:
        players_block = {}

    active_quest_progress = 0
    try:
        from backend.linkin.quest_runtime import list_quest_progress

        active_quest_progress = len(list_quest_progress(status="active"))
    except Exception:
        active_quest_progress = 0

    pending_briefs = [b for b in briefs if str(b.get("status") or "") in {"pending_builder", "planned"}]
    pipeline_evt = _last_event("narrative", "pipeline")
    bridge_errors = [
        e
        for e in _recent_errors(8)
        if str(e.get("domain")) == "bridge" or e.get("bridge_offline")
    ]

    return {
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
            "live": bridge.get("live"),
            "token_configured": bridge.get("token_configured"),
            "world": bridge.get("world"),
            "url": bridge.get("url"),
        },
        "bridge_setup": _bridge_setup_block(bridge),
        "plugins": plugins,
        "kpis": {
            "pending_build_briefs": len(pending_briefs),
            "pending_world_intents": pending.get("count", 0),
            "map_plan_count": len(map_plans),
            "npc_count": len(npcs),
            "quest_count": len(quests),
            "item_count": len(items),
            "online_players": players_block.get("online_count", 0),
            "active_quest_progress": active_quest_progress,
            "players_live": {
                "online_count": players_block.get("online_count", 0),
                "bridge_offline": players_block.get("bridge_offline"),
                "recent_events": len(players_block.get("recent_activity") or []),
            },
            "ai": aggregate_ai_monitor_kpis(),
        },
        "players": players_block,
        "world_status": {
            "npcs": _count_by_status(npcs),
            "quests": _count_by_status(quests),
            "items": _count_by_status(items),
            "build_briefs": _count_by_status(briefs, "status"),
            "map_plans": _count_by_status(map_plans, "status"),
        },
        "last_pipeline": pipeline_evt,
        "pipeline_timeline": recent_pipeline_events(10),
        "recent_errors": _recent_errors(5),
        "bridge_errors": bridge_errors[:3],
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
    players_block: dict[str, Any] = {}
    try:
        from backend.linkin.minecraft_players import build_players_ai_block

        players_block = build_players_ai_block(max_players=8, max_events=8)
    except Exception:
        players_block = {}

    quest_runtime: dict[str, Any] = {}
    try:
        from backend.linkin.quest_runtime import build_active_quests_summary, list_quest_progress

        active_rows = build_active_quests_summary(limit=10)
        quest_runtime = {
            "active_count": len(active_rows),
            "completed_count": len(list_quest_progress(status="completed")),
            "active_quests": active_rows,
        }
    except Exception:
        quest_runtime = {}

    layout_summary = None
    try:
        from backend.linkin.layout_preview import build_layout_preview

        preview = build_layout_preview()
        if not preview.get("empty"):
            layout_summary = preview.get("layout_summary")
    except Exception:
        layout_summary = None

    situation: dict[str, Any] = {}
    try:
        from backend.linkin.minecraft_situation import compact_situation_for_context

        situation = compact_situation_for_context()
    except Exception:
        situation = {}

    return {
        "bridge": summary["bridge"],
        "bridge_setup": summary.get("bridge_setup"),
        "plugins": summary.get("plugins") or {},
        "kpis": summary["kpis"],
        "world_status": summary["world_status"],
        "pending_intents": list_pending_intents(),
        "latest_map_plan": latest_map[0] if latest_map else None,
        "layout_summary": layout_summary,
        "active_workspaces": [w for w in workspaces if w.get("state") == "active"],
        "last_pipeline": summary.get("last_pipeline"),
        "pipeline_timeline": summary.get("pipeline_timeline") or [],
        "recent_events": recent.get("events") or [],
        "recent_errors": summary.get("recent_errors") or [],
        "players": players_block,
        "quest_runtime": quest_runtime,
        "situation": situation,
        "generated_at": time.time(),
    }


def build_ai_context(*, max_chars: int = 8000, fmt: str = "markdown") -> dict[str, Any]:
    """token-budget 感知的 LLM 注入 blob。"""
    max_chars = max(500, min(int(max_chars or 8000), 32000))
    snap = build_ai_snapshot()
    plugins = snap.get("plugins") or {}
    situation = snap.get("situation") or {}
    lines: list[str] = [
        "# Minecraft 伺服器可觀測狀態",
        "",
        "## 四維情境快照",
    ]
    if situation:
        for dim_key, dim_label in (
            ("market", "市況"),
            ("economy", "經濟"),
            ("land", "地土"),
            ("players", "玩家"),
        ):
            block = situation.get(dim_key) or {}
            status = block.get("status") or "unknown"
            summary_txt = block.get("summary") or "—"
            conf = block.get("confidence")
            conf_txt = f" conf={conf}" if conf is not None else ""
            lines.append(f"- {dim_label} [{status}]{conf_txt}: {summary_txt}")
        hints = situation.get("hints") or []
        if hints:
            lines.append("\n### GM 情境提示")
            for hint in hints[:6]:
                lines.append(f"- {hint}")
    else:
        lines.append("- 情境快照不可用")

    lines.extend(
        [
            "",
            "## 橋接",
            (
                f"- enabled={snap['bridge'].get('enabled')} connected={snap['bridge'].get('connected')} "
                f"dry_run={snap['bridge'].get('dry_run')} world={snap['bridge'].get('world')}"
            ),
            "",
            "## 地圖插件",
            (
                f"- active={plugins.get('active_map_plugin')} map_url={plugins.get('map_url')} "
                f"reachable={plugins.get('reachable_count')}/{plugins.get('configured_count')}"
            ),
            "",
            "## KPI",
        ]
    )
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

    quest_rt = snap.get("quest_runtime") or {}
    if quest_rt.get("active_quests"):
        lines.append(f"\n## 任務進度（活躍 {quest_rt.get('active_count', 0)}）")
        for row in (quest_rt.get("active_quests") or [])[:8]:
            objs = row.get("objectives_detail") or []
            done = row.get("objectives_done", 0)
            total = row.get("objectives_total", len(objs))
            obj_txt = "；".join(
                f"{'✓' if o.get('done') else '○'}{o.get('title') or o.get('id')}" for o in objs[:4]
            )
            lines.append(
                f"- [{row.get('player_id')}] {row.get('quest_title') or row.get('quest_id')} "
                f"({done}/{total}) {obj_txt}"
            )

    players = snap.get("players") or {}
    if players.get("bridge_offline") and not players.get("online_count"):
        lines.append("\n## 玩家現場")
        lines.append("- 橋接離線或未啟用 — 無即時玩家資料（不捏造）")
    elif players.get("online_count"):
        lines.append(f"\n## 玩家現場（在線 {players.get('online_count')}）")
        for p in (players.get("players") or [])[:6]:
            pos = p.get("position") or {}
            pos_txt = (
                f" @ ({int(pos.get('x', 0))}, {int(pos.get('y', 0))}, {int(pos.get('z', 0))})"
                if pos
                else ""
            )
            dim = p.get("dimension") or p.get("world") or "?"
            inv = p.get("inventory_summary") or []
            inv_txt = ", ".join(f"{i.get('name')}×{i.get('count')}" for i in inv[:4]) if inv else "—"
            lines.append(
                f"- {p.get('name')} [{dim}]{pos_txt} HP={p.get('health') or '?'} 背包={inv_txt}"
            )
        for line in (players.get("activity_lines") or [])[:5]:
            lines.append(f"- 活動：{line}")

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
    "aggregate_ai_monitor_kpis",
    "append_minecraft_event",
    "build_ai_context",
    "build_ai_snapshot",
    "build_monitor_summary",
    "count_minecraft_events_since",
    "list_minecraft_events",
    "recent_pipeline_events",
    "reset_minecraft_events",
    "resolve_ai_gm_status",
    "safe_append_minecraft_event",
]
