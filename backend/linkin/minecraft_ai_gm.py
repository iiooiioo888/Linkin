"""Minecraft AI Game Master：玩家事件驅動任務進度與 NPC 回應。

讀取世界上下文 → LLM 結構化決策 → 可選經橋接執行（預設 dry-run）。
決策與執行結果寫入 ``minecraft_gm_runs.jsonl`` 與 ``minecraft_events``（domain=gm）。
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from backend.linkin.minecraft_observability import append_minecraft_event, list_minecraft_events
from backend.linkin.narrative_starter import _extract_json_object, _llm_ready

logger = logging.getLogger(__name__)

TRACE_LABEL = "minecraft_ai_gm"

ALLOWED_ACTION_TYPES = frozenset({"quest_progress", "npc_say", "hint", "noop"})
REACT_ACTIONS = frozenset(
    {
        "join",
        "quit",
        "chat",
        "death",
        "inventory",
        "pickup",
        "drop",
        "block_break",
        "block_place",
    }
)
FORBIDDEN_ACTION_KEYS = frozenset(
    {
        "place_block",
        "break_block",
        "fill_block",
        "destroy",
        "write_file",
        "command",
        "execute",
        "fill",
        "blocks",
    }
)

_lock = threading.Lock()
_last_react_by_player: dict[str, float] = {}

_DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "auto_apply": False,
    "dry_run": True,
    "max_actions_per_event": 3,
    "cooldown_seconds": 30.0,
}


def _data_dir() -> Path:
    return Path(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin"))


def _config_path() -> Path:
    return _data_dir() / "minecraft_gm_config.json"


def _state_path() -> Path:
    return _data_dir() / "minecraft_gm_state.json"


def _runs_path() -> Path:
    return _data_dir() / "minecraft_gm_runs.jsonl"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def reset_gm_state() -> None:
    """測試用：清空 GM 狀態、設定與執行紀錄。"""
    global _last_react_by_player
    with _lock:
        _last_react_by_player = {}
        for path in (_config_path(), _state_path(), _runs_path()):
            if path.exists():
                path.unlink()


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_gm_config() -> dict[str, Any]:
    """合併環境變數與持久化設定。"""
    stored = _load_json_file(_config_path())
    cfg = {**_DEFAULT_CONFIG, **stored}
    if _env_bool("EVOL_MC_GM_ENABLED"):
        cfg["enabled"] = True
    if os.getenv("EVOL_MC_GM_AUTO_APPLY", "").strip():
        cfg["auto_apply"] = _env_bool("EVOL_MC_GM_AUTO_APPLY", False)
    if os.getenv("EVOL_MC_GM_DRY_RUN", "").strip():
        cfg["dry_run"] = _env_bool("EVOL_MC_GM_DRY_RUN", True)
    cooldown = os.getenv("EVOL_MC_GM_COOLDOWN_SECONDS", "").strip()
    if cooldown:
        try:
            cfg["cooldown_seconds"] = float(cooldown)
        except ValueError:
            pass
    max_actions = os.getenv("EVOL_MC_GM_MAX_ACTIONS", "").strip()
    if max_actions:
        try:
            cfg["max_actions_per_event"] = int(max_actions)
        except ValueError:
            pass
    return cfg


def update_gm_config(patch: dict[str, Any]) -> dict[str, Any]:
    """更新持久化 GM 設定（不覆寫未提供欄位）。"""
    allowed = {"enabled", "auto_apply", "dry_run", "max_actions_per_event", "cooldown_seconds"}
    stored = _load_json_file(_config_path())
    for key in allowed:
        if key in patch:
            stored[key] = patch[key]
    _save_json_file(_config_path(), stored)
    return get_gm_config()


def _load_state() -> dict[str, Any]:
    return _load_json_file(_state_path())


def _save_state(state: dict[str, Any]) -> None:
    _save_json_file(_state_path(), state)


def _append_run(record: dict[str, Any]) -> dict[str, Any]:
    path = _runs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _lock, path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return record


def _read_runs(limit: int = 50) -> list[dict[str, Any]]:
    path = _runs_path()
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
    rows.sort(key=lambda r: float(r.get("ts") or 0))
    return rows[-limit:]


def list_gm_runs(limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 200))
    runs = _read_runs(limit)
    runs.reverse()
    return {"runs": runs, "count": len(runs)}


def _player_id_from_event(event: dict[str, Any]) -> str:
    refs = event.get("entity_refs") or {}
    return str(refs.get("player_id") or refs.get("player_name") or "").lower()


def _is_on_cooldown(player_id: str, cooldown: float) -> bool:
    if not player_id:
        return False
    last = _last_react_by_player.get(player_id, 0.0)
    return (time.time() - last) < cooldown


def _mark_reacted(player_id: str) -> None:
    if player_id:
        _last_react_by_player[player_id] = time.time()


def _is_processed(event_id: str) -> bool:
    state = _load_state()
    processed = state.get("processed_event_ids") or []
    return str(event_id) in processed


def _mark_processed(event_id: str) -> None:
    state = _load_state()
    processed = list(state.get("processed_event_ids") or [])
    if event_id not in processed:
        processed.append(event_id)
    state["processed_event_ids"] = processed[-500:]
    state["last_tick_ts"] = time.time()
    _save_state(state)


def validate_gm_actions(actions: list[Any], *, max_actions: int) -> list[dict[str, Any]]:
    """安全過濾：僅允許白名單動作類型，拒絕破壞性欄位。"""
    safe: list[dict[str, Any]] = []
    for raw in actions[: max(0, max_actions)]:
        if not isinstance(raw, dict):
            continue
        action_type = str(raw.get("type") or "").strip().lower()
        if action_type not in ALLOWED_ACTION_TYPES:
            continue
        if any(key in raw for key in FORBIDDEN_ACTION_KEYS):
            continue
        if action_type == "noop":
            safe.append({"type": "noop"})
            continue
        cleaned: dict[str, Any] = {"type": action_type}
        for key, val in raw.items():
            if key == "type":
                continue
            if key in FORBIDDEN_ACTION_KEYS:
                continue
            if isinstance(val, (str, int, float, bool)) or val is None:
                cleaned[key] = val
            elif isinstance(val, dict):
                cleaned[key] = {str(k): v for k, v in val.items() if isinstance(v, (str, int, float, bool))}
        safe.append(cleaned)
    return safe[:max_actions]


def build_gm_context(event: dict[str, Any] | None = None) -> dict[str, Any]:
    """從 AI snapshot 風格資料構建 GM 精簡上下文。"""
    from backend.linkin.knowledge import list_entities
    from backend.linkin.minecraft import monitor_status
    from backend.linkin.minecraft_players import build_players_ai_block

    bridge = monitor_status()
    players_block = build_players_ai_block(max_players=6, max_events=4)
    quests = list_entities("quests")
    npcs = list_entities("npcs")
    active_quests = [
        {
            "id": q.get("id"),
            "title": q.get("title"),
            "player_id": q.get("player_id"),
            "region": q.get("region"),
            "description": (str(q.get("description") or ""))[:200],
            "gm_progress": q.get("gm_progress") or [],
        }
        for q in quests
    ][:8]
    nearby_npcs = [
        {
            "id": n.get("id"),
            "name": n.get("name"),
            "location": n.get("location"),
            "occupation": n.get("occupation"),
            "world_status": n.get("world_status"),
        }
        for n in npcs
    ][:8]

    ctx: dict[str, Any] = {
        "bridge": {
            "enabled": bridge.get("enabled"),
            "connected": bridge.get("connected"),
            "dry_run": bridge.get("dry_run"),
        },
        "players": players_block,
        "active_quests": active_quests,
        "npcs": nearby_npcs,
        "trigger_event": event,
    }
    return ctx


def _build_gm_prompt(context: dict[str, Any], event: dict[str, Any]) -> str:
    refs = event.get("entity_refs") or {}
    player_name = refs.get("player_name") or "?"
    action = event.get("action") or "?"
    summary = event.get("summary") or ""
    details = event.get("details") or {}

    quests_text = json.dumps(context.get("active_quests") or [], ensure_ascii=False)[:1500]
    npcs_text = json.dumps(context.get("npcs") or [], ensure_ascii=False)[:800]
    players_text = json.dumps(
        (context.get("players") or {}).get("players") or [],
        ensure_ascii=False,
    )[:600]

    return (
        "你是 Minecraft RPG 的 AI 遊戲主持人（GM）。根據玩家事件決定少量、安全的回應動作。\n"
        "只輸出 JSON：{\"rationale\":\"...\",\"actions\":[...]}\n"
        "允許的 action.type：quest_progress、npc_say、hint、noop。\n"
        "禁止：place_block、break_block、fill、大規模破壞、任意 execute_command。\n"
        "quest_progress 欄位：quest_id, objective, status(advance|complete), note。\n"
        "npc_say 欄位：npc_name, message, target_player（可選）。\n"
        "hint 欄位：message, target_player（可選，僅面板提示）。\n"
        "最多 3 個 actions；若無需回應請用 noop。\n\n"
        f"觸發事件：玩家={player_name} action={action} summary={summary}\n"
        f"事件詳情：{json.dumps(details, ensure_ascii=False)[:400]}\n"
        f"在線玩家：{players_text}\n"
        f"活躍任務：{quests_text}\n"
        f"已知 NPC：{npcs_text}\n"
    )


def decide_gm_actions(context: dict[str, Any], event: dict[str, Any], *, max_actions: int = 3) -> dict[str, Any]:
    """呼叫 LLM 產生結構化 GM 動作（經計量路由）。"""
    if not _llm_ready():
        return {
            "rationale": "LLM 未配置，跳過 GM 決策",
            "actions": [{"type": "noop"}],
            "source": "unavailable",
        }

    try:
        from backend.core.llm import call_llm

        try:
            from backend.linkin.prompts import inherit_prompt

            system = inherit_prompt("narrative_director")
        except Exception:
            system = "你是靈境·Linkin 的敘事總監與遊戲主持人。"
        system = (
            f"{system}\n"
            "你只輸出嚴格 JSON 物件，不要 markdown 程式碼區塊、不要解釋文字。"
            "動作必須安全、小規模，不得破壞世界方塊。"
        )
        prompt = _build_gm_prompt(context, event)
        raw = (call_llm(prompt, system=system, trace_label=TRACE_LABEL) or "").strip()
    except Exception as exc:
        logger.warning("GM LLM 呼叫失敗", exc_info=True)
        return {
            "rationale": f"LLM 呼叫失敗：{exc}",
            "actions": [{"type": "noop"}],
            "source": "error",
        }

    parsed = _extract_json_object(raw)
    if not parsed:
        return {
            "rationale": "LLM 回傳無法解析",
            "actions": [{"type": "noop"}],
            "source": "parse_failed",
        }

    actions = validate_gm_actions(parsed.get("actions") or [], max_actions=max_actions)
    if not actions:
        actions = [{"type": "noop"}]
    return {
        "rationale": str(parsed.get("rationale") or "").strip()[:500],
        "actions": actions,
        "source": "llm",
    }


def _apply_quest_progress(action: dict[str, Any], *, dry_run: bool) -> dict[str, Any]:
    from backend.linkin.knowledge import list_entities, upsert_entity

    quest_id = str(action.get("quest_id") or "").strip()
    if not quest_id:
        return {"ok": False, "status": "skipped", "reason": "missing_quest_id"}
    quest = next((q for q in list_entities("quests") if str(q.get("id")) == quest_id), None)
    if not quest:
        return {"ok": False, "status": "skipped", "reason": "quest_not_found"}
    if dry_run:
        return {"ok": True, "status": "dry_run", "quest_id": quest_id}
    progress = list(quest.get("gm_progress") or [])
    progress.append(
        {
            "ts": time.time(),
            "objective": str(action.get("objective") or ""),
            "status": str(action.get("status") or "advance"),
            "note": str(action.get("note") or "")[:200],
        }
    )
    patch: dict[str, Any] = {"gm_progress": progress[-20:]}
    if str(action.get("status") or "") == "complete":
        patch["gm_status"] = "completed"
    saved = upsert_entity("quests", {**quest, **patch})
    return {"ok": True, "status": "applied", "quest_id": quest_id, "quest": saved}


def _tellraw_message(message: str, target: str | None = None) -> str:
    prefix = "[GM] "
    text = f"{prefix}{message}"
    payload = json.dumps({"text": text}, ensure_ascii=False)
    if target and target.strip():
        return f'tellraw {target.strip()} {payload}'
    return f"tellraw @a {payload}"


def _apply_npc_say(action: dict[str, Any], *, dry_run: bool, bridge: dict[str, Any]) -> dict[str, Any]:
    message = str(action.get("message") or "").strip()
    if not message:
        return {"ok": False, "status": "skipped", "reason": "empty_message"}
    npc_name = str(action.get("npc_name") or "NPC").strip()
    full_msg = f"{npc_name}：{message}"
    target = action.get("target_player")

    if dry_run or bridge.get("dry_run") or not bridge.get("connected"):
        return {
            "ok": True,
            "status": "log_only",
            "message": full_msg,
            "bridge_offline": not bridge.get("connected"),
        }

    from backend.tools import minecraft_mcp as mcp

    cmd = _tellraw_message(full_msg, str(target) if target else None)
    result = mcp.execute_command(cmd, role="minecraft_ai_gm")
    if not result.get("ok"):
        return {
            "ok": False,
            "status": "partial",
            "message": full_msg,
            "bridge_error": result.get("error") or result.get("message"),
        }
    return {"ok": True, "status": "applied", "message": full_msg, "command": cmd}


def _apply_hint(action: dict[str, Any]) -> dict[str, Any]:
    message = str(action.get("message") or "").strip()
    if not message:
        return {"ok": False, "status": "skipped", "reason": "empty_message"}
    return {"ok": True, "status": "log_only", "message": message}


def apply_gm_actions(
    actions: list[dict[str, Any]],
    *,
    dry_run: bool,
    auto_apply: bool,
    trigger_event: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """執行 GM 動作；bridge 離線時 npc_say 降級為 log_only。"""
    from backend.linkin.minecraft import monitor_status

    bridge = monitor_status()
    effective_dry_run = dry_run or not auto_apply
    results: list[dict[str, Any]] = []

    for action in actions:
        action_type = str(action.get("type") or "noop")
        if action_type == "noop":
            results.append({"type": "noop", "status": "noop"})
            continue
        if action_type == "quest_progress":
            out = _apply_quest_progress(action, dry_run=effective_dry_run)
            results.append({"type": "quest_progress", **out})
            continue
        if action_type == "npc_say":
            out = _apply_npc_say(action, dry_run=effective_dry_run, bridge=bridge)
            results.append({"type": "npc_say", **out})
            continue
        if action_type == "hint":
            out = _apply_hint(action)
            results.append({"type": "hint", **out})
            continue
        results.append({"type": action_type, "status": "denied"})

    return results


def _log_gm_decision(
    *,
    run_id: str,
    event: dict[str, Any],
    rationale: str,
    actions: list[dict[str, Any]],
    apply_results: list[dict[str, Any]],
    dry_run: bool,
    status: str,
) -> dict[str, Any]:
    player_id = _player_id_from_event(event)
    applied = any(r.get("status") == "applied" for r in apply_results)
    summary_parts = [str(a.get("type")) for a in actions if a.get("type") != "noop"]
    summary = rationale[:80] if rationale else (", ".join(summary_parts) or "noop")

    evt = append_minecraft_event(
        domain="gm",
        action="react",
        status=status,
        summary=summary,
        details={
            "run_id": run_id,
            "rationale": rationale,
            "actions": actions,
            "apply_results": apply_results,
            "trigger_event_id": event.get("id"),
            "dry_run": dry_run,
            "applied": applied,
        },
        entity_refs={
            "player_id": player_id,
            "player_name": (event.get("entity_refs") or {}).get("player_name"),
        },
        dry_run=dry_run,
    )
    return evt


def react_to_event(
    event: dict[str, Any],
    *,
    force: bool = False,
    skip_cooldown: bool = False,
) -> dict[str, Any]:
    """對單一玩家事件執行 GM 決策迴圈。"""
    cfg = get_gm_config()
    if not cfg.get("enabled") and not force:
        return {"ok": False, "error": "gm_disabled"}

    event_id = str(event.get("id") or "")
    action = str(event.get("action") or "")
    if event.get("domain") != "player" and not force:
        return {"ok": False, "error": "not_player_event"}
    if action not in REACT_ACTIONS and not force:
        return {"ok": False, "error": f"action_not_reactive:{action}"}

    player_id = _player_id_from_event(event)
    cooldown = float(cfg.get("cooldown_seconds") or 30)
    if not skip_cooldown and _is_on_cooldown(player_id, cooldown):
        return {"ok": False, "error": "cooldown", "player_id": player_id}

    if event_id and _is_processed(event_id) and not force:
        return {"ok": False, "error": "already_processed", "event_id": event_id}

    max_actions = int(cfg.get("max_actions_per_event") or 3)
    dry_run = bool(cfg.get("dry_run", True))
    auto_apply = bool(cfg.get("auto_apply", False))

    context = build_gm_context(event)
    decision = decide_gm_actions(context, event, max_actions=max_actions)
    actions = decision.get("actions") or [{"type": "noop"}]
    apply_results = apply_gm_actions(
        actions,
        dry_run=dry_run,
        auto_apply=auto_apply,
        trigger_event=event,
    )

    applied_any = any(r.get("status") == "applied" for r in apply_results)
    bridge_offline = any(r.get("bridge_offline") for r in apply_results)
    if dry_run or not auto_apply:
        status = "dry_run"
    elif applied_any:
        status = "ok"
    elif bridge_offline:
        status = "partial"
    else:
        status = "ok" if all(r.get("status") in {"noop", "log_only", "applied"} for r in apply_results) else "partial"

    run_id = f"gmrun-{uuid.uuid4().hex[:12]}"
    run_record = {
        "id": run_id,
        "ts": time.time(),
        "trigger_event_id": event_id,
        "player_id": player_id,
        "player_name": (event.get("entity_refs") or {}).get("player_name"),
        "trigger_action": action,
        "rationale": decision.get("rationale"),
        "actions": actions,
        "apply_results": apply_results,
        "dry_run": dry_run,
        "auto_apply": auto_apply,
        "applied": applied_any,
        "status": status,
        "source": decision.get("source"),
    }
    _append_run(run_record)
    _log_gm_decision(
        run_id=run_id,
        event=event,
        rationale=str(decision.get("rationale") or ""),
        actions=actions,
        apply_results=apply_results,
        dry_run=dry_run,
        status=status,
    )

    if event_id:
        _mark_processed(event_id)
    if not skip_cooldown:
        _mark_reacted(player_id)

    return {"ok": True, "run": run_record}


def react_to_event_id(event_id: str, *, force: bool = False) -> dict[str, Any]:
    """依事件 id 查找並 react。"""
    page = list_minecraft_events(limit=200)
    for evt in reversed(page.get("events") or []):
        if str(evt.get("id")) == event_id:
            return react_to_event(evt, force=force)
    return {"ok": False, "error": "event_not_found", "event_id": event_id}


def gm_tick(limit: int = 5) -> dict[str, Any]:
    """處理尚未處理的玩家事件（批次 tick）。"""
    cfg = get_gm_config()
    if not cfg.get("enabled"):
        return {"ok": False, "error": "gm_disabled", "processed": 0}

    page = list_minecraft_events(limit=100, domain="player")
    candidates = [
        e
        for e in (page.get("events") or [])
        if str(e.get("action")) in REACT_ACTIONS and not _is_processed(str(e.get("id") or ""))
    ]
    candidates = candidates[-limit:]
    results: list[dict[str, Any]] = []
    for evt in candidates:
        res = react_to_event(evt)
        results.append(res)

    return {
        "ok": True,
        "processed": len(results),
        "results": results,
    }


def maybe_auto_react(event: dict[str, Any]) -> None:
    """事件寫入後的可選自動觸發（不拋出例外）。"""
    try:
        cfg = get_gm_config()
        if not cfg.get("enabled"):
            return
        action = str(event.get("action") or "")
        if action not in REACT_ACTIONS:
            return
        react_to_event(event)
    except Exception:
        logger.warning("GM auto-react 失敗", exc_info=True)


__all__ = [
    "ALLOWED_ACTION_TYPES",
    "REACT_ACTIONS",
    "TRACE_LABEL",
    "apply_gm_actions",
    "build_gm_context",
    "decide_gm_actions",
    "get_gm_config",
    "gm_tick",
    "list_gm_runs",
    "maybe_auto_react",
    "react_to_event",
    "react_to_event_id",
    "reset_gm_state",
    "update_gm_config",
    "validate_gm_actions",
]
