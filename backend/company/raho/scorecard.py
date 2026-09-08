"""角色評分卡：被質詢率、決策清晰度。"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_STATS: dict[str, dict[str, float]] = {}

DEMOTE_GRILL_RATE = 0.4
DEMOTE_MIN_EXECUTIONS = 3
WATCH_GRILL_RATE = 0.25


def _role(role_id: str) -> dict[str, float]:
    key = (role_id or "unknown").strip() or "unknown"
    if key not in _STATS:
        _STATS[key] = {
            "executions": 0.0,
            "grills": 0.0,
            "resolutions": 0.0,
            "clears": 0.0,
            "escalations": 0.0,
            "user_escalations": 0.0,
        }
    return _STATS[key]


def record_execution(role_id: str) -> None:
    with _lock:
        _role(role_id)["executions"] += 1


def record_grill(role_id: str) -> None:
    with _lock:
        stats = _role(role_id)
        stats["grills"] += 1
        if stats["executions"] < 1:
            stats["executions"] = 1


def record_resolution(role_id: str, *, clear: bool) -> None:
    with _lock:
        stats = _role(role_id)
        stats["resolutions"] += 1
        if clear:
            stats["clears"] += 1


def record_escalation(role_id: str, *, to_user: bool = False) -> None:
    with _lock:
        stats = _role(role_id)
        stats["escalations"] += 1
        if to_user:
            stats["user_escalations"] += 1


def metrics_for(role_id: str) -> dict[str, Any]:
    with _lock:
        stats = dict(_role(role_id))
    executions = max(stats["executions"], 1.0)
    grill_rate = stats["grills"] / executions
    # 被質詢率高 = 規劃／指令清晰度差
    decision_clarity = max(0.0, min(1.0, 1.0 - grill_rate * 0.85))
    if stats["resolutions"]:
        decision_clarity = (
            decision_clarity * 0.6 + (stats["clears"] / stats["resolutions"]) * 0.4
        )
    executions_n = int(stats["executions"])
    demoted = grill_rate >= DEMOTE_GRILL_RATE and executions_n >= DEMOTE_MIN_EXECUTIONS
    if demoted:
        rank = "demoted"
    elif grill_rate >= WATCH_GRILL_RATE and executions_n >= 2:
        rank = "watch"
    else:
        rank = "ok"
    return {
        "grill_count": int(stats["grills"]),
        "grill_rate": round(grill_rate, 4),
        "decision_clarity": round(decision_clarity, 4),
        "escalations": int(stats["escalations"]),
        "user_escalations": int(stats["user_escalations"]),
        "executions": executions_n,
        "demoted": demoted,
        "rank": rank,
    }


def should_demote(role_id: str) -> bool:
    """上層常被 Grill → 規劃能力差，系統降級（改走規則骨架、禁止口號式拆解）。"""
    return bool(metrics_for(role_id).get("demoted"))


def all_metrics() -> dict[str, dict[str, Any]]:
    with _lock:
        keys = list(_STATS)
    return {k: metrics_for(k) for k in keys}


def planning_paradigm_hint(role_id: str = "manager") -> str:
    """L3 常被 Grill 時，要求下一輪規劃寫清規格；過高則宣告降級。"""
    card = metrics_for(role_id)
    if card.get("demoted"):
        return (
            "【規劃官已降級】被質詢率過高"
            f"（{card['grill_rate']:.0%}，清晰度 {card['decision_clarity']:.2f}）。"
            "本輪強制使用規則骨架：每個原子任務必須寫明輸入欄位、輸出規格、"
            "工具白名單、可驗證成敗數字。禁止口號式描述，禁止自行擴寫範圍。"
        )
    if card["grill_rate"] < 0.35 or card["executions"] < 2:
        return ""
    return (
        "【規劃範式重構】近期戰術指令被質詢率偏高"
        f"（{card['grill_rate']:.0%}，清晰度 {card['decision_clarity']:.2f}）。"
        "每個原子任務必須寫明：輸入欄位、輸出規格、工具白名單、成敗數字。"
        "禁止口號式描述。"
    )


def reflection_notes(company_result: dict[str, Any] | None) -> str:
    """把質詢交鋒摘要交給 EvoLoop 反思，而不只評最終產出。"""
    if not company_result:
        return ""
    raho = company_result.get("raho") or {}
    tree = raho.get("tree") or {}
    nodes = tree.get("nodes") or []
    if not nodes:
        return ""
    grills = [n for n in nodes if n.get("kind") in {"mgp", "escalate", "user_grill"}]
    blocked = [n for n in nodes if n.get("status") in {"open", "blocked"}]
    timeouts = [n for n in nodes if n.get("status") == "timeout" or n.get("kind") == "timeout"]
    if not grills and not blocked:
        return ""
    lines = [
        "【RAHO 質詢交鋒】請針對每一次質詢與決策的缺口反思，不要只評最終產出。",
        f"- 質詢／上交節點 {len(grills)} 個，未解阻塞 {len(blocked)}，逾時 {len(timeouts)}。",
    ]
    for node in grills[:4]:
        lines.append(f"- L{node.get('from_layer')}→L{node.get('to_layer')} {node.get('summary', '')[:120]}")
    campaign = tree.get("campaign") or company_result.get("campaign") or {}
    if campaign.get("nodes"):
        lines.append(f"- 戰役節點 {len(campaign['nodes'])} 個（來源 {campaign.get('source', 'rule')}）")
    return "\n".join(lines)


def reset_scorecard() -> None:
    with _lock:
        _STATS.clear()
