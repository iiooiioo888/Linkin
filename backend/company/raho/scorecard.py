"""角色評分卡：被質詢率、決策清晰度。"""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_STATS: dict[str, dict[str, float]] = {}


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
    return {
        "grill_count": int(stats["grills"]),
        "grill_rate": round(grill_rate, 4),
        "decision_clarity": round(decision_clarity, 4),
        "escalations": int(stats["escalations"]),
        "user_escalations": int(stats["user_escalations"]),
        "executions": int(stats["executions"]),
    }


def all_metrics() -> dict[str, dict[str, Any]]:
    with _lock:
        keys = list(_STATS)
    return {k: metrics_for(k) for k in keys}


def reset_scorecard() -> None:
    with _lock:
        _STATS.clear()
