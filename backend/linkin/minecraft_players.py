"""Minecraft 玩家現場：橋接輪詢、狀態 diff 事件與 AI 摘要。

MineMCP 提供 ``get_online_players`` / ``get_player``；本模組正規化回應、
以快照 diff 產生 join/move/inventory 等事件，並寫入 ``minecraft_events``。
橋接離線時不捏造資料，僅回傳誠實 empty/offline 狀態與已 ingest 的事件。
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from backend.linkin.minecraft_observability import append_minecraft_event, list_minecraft_events

_lock = threading.Lock()
_last_sync_ts = 0.0
_MIN_SYNC_INTERVAL = 3.0
_state_cache: dict[str, dict[str, Any]] = {}
_state_loaded = False


def _data_dir() -> Path:
    import os

    return Path(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin"))


def _state_path() -> Path:
    return _data_dir() / "minecraft_player_state.json"


def reset_player_state() -> None:
    """測試用：清空記憶體與磁碟玩家快照。"""
    global _last_sync_ts, _state_cache, _state_loaded
    with _lock:
        _last_sync_ts = 0.0
        _state_cache = {}
        _state_loaded = False
        path = _state_path()
        if path.exists():
            path.unlink()


def _load_state_cache() -> None:
    global _state_cache, _state_loaded
    if _state_loaded:
        return
    path = _state_path()
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                _state_cache = {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
        except (OSError, json.JSONDecodeError):
            _state_cache = {}
    _state_loaded = True


def _save_state_cache() -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_state_cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _player_key(name: str, uuid_val: str | None = None) -> str:
    if uuid_val:
        return str(uuid_val).lower()
    return str(name).lower()


def _safe_float(val: Any, default: float | None = None) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val: Any, default: int | None = None) -> int | None:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _parse_xyz(raw: Any) -> dict[str, float] | None:
    if isinstance(raw, dict):
        x = _safe_float(raw.get("x"))
        y = _safe_float(raw.get("y"))
        z = _safe_float(raw.get("z"))
        if x is not None and y is not None and z is not None:
            return {"x": x, "y": y, "z": z}
    if isinstance(raw, (list, tuple)) and len(raw) >= 3:
        x = _safe_float(raw[0])
        y = _safe_float(raw[1])
        z = _safe_float(raw[2])
        if x is not None and y is not None and z is not None:
            return {"x": x, "y": y, "z": z}
    text = str(raw or "")
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if len(nums) >= 3:
        return {"x": float(nums[0]), "y": float(nums[1]), "z": float(nums[2])}
    return None


def _extract_mcp_data(payload: dict[str, Any]) -> Any:
    """從 MineMCP tools/call 回應抽出結構化資料；乾跑/失敗回 None。"""
    if not payload.get("ok") or payload.get("dry_run"):
        return None
    text = str(payload.get("text") or "").strip()
    if text:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_text": text}
    result = payload.get("result")
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    try:
                        return json.loads(str(item["text"]))
                    except json.JSONDecodeError:
                        return {"raw_text": str(item["text"])}
        return result
    return None


def _normalize_item(entry: Any) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    name = (
        entry.get("type")
        or entry.get("material")
        or entry.get("id")
        or entry.get("name")
        or entry.get("item")
    )
    if not name:
        return None
    count = _safe_int(entry.get("amount") or entry.get("count"), 1) or 1
    slot = entry.get("slot")
    out: dict[str, Any] = {"name": str(name), "count": count}
    if slot is not None:
        out["slot"] = slot
    return out


def _normalize_inventory(raw: Any) -> dict[str, Any]:
    """正規化背包：slots、armor、held。"""
    slots: list[dict[str, Any]] = []
    armor: list[dict[str, Any]] = []
    held: dict[str, Any] | None = None

    if isinstance(raw, dict):
        inv = raw.get("inventory") or raw.get("items") or raw.get("contents")
        armor_raw = raw.get("armor") or raw.get("armorContents")
        held_raw = raw.get("heldItem") or raw.get("held_item") or raw.get("mainHand") or raw.get("itemInHand")
        if inv is None and any(k in raw for k in ("main", "hotbar", "storage")):
            inv = raw
        if isinstance(inv, dict):
            for key, val in inv.items():
                if key in {"armor", "heldItem", "held_item"}:
                    continue
                item = _normalize_item(val if isinstance(val, dict) else {"type": val})
                if item:
                    item["slot"] = item.get("slot", key)
                    slots.append(item)
        elif isinstance(inv, list):
            for idx, entry in enumerate(inv):
                item = _normalize_item(entry)
                if item:
                    if item.get("slot") is None:
                        item["slot"] = idx
                    slots.append(item)
        if isinstance(armor_raw, list):
            for entry in armor_raw:
                item = _normalize_item(entry)
                if item:
                    armor.append(item)
        elif isinstance(armor_raw, dict):
            for slot, entry in armor_raw.items():
                item = _normalize_item(entry if isinstance(entry, dict) else {"type": entry})
                if item:
                    item["slot"] = slot
                    armor.append(item)
        held = _normalize_item(held_raw if isinstance(held_raw, dict) else {"type": held_raw})
    elif isinstance(raw, list):
        for idx, entry in enumerate(raw):
            item = _normalize_item(entry)
            if item:
                item["slot"] = idx
                slots.append(item)

    return {"slots": slots, "armor": armor, "held": held}


def _inventory_fingerprint(inv: dict[str, Any]) -> str:
    parts: list[str] = []
    for bucket in ("slots", "armor"):
        for item in inv.get(bucket) or []:
            parts.append(f"{item.get('slot')}:{item.get('name')}:{item.get('count')}")
    held = inv.get("held")
    if held:
        parts.append(f"held:{held.get('name')}:{held.get('count')}")
    blob = "|".join(sorted(parts))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _inventory_summary(inv: dict[str, Any], max_items: int = 12) -> list[dict[str, Any]]:
    """AI 用精簡物品摘要（名稱+數量，無 NBT）。"""
    counts: dict[str, int] = {}
    for bucket in ("slots", "armor"):
        for item in inv.get(bucket) or []:
            name = str(item.get("name") or "")
            if not name:
                continue
            counts[name] = counts.get(name, 0) + int(item.get("count") or 1)
    held = inv.get("held")
    if held and held.get("name"):
        name = str(held["name"])
        counts[name] = counts.get(name, 0) + int(held.get("count") or 1)
    rows = [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda x: -x[1])]
    return rows[:max_items]


def normalize_player_record(raw: Any, *, fallback_name: str | None = None) -> dict[str, Any]:
    """將 MineMCP get_player / 列表項正規化為 Linkin 玩家摘要。"""
    now = time.time()
    if isinstance(raw, str):
        name = raw.strip()
        return {
            "id": _player_key(name),
            "name": name,
            "uuid": None,
            "online": True,
            "dimension": None,
            "world": None,
            "position": None,
            "health": None,
            "food": None,
            "gamemode": None,
            "last_seen": now,
        }

    data = raw if isinstance(raw, dict) else {}
    name = str(
        data.get("name")
        or data.get("displayName")
        or data.get("username")
        or fallback_name
        or ""
    ).strip()
    uuid_val = data.get("uuid") or data.get("uniqueId") or data.get("id")
    if uuid_val and str(uuid_val).startswith("Player-"):
        uuid_val = None

    loc = data.get("location") or data.get("position") or data.get("loc") or data.get("coords")
    pos = _parse_xyz(loc)
    dimension = (
        data.get("dimension")
        or data.get("world")
        or (loc.get("world") if isinstance(loc, dict) else None)
        or (loc.get("dimension") if isinstance(loc, dict) else None)
    )
    health = _safe_float(data.get("health"))
    food = _safe_float(data.get("food") or data.get("foodLevel"))
    gamemode = data.get("gamemode") or data.get("gameMode") or data.get("mode")
    inv_raw = data.get("inventory") or data.get("items") or data
    inventory = _normalize_inventory(inv_raw if isinstance(inv_raw, (dict, list)) else data)

    return {
        "id": _player_key(name or str(fallback_name or ""), str(uuid_val) if uuid_val else None),
        "name": name or fallback_name or "unknown",
        "uuid": str(uuid_val) if uuid_val else None,
        "online": bool(data.get("online", True)),
        "dimension": str(dimension) if dimension else None,
        "world": str(data.get("world") or dimension) if (data.get("world") or dimension) else None,
        "position": pos,
        "health": health,
        "food": food,
        "gamemode": str(gamemode) if gamemode is not None else None,
        "inventory": inventory,
        "inventory_summary": _inventory_summary(inventory),
        "inventory_fingerprint": _inventory_fingerprint(inventory),
        "last_seen": now,
    }


def _parse_online_players_payload(data: Any) -> list[str]:
    """從 get_online_players 回應提取玩家名列表。"""
    if data is None:
        return []
    if isinstance(data, list):
        names: list[str] = []
        for item in data:
            if isinstance(item, str) and item.strip():
                names.append(item.strip())
            elif isinstance(item, dict):
                n = item.get("name") or item.get("username")
                if n:
                    names.append(str(n).strip())
        return names
    if isinstance(data, dict):
        players = data.get("players") or data.get("online") or data.get("names")
        if isinstance(players, list):
            return _parse_online_players_payload(players)
        if isinstance(players, str):
            return [p.strip() for p in players.split(",") if p.strip()]
        raw_text = data.get("raw_text")
        if raw_text:
            return [p.strip() for p in re.split(r"[\n,]+", str(raw_text)) if p.strip()]
    if isinstance(data, str):
        return [p.strip() for p in re.split(r"[\n,]+", data) if p.strip()]
    return []


def _bridge_status() -> dict[str, Any]:
    from backend.linkin.minecraft import monitor_status

    return monitor_status()


def _record_player_event(
    *,
    action: str,
    player: dict[str, Any],
    summary: str,
    status: str = "ok",
    details: dict[str, Any] | None = None,
    bridge_offline: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    return append_minecraft_event(
        domain="player",
        action=action,
        status=status,
        summary=summary,
        details=details,
        entity_refs={"player_id": player.get("id"), "player_name": player.get("name")},
        bridge_offline=bridge_offline,
        dry_run=dry_run,
    )


def _diff_and_emit(prev: dict[str, Any] | None, current: dict[str, Any], *, bridge_offline: bool) -> None:
    """比較前後快照並寫入 move/inventory 等事件。"""
    name = current.get("name") or "unknown"
    if not prev:
        _record_player_event(
            action="join",
            player=current,
            summary=f"{name} 上線",
            details={"position": current.get("position"), "dimension": current.get("dimension")},
            bridge_offline=bridge_offline,
        )
        return

    prev_pos = prev.get("position") or {}
    cur_pos = current.get("position") or {}
    if cur_pos and prev_pos:
        moved = any(
            _safe_int(cur_pos.get(axis)) != _safe_int(prev_pos.get(axis))
            for axis in ("x", "y", "z")
        )
        if moved:
            _record_player_event(
                action="move",
                player=current,
                summary=f"{name} 移動至 ({int(cur_pos.get('x', 0))}, {int(cur_pos.get('y', 0))}, {int(cur_pos.get('z', 0))})",
                details={"from": prev_pos, "to": cur_pos, "dimension": current.get("dimension")},
                bridge_offline=bridge_offline,
            )

    prev_dim = prev.get("dimension")
    cur_dim = current.get("dimension")
    if prev_dim and cur_dim and prev_dim != cur_dim:
        _record_player_event(
            action="teleport",
            player=current,
            summary=f"{name} 維度 {prev_dim} → {cur_dim}",
            details={"from_dimension": prev_dim, "to_dimension": cur_dim},
            bridge_offline=bridge_offline,
        )

    prev_fp = prev.get("inventory_fingerprint")
    cur_fp = current.get("inventory_fingerprint")
    if prev_fp and cur_fp and prev_fp != cur_fp:
        _record_player_event(
            action="inventory",
            player=current,
            summary=f"{name} 背包變更",
            details={"inventory_summary": current.get("inventory_summary")},
            bridge_offline=bridge_offline,
        )


def sync_players_from_bridge(*, force: bool = False) -> dict[str, Any]:
    """輪詢 MineMCP 並以 diff 產生事件。回傳同步元資料。"""
    global _last_sync_ts
    from backend.tools import minecraft_mcp as mcp

    bridge = _bridge_status()
    now = time.time()
    with _lock:
        _load_state_cache()
        if not force and (now - _last_sync_ts) < _MIN_SYNC_INTERVAL:
            return {
                "synced": False,
                "reason": "throttled",
                "bridge_offline": not bridge.get("connected"),
                "dry_run": bridge.get("dry_run"),
                "online_count": sum(1 for p in _state_cache.values() if p.get("online")),
            }
        _last_sync_ts = now

    if bridge.get("dry_run") or not bridge.get("enabled"):
        return {
            "synced": False,
            "reason": "dry_run" if bridge.get("dry_run") else "disabled",
            "bridge_offline": True,
            "dry_run": bool(bridge.get("dry_run")),
            "online_count": 0,
        }

    if not bridge.get("connected"):
        return {
            "synced": False,
            "reason": "bridge_offline",
            "bridge_offline": True,
            "dry_run": False,
            "online_count": 0,
        }

    online_payload = mcp.get_online_players()
    online_data = _extract_mcp_data(online_payload)
    names = _parse_online_players_payload(online_data)
    bridge_offline = not online_payload.get("ok")

    current: dict[str, dict[str, Any]] = {}
    for name in names:
        detail_payload = mcp.get_player(name)
        detail_data = _extract_mcp_data(detail_payload)
        if detail_data is None and detail_payload.get("ok"):
            detail_data = {"name": name, "online": True}
        record = normalize_player_record(detail_data or {"name": name, "online": True}, fallback_name=name)
        record["online"] = True
        record["last_seen"] = now
        current[record["id"]] = record

    with _lock:
        prev_online_ids = {pid for pid, p in _state_cache.items() if p.get("online")}
        cur_online_ids = set(current.keys())

        for pid in prev_online_ids - cur_online_ids:
            prev = _state_cache.get(pid, {})
            prev["online"] = False
            prev["last_seen"] = now
            _record_player_event(
                action="quit",
                player=prev,
                summary=f"{prev.get('name', pid)} 下線",
                bridge_offline=bridge_offline,
            )

        for pid, record in current.items():
            cached = _state_cache.get(pid)
            _diff_and_emit(cached, record, bridge_offline=bridge_offline)
            _state_cache[pid] = record

        for pid, prev in list(_state_cache.items()):
            if pid not in current and prev.get("online"):
                prev = dict(prev)
                prev["online"] = False
                prev["last_seen"] = now
                _state_cache[pid] = prev

        _save_state_cache()

    return {
        "synced": True,
        "reason": "ok",
        "bridge_offline": bridge_offline,
        "dry_run": False,
        "online_count": len(current),
    }


def list_players_snapshot(*, sync: bool = True) -> dict[str, Any]:
    """線上玩家列表 + 橋接狀態（可選觸發 sync）。"""
    bridge = _bridge_status()
    if sync:
        sync_players_from_bridge()
    with _lock:
        _load_state_cache()
        online = [dict(p) for p in _state_cache.values() if p.get("online")]
        online.sort(key=lambda p: str(p.get("name") or ""))

    summaries = []
    for p in online:
        summaries.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "uuid": p.get("uuid"),
                "dimension": p.get("dimension"),
                "world": p.get("world"),
                "position": p.get("position"),
                "health": p.get("health"),
                "food": p.get("food"),
                "gamemode": p.get("gamemode"),
                "last_seen": p.get("last_seen"),
                "inventory_summary": p.get("inventory_summary") or [],
            }
        )

    return {
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
            "live": bridge.get("live"),
        },
        "bridge_offline": bool(bridge.get("dry_run") or (bridge.get("enabled") and not bridge.get("connected"))),
        "online_count": len(summaries),
        "players": summaries,
        "generated_at": time.time(),
    }


def get_player_detail(player_id: str, *, sync: bool = False) -> dict[str, Any]:
    """單一玩家詳情（含背包 grid）。"""
    key = str(player_id or "").strip().lower()
    bridge = _bridge_status()

    if sync and bridge.get("connected") and not bridge.get("dry_run"):
        sync_players_from_bridge(force=True)

    with _lock:
        _load_state_cache()
        record = _state_cache.get(key)
        if not record:
            for pid, p in _state_cache.items():
                if str(p.get("name") or "").lower() == key or str(p.get("uuid") or "").lower() == key:
                    record = p
                    key = pid
                    break

    if not record and bridge.get("connected") and not bridge.get("dry_run"):
        from backend.tools import minecraft_mcp as mcp

        payload = mcp.get_player(player_id)
        data = _extract_mcp_data(payload)
        if data is not None or payload.get("ok"):
            record = normalize_player_record(data or {"name": player_id}, fallback_name=player_id)
            with _lock:
                _state_cache[record["id"]] = record
                _save_state_cache()

    if not record:
        return {
            "ok": False,
            "error": "player_not_found",
            "bridge_offline": bool(bridge.get("dry_run") or not bridge.get("connected")),
            "player": None,
        }

    inv = record.get("inventory") or {}
    return {
        "ok": True,
        "bridge_offline": bool(bridge.get("dry_run") or (bridge.get("enabled") and not bridge.get("connected"))),
        "player": {
            "id": record.get("id"),
            "name": record.get("name"),
            "uuid": record.get("uuid"),
            "online": record.get("online"),
            "dimension": record.get("dimension"),
            "world": record.get("world"),
            "position": record.get("position"),
            "health": record.get("health"),
            "food": record.get("food"),
            "gamemode": record.get("gamemode"),
            "last_seen": record.get("last_seen"),
            "inventory": inv,
            "inventory_summary": record.get("inventory_summary") or _inventory_summary(inv),
            "held": inv.get("held"),
            "armor": inv.get("armor") or [],
            "slots": inv.get("slots") or [],
        },
    }


def list_player_events(
    *,
    since: float | None = None,
    cursor: str | None = None,
    limit: int = 50,
    player_id: str | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """分頁列出 domain=player 的活動事件。"""
    page = list_minecraft_events(since=since, cursor=cursor, limit=limit, domain="player")
    filtered = list(page.get("events") or [])
    if player_id:
        pid = player_id.lower()
        filtered = [
            e
            for e in filtered
            if str((e.get("entity_refs") or {}).get("player_id") or "").lower() == pid
            or str((e.get("entity_refs") or {}).get("player_name") or "").lower() == pid
        ]
    if action:
        filtered = [e for e in filtered if str(e.get("action")) == action]
    return {
        "events": filtered,
        "count": len(filtered),
        "total": page.get("total"),
        "next_cursor": page.get("next_cursor"),
        "has_more": page.get("has_more"),
    }


_INGEST_ACTIONS = frozenset(
    {
        "join",
        "quit",
        "move",
        "chat",
        "death",
        "inventory",
        "teleport",
        "pickup",
        "drop",
        "block_break",
        "block_place",
    }
)


def validate_ingest_body(body: dict[str, Any]) -> str | None:
    """驗證 ingest payload；回傳 error code 或 None。"""
    if not isinstance(body, dict):
        return "invalid_body"
    action = str(body.get("action") or body.get("type") or "").strip().lower()
    if not action:
        return "missing_action"
    if action not in _INGEST_ACTIONS:
        return f"unsupported_action:{action}"

    name = str(body.get("player") or body.get("player_name") or body.get("name") or "").strip()
    if not name:
        return "missing_player"
    if len(name) > 64:
        return "player_name_too_long"

    raw_details = body.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    message = body.get("message") or body.get("summary") or details.get("message")
    block = body.get("block") or details.get("block")

    if action == "chat" and not str(message or "").strip():
        return "chat_requires_message"
    if action in {"block_break", "block_place"} and not block:
        return "block_action_requires_block"
    if action == "death" and not str(body.get("summary") or message or "").strip():
        return "death_requires_summary"
    return None


def ingest_player_event(body: dict[str, Any]) -> dict[str, Any]:
    """外部插件 webhook：追加玩家活動（chat/death/block 等）。"""
    err = validate_ingest_body(body)
    if err:
        return {"ok": False, "error": err}

    action = str(body.get("action") or body.get("type") or "").strip().lower()
    name = str(body.get("player") or body.get("player_name") or body.get("name") or "unknown").strip()
    player_id = str(body.get("player_id") or body.get("uuid") or _player_key(name))
    summary = str(body.get("summary") or body.get("message") or f"{name} {action}").strip()
    raw_details = body.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    for key in ("message", "position", "item", "block", "dimension", "cause", "killer"):
        if key in body and key not in details:
            details[key] = body[key]
    details["source"] = "ingest"

    evt = _record_player_event(
        action=action,
        player={"id": player_id, "name": name},
        summary=summary,
        status=str(body.get("status") or "ok"),
        details=details,
        bridge_offline=bool(body.get("bridge_offline")),
        dry_run=bool(body.get("dry_run")),
    )
    return {"ok": True, "event": evt}


def has_live_player_signal() -> bool:
    """是否有在線玩家或近期玩家活動（供 AI 上下文門控）。"""
    block = build_players_ai_block(max_players=1, max_events=3)
    if int(block.get("online_count") or 0) > 0:
        return True
    return bool(block.get("recent_activity"))


def format_players_presence_markdown(
    *,
    max_players: int = 6,
    max_events: int = 5,
    max_chars: int = 1200,
) -> str:
    """精簡「玩家現場」Markdown（token 預算友好）。"""
    block = build_players_ai_block(max_players=max_players, max_events=max_events)
    online = int(block.get("online_count") or 0)
    recent = block.get("recent_activity") or []
    if online <= 0 and not recent:
        return ""

    lines = ["## 玩家現場"]
    if block.get("bridge_offline") and online <= 0:
        lines.append("- 橋接離線 — 僅顯示外部 ingest 活動")
    if online > 0:
        lines.append(f"- 在線 {online} 人")
        for player in (block.get("players") or [])[:max_players]:
            pos = player.get("position") or {}
            pos_txt = (
                f" ({int(pos.get('x', 0))}, {int(pos.get('y', 0))}, {int(pos.get('z', 0))})"
                if pos
                else ""
            )
            dim = player.get("dimension") or player.get("world") or "?"
            inv = player.get("inventory_summary") or []
            inv_txt = ", ".join(f"{i.get('name')}×{i.get('count')}" for i in inv[:3]) if inv else "—"
            lines.append(f"- {player.get('name')} [{dim}]{pos_txt} 背包={inv_txt}")
    for line in (block.get("activity_lines") or [])[:max_events]:
        lines.append(f"- 活動：{line}")

    text = "\n".join(lines).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 20].rstrip() + "\n…(truncated)"
    return text


def build_players_ai_block(*, max_players: int = 8, max_events: int = 6) -> dict[str, Any]:
    """供 snapshot/context 使用的玩家現場摘要。"""
    snap = list_players_snapshot(sync=False)
    bridge_offline = snap.get("bridge_offline")
    players = (snap.get("players") or [])[:max_players]
    events_page = list_player_events(limit=max_events * 3)
    recent = (events_page.get("events") or [])[-max_events:]
    recent.reverse()

    activity_lines = []
    for evt in recent:
        refs = evt.get("entity_refs") or {}
        pname = refs.get("player_name") or "?"
        activity_lines.append(f"{pname} {evt.get('action')}: {evt.get('summary')}")

    return {
        "bridge_offline": bridge_offline,
        "online_count": snap.get("online_count", 0),
        "players": players,
        "recent_activity": recent,
        "activity_lines": activity_lines,
    }


__all__ = [
    "build_players_ai_block",
    "format_players_presence_markdown",
    "get_player_detail",
    "has_live_player_signal",
    "ingest_player_event",
    "list_player_events",
    "list_players_snapshot",
    "normalize_player_record",
    "reset_player_state",
    "sync_players_from_bridge",
    "validate_ingest_body",
]
