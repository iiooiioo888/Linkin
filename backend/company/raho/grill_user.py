"""L5→L4 用戶 Grill-Me：語意鎖定（Semantic Locking）。

強制前置閘門已升級為 L4 需求審計官（`backend.services.auditor`）。
本模組保留既有函式名與 `/raho/grill/*` 介面，避免呼叫端分裂。
與 `backend.linkin.grill_me`（烤問使用者計畫）互補，不取代。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from backend.company.raho.protocol import (
    MAX_USER_GRILL_TURNS,
    lock_threshold,
    user_grill_enabled,
)

logger = logging.getLogger(__name__)


def _auditor():
    """延後匯入，避免 raho/__init__ → grill_user → auditor → raho 循環。"""
    from backend.services import auditor

    return auditor


def should_grill_user(query: str, execution_strategy: str = "auto") -> bool:
    return _auditor().should_grill_user(query, execution_strategy)

_QUANT = re.compile(
    r"(\d+(\.\d+)?\s*%|\d+|gmv|kpi|roi|轉化|复购|復購|淨利|净利|營收|营收|"
    r"deadline|驗收|验收|指標|指标|預算|预算|時程|时程)",
    re.IGNORECASE,
)
_VAGUE = re.compile(r"(提升|優化|优化|改善|做好|加強|加强|更好|完善)")
_CONSTRAINT = re.compile(r"(預算|预算|時程|时程|期限|優先|优先|犧牲|牺牲|品質|质量|範圍|范围)")
_SCOPE = re.compile(r"(現有|现有|拉新|復購|复购|對象|对象|客群|受眾|受众|不包含|不做)")


def score_requirement(query: str, answers: list[str] | None = None) -> tuple[float, list[str]]:
    """規則評分（向後相容）：回傳 (confidence, 仍缺的維度)。不呼叫 LLM。"""
    text = (query or "").strip()
    joined = text + "\n" + "\n".join(answers or [])
    gaps: list[str] = []
    score = 0.28

    if len(text) >= 200:
        score += 0.22
    elif len(text) >= 80:
        score += 0.14
    elif len(text) < 16:
        score = min(score, 0.38)

    if _QUANT.search(joined) and re.search(r"\d", joined):
        score += 0.18
    else:
        gaps.append("metric")
    if _CONSTRAINT.search(joined):
        score += 0.14
    else:
        gaps.append("tradeoff")
    if _SCOPE.search(joined):
        score += 0.12
    else:
        gaps.append("scope")
    if any(len(a.strip()) >= 20 for a in (answers or [])):
        score += 0.08 * min(3, sum(1 for a in answers or [] if len(a.strip()) >= 12))
    if _VAGUE.search(text) and not _QUANT.search(text) and not answers:
        score -= 0.12

    score = max(0.05, min(0.99, score))
    return score, gaps


def _llm_question(query: str, transcript: str, gaps: list[str], phase: int = 1):
    """測試可 monkeypatch 的 LLM 追問入口。"""
    return _auditor()._llm_question(query, transcript, gaps, phase)


def grill_user_start(query: str) -> dict[str, Any]:
    """開一場需求審計。第一次絕不放行。"""
    return _auditor().auditor_start(query)


def grill_user_turn(session_id: str, answer: str) -> dict[str, Any]:
    return _auditor().auditor_turn(session_id, answer)


def grill_user_lock(session_id: str, note: str = "") -> dict[str, Any]:
    """『直接執行』視同過度授權，不得繞過五維門檻。"""
    return _auditor().auditor_lock(session_id, note)


def grill_user_status() -> dict[str, Any]:
    status = _auditor().auditor_status()
    status.setdefault("lock_threshold", lock_threshold())
    status.setdefault("enabled", user_grill_enabled())
    status.setdefault("max_turns", MAX_USER_GRILL_TURNS)
    return status


__all__ = [
    "grill_user_lock",
    "grill_user_start",
    "grill_user_status",
    "grill_user_turn",
    "score_requirement",
    "should_grill_user",
]
