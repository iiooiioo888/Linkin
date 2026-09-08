"""L5→L4 用戶 Grill-Me：語意鎖定（Semantic Locking）。

強制前置閘門已升級為 L4 需求審計官（`backend.services.auditor`）。
本模組保留既有函式名與 `/raho/grill/*` 介面，避免呼叫端分裂。
與 `backend.linkin.grill_me`（烤問使用者計畫）互補，不取代。
"""

from __future__ import annotations

import logging
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

def score_requirement(query: str, answers: list[str] | None = None) -> tuple[float, list[str]]:
    """五維評分（單一來源：`backend.services.auditor`）。不呼叫 LLM。"""
    return _auditor().score_requirement(query, answers)


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
    status["lock_threshold"] = lock_threshold()
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
