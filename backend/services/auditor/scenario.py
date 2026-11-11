"""Requirement Auditor 的下一題與 fan 場景推進（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

from backend.company.raho.protocol import GrillQuestion
from backend.company.raho.store import UserGrillSession

from .bank import _FAN_PHASE3_CHOICES, FAN_PHASE2_QUESTION, FAN_PHASE3_QUESTION, QUESTION_BANK
from .constants import _FALLBACK, _QUANT, _REVIEW_GATE, _RISK
from .questions import _make_question
from .scoring import _is_fan_scenario, _is_unquantified, _synthesize_fan_lock, _user_answers


def _scenario_next(sess: UserGrillSession) -> GrillQuestion | None:
    """規格第 6 節粉絲／管粉情境：走範例話術，不先丟通用題庫。"""
    if not _is_fan_scenario(sess.query):
        return None
    answers = _user_answers(sess)
    last = answers[-1] if answers else ""
    if sess.user_rounds >= 1 and 4 not in sess.asked_ids and _is_unquantified(last, 1):
        sess.phase = 2
        sess.phase_rounds = 0
        sess.asked_ids.append(4)
        return _make_question(
            FAN_PHASE2_QUESTION,
            why="效率必須是可驗收的三段數字。",
            dimension="success",
            question_id=4,
        )
    if 4 in sess.asked_ids and 7 not in sess.asked_ids and _QUANT.search(last):
        sess.phase = 3
        sess.phase_rounds = 0
        sess.asked_ids.append(7)
        return _make_question(
            FAN_PHASE3_QUESTION,
            why="沒有備案就等於把失敗外包給運氣。",
            dimension="risk",
            choices=_FAN_PHASE3_CHOICES,
        )
    if (
        7 in sess.asked_ids
        and 10 not in sess.asked_ids
        and answers
        and (_FALLBACK.search(last) or _RISK.search(last) or _REVIEW_GATE.search(last) or _QUANT.search(last))
    ):
        sess.phase = 4
        sess.phase_rounds = 0
        sess.asked_ids.append(10)
        return _make_question(
            _synthesize_fan_lock(sess),
            why="複誦才能暴露殘餘歧義。",
            dimension="success",
            question_id=10,
        )
    return None


def _next_question(sess: UserGrillSession) -> GrillQuestion:
    asked = set(sess.asked_ids)
    phase = int(sess.phase or 1)
    for item in QUESTION_BANK:
        if item["phase"] == phase and item["id"] not in asked:
            sess.asked_ids.append(item["id"])
            return _make_question(
                item["question"],
                why=item["why"],
                dimension=item["dimension"],
                choices=item.get("choices"),
                question_id=item["id"],
            )
    for item in QUESTION_BANK:
        if item["id"] not in asked:
            sess.phase = int(item["phase"])
            sess.phase_rounds = 0
            sess.asked_ids.append(item["id"])
            return _make_question(
                item["question"],
                why=item["why"],
                dimension=item["dimension"],
                choices=item.get("choices"),
                question_id=item["id"],
            )
    item = QUESTION_BANK[9]  # Phase 4 複誦
    return _make_question(
        item["question"],
        why=item["why"],
        dimension=item["dimension"],
        choices=item.get("choices"),
        question_id=item["id"],
    )
