"""Minecraft 情境規則引擎（決定性、無 LLM）。

讀取 ``minecraft_situation`` 四維快照，產出安全調整建議；可選自動套用僅限
log-only 動作（hint / player_assist / region_focus），遵守 dry-run 護欄。
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

_SAFE_AUTO_ACTIONS = frozenset({"hint", "player_assist", "region_focus", "noop"})
_LOG_ONLY_ACTIONS = frozenset({"hint", "player_assist", "region_focus"})


def _data_dir() -> Path:
    return Path(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin"))


def _rules_log_path() -> Path:
    return _data_dir() / "minecraft_situation_rules.jsonl"


def _region_focus_path() -> Path:
    return _data_dir() / "minecraft_region_focus.json"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def rules_enabled() -> bool:
    """預設啟用（僅建議，不自動套用）。"""
    return _env_bool("EVOL_MC_GM_RULES_ENABLED", True)


def rules_auto_apply_enabled() -> bool:
    """僅套用 log-only 安全動作；仍受 GM dry_run / auto_apply 護欄約束。"""
    return _env_bool("EVOL_MC_GM_RULES_AUTO_APPLY", False)


def reset_rules_state() -> None:
    """測試用：清空規則日誌與區域焦點。"""
    with _lock:
        for path in (_rules_log_path(), _region_focus_path()):
            if path.exists():
                path.unlink()


def _sig_val(dim: dict[str, Any], name: str) -> Any:
    for s in dim.get("signals") or []:
        if isinstance(s, dict) and s.get("name") == name:
            return s.get("value")
    return None


def _load_region_focus() -> dict[str, Any]:
    path = _region_focus_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_region_focus(data: dict[str, Any]) -> dict[str, Any]:
    path = _region_focus_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def get_region_focus() -> dict[str, Any]:
    with _lock:
        return _load_region_focus()


def set_region_focus(marker: dict[str, Any]) -> dict[str, Any]:
    """寫入區域焦點標記（log-only，不修改地形）。"""
    with _lock:
        return _save_region_focus(marker)


def _append_rule_run(record: dict[str, Any]) -> dict[str, Any]:
    path = _rules_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    with _lock, path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    return record


def list_rule_runs(limit: int = 20) -> list[dict[str, Any]]:
    path = _rules_log_path()
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
    limit = max(1, min(int(limit or 20), 100))
    return list(reversed(rows[-limit:]))


def _recommendation(
    *,
    rule_id: str,
    action_type: str,
    message: str,
    rationale: str,
    priority: int = 50,
    auto_apply_safe: bool = False,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": rule_id,
        "action_type": action_type,
        "message": message,
        "rationale": rationale,
        "priority": priority,
        "auto_apply_safe": auto_apply_safe and action_type in _SAFE_AUTO_ACTIONS,
        "payload": payload or {},
    }


def evaluate_situation_rules(snap: dict[str, Any] | None = None) -> dict[str, Any]:
    """依情境快照產出規則建議（決定性）。"""
    from backend.linkin.minecraft_situation import build_situation_snapshot

    full = snap or build_situation_snapshot()
    market = full.get("market") or {}
    economy = full.get("economy") or {}
    land = full.get("land") or {}
    players = full.get("players") or {}

    recs: list[dict[str, Any]] = []

    stuck = _sig_val(players, "stuck_quest_count")
    if isinstance(stuck, int) and stuck > 0:
        examples = _sig_val(players, "stuck_quest_examples")
        player_hint = ""
        if isinstance(examples, list) and examples:
            player_hint = str(examples[0])
        recs.append(
            _recommendation(
                rule_id="stuck_quests",
                action_type="player_assist",
                message=f"{stuck} 位玩家任務可能卡住，建議 player_assist 或 hint 引導",
                rationale="多名玩家長時間無任務進度",
                priority=10,
                auto_apply_safe=True,
                payload={
                    "assist_type": "quest_unstick",
                    "target_player": player_hint,
                    "hint": "任務卡住了？試著與 NPC 對話或查看任務目標。",
                },
            )
        )

    online = _sig_val(players, "online_count")
    hotspot = _sig_val(players, "activity_hotspot_center")
    if isinstance(online, int) and online == 0:
        recs.append(
            _recommendation(
                rule_id="no_players_online",
                action_type="noop",
                message="目前無在線玩家，建議 noop 或僅記錄情境",
                rationale="玩家維度顯示在線人數為 0",
                priority=5,
                auto_apply_safe=True,
            )
        )
    elif isinstance(hotspot, dict) and isinstance(online, int) and online >= 2:
        hx = hotspot.get("x")
        hz = hotspot.get("z")
        near_spawn = False
        try:
            near_spawn = abs(float(hx or 0)) < 64 and abs(float(hz or 0)) < 64
        except (TypeError, ValueError):
            near_spawn = False
        if near_spawn:
            recs.append(
                _recommendation(
                    rule_id="spawn_cluster",
                    action_type="region_focus",
                    message="玩家聚集於出生點附近，建議 region_focus 引導至外圍區域",
                    rationale="活動熱點距出生點過近，可能造成建造密度過高",
                    priority=20,
                    auto_apply_safe=True,
                    payload={
                        "focus_mode": "away_from_spawn",
                        "hotspot": {"x": hx, "z": hz},
                        "suggested_offset_blocks": 128,
                    },
                )
            )
        else:
            recs.append(
                _recommendation(
                    rule_id="activity_hotspot",
                    action_type="region_focus",
                    message=f"玩家聚集於 ({hx}, {hz})，可將敘事焦點置於該區",
                    rationale="偵測到活動熱點",
                    priority=35,
                    auto_apply_safe=True,
                    payload={
                        "focus_mode": "at_hotspot",
                        "center": {"x": hx, "z": hz},
                    },
                )
            )

    empty_regions = _sig_val(land, "map_regions_without_briefs")
    pending_briefs = _sig_val(land, "build_briefs_pending")
    if isinstance(empty_regions, int) and empty_regions > 0 and isinstance(online, int) and online > 0:
        recs.append(
            _recommendation(
                rule_id="sparse_land_active_players",
                action_type="hint",
                message=f"{empty_regions} 個地圖區塊尚無建築意圖，可引導玩家探索或提交 map/build",
                rationale="地土稀疏且有在線玩家",
                priority=25,
                auto_apply_safe=True,
                payload={"hint": "尚有未開發區域，可考慮新增地圖計畫或建築意圖。"},
            )
        )

    if isinstance(pending_briefs, int) and pending_briefs > 0:
        recs.append(
            _recommendation(
                rule_id="pending_build_briefs",
                action_type="hint",
                message=f"尚有 {pending_briefs} 筆待建築意圖，優先推進 build apply",
                rationale="地土維度顯示待處理建築意圖",
                priority=30,
                auto_apply_safe=True,
                payload={"hint": "建築意圖待落地，可從監控面板或敘事工作區推進。"},
            )
        )

    price_index = _sig_val(economy, "price_index")
    if price_index == "unknown" or economy.get("status") == "unknown":
        recs.append(
            _recommendation(
                rule_id="economy_unknown_no_prices",
                action_type="noop",
                message="經濟／市場指標不足，勿捏造物價或通膨敘事",
                rationale="price_index 為 unknown，遵守誠實未知指標",
                priority=15,
                auto_apply_safe=True,
            )
        )

    heat = _sig_val(market, "trade_heat")
    if heat == "high":
        recs.append(
            _recommendation(
                rule_id="trade_heat_high",
                action_type="hint",
                message="交易活動頻繁，NPC 回應可提及道具流通（不臆測價格）",
                rationale="市況 trade_heat 偏高",
                priority=40,
                auto_apply_safe=True,
                payload={"hint": "市場交易活躍，可引導玩家交換或完成交易相關任務。"},
            )
        )
    elif market.get("status") == "unknown":
        recs.append(
            _recommendation(
                rule_id="market_unknown",
                action_type="noop",
                message="市況資料不足，勿臆測稀缺品價格",
                rationale="市況維度 status 為 unknown",
                priority=18,
                auto_apply_safe=True,
            )
        )

    recs.sort(key=lambda r: int(r.get("priority") or 99))
    top = recs[:8]

    return {
        "generated_at": full.get("generated_at") or time.time(),
        "enabled": rules_enabled(),
        "auto_apply_enabled": rules_auto_apply_enabled(),
        "recommendations": top,
        "region_focus": get_region_focus(),
    }


def recommendation_to_action(rec: dict[str, Any]) -> dict[str, Any]:
    """將規則建議轉為 GM 動作 payload。"""
    action_type = str(rec.get("action_type") or "noop")
    payload = rec.get("payload") or {}
    if action_type == "noop":
        return {"type": "noop"}
    if action_type == "hint":
        return {
            "type": "hint",
            "message": str(payload.get("hint") or rec.get("message") or "")[:300],
            "target_player": payload.get("target_player"),
            "source_rule": rec.get("id"),
        }
    if action_type == "player_assist":
        return {
            "type": "player_assist",
            "assist_type": str(payload.get("assist_type") or "general"),
            "message": str(payload.get("hint") or rec.get("message") or "")[:300],
            "target_player": payload.get("target_player"),
            "source_rule": rec.get("id"),
        }
    if action_type == "region_focus":
        return {
            "type": "region_focus",
            "focus_mode": str(payload.get("focus_mode") or "at_hotspot"),
            "center": payload.get("center") or payload.get("hotspot"),
            "suggested_offset_blocks": payload.get("suggested_offset_blocks"),
            "message": str(rec.get("message") or "")[:300],
            "source_rule": rec.get("id"),
        }
    return {"type": "noop"}


def run_situation_rules(
    snap: dict[str, Any] | None = None,
    *,
    auto_apply: bool | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """評估規則、記錄日誌；可選自動套用安全 log-only 動作。"""
    if not rules_enabled():
        return {"ok": False, "error": "rules_disabled", "recommendations": []}

    eval_result = evaluate_situation_rules(snap)
    recs = eval_result.get("recommendations") or []

    should_apply = auto_apply if auto_apply is not None else rules_auto_apply_enabled()
    apply_results: list[dict[str, Any]] = []
    applied_actions: list[dict[str, Any]] = []

    if should_apply and not dry_run:
        from backend.linkin.minecraft_ai_gm import apply_gm_actions

        for rec in recs:
            if not rec.get("auto_apply_safe"):
                continue
            action = recommendation_to_action(rec)
            if str(action.get("type")) not in _LOG_ONLY_ACTIONS:
                continue
            applied_actions.append(action)
        if applied_actions:
            apply_results = apply_gm_actions(
                applied_actions,
                dry_run=False,
                auto_apply=True,
            )

    run_id = f"rule-{uuid.uuid4().hex[:10]}"
    record = {
        "id": run_id,
        "ts": time.time(),
        "recommendation_count": len(recs),
        "recommendations": recs,
        "auto_applied": bool(applied_actions),
        "apply_results": apply_results,
        "dry_run": dry_run,
    }
    _append_rule_run(record)

    return {
        "ok": True,
        "run_id": run_id,
        "recommendations": recs,
        "auto_applied": bool(applied_actions),
        "apply_results": apply_results,
        "region_focus": eval_result.get("region_focus"),
    }


def enrich_situation_snapshot(snap: dict[str, Any]) -> dict[str, Any]:
    """在情境快照上附加規則建議與精簡提示。"""
    if not rules_enabled():
        return snap

    eval_result = evaluate_situation_rules(snap)
    recs = eval_result.get("recommendations") or []
    rule_hints = [str(r.get("message") or "") for r in recs[:4] if r.get("message")]

    hints = list(snap.get("hints") or [])
    for hint in rule_hints:
        if hint and hint not in hints:
            hints.append(hint)
    hints = hints[:8]

    return {
        **snap,
        "hints": hints,
        "rule_recommendations": recs,
        "region_focus": eval_result.get("region_focus") or {},
    }


__all__ = [
    "enrich_situation_snapshot",
    "evaluate_situation_rules",
    "get_region_focus",
    "list_rule_runs",
    "recommendation_to_action",
    "reset_rules_state",
    "rules_auto_apply_enabled",
    "rules_enabled",
    "run_situation_rules",
    "set_region_focus",
]
