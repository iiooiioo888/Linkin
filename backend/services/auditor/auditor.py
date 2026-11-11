"""RequirementAuditor 類（自 backend.services.auditor 抽出；會話流程在同套件 service.py）。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.store import STORE
from backend.services.auditor_prompt import SYSTEM_PROMPT

from .constants import CONFIDENCE_THRESHOLD, MAX_AUDITOR_ROUNDS
from .questions import extract_json
from .service import _terminate, auditor_start, auditor_turn, trigger_planner


class RequirementAuditor:
    """強制前置閘門。會話由 RAHO STORE 持有，供 HTTP／SSE／產生器多輪餵入。"""

    def __init__(self) -> None:
        self.system_prompt = SYSTEM_PROMPT
        self.max_rounds = MAX_AUDITOR_ROUNDS
        self.confidence_threshold = CONFIDENCE_THRESHOLD

    def start(self, initial_input: str) -> dict[str, Any]:
        return auditor_start(initial_input)

    def turn(self, session_id: str, user_reply: str) -> dict[str, Any]:
        return auditor_turn(session_id, user_reply)

    def extract_json(self, response: str) -> dict[str, Any] | None:
        return extract_json(response)

    def trigger_planner(self, final_plan: dict[str, Any]) -> dict[str, Any]:
        return trigger_planner(final_plan)

    def force_termination(self, session_id: str, reason: str = "") -> dict[str, Any]:
        sess = STORE.get_user_session(session_id)
        if sess is None:
            raise KeyError(f"審計會話不存在或已過期：{session_id}")
        return _terminate(sess, reason or f"超過 {self.max_rounds} 輪仍未達標")

    def process_user_request(self, initial_input: str):
        """強制前置閘門產生器（規格第 5 節）。

        用法::
            gen = auditor.process_user_request(query)
            payload = next(gen)          # 第一問
            payload = gen.send(reply)    # 後續輪
            # 終態以 return 結束：APPROVED_FOR_PLANNING 或 FAILED
        """
        result = auditor_start(initial_input)
        if result.get("status") in {"APPROVED_FOR_PLANNING", "FAILED"}:
            return result
        user_reply = yield result
        session_id = str(result.get("session_id") or "")
        rounds = 0
        while rounds < self.max_rounds:
            if user_reply is None:
                user_reply = yield result
                continue
            result = auditor_turn(session_id, str(user_reply))
            session_id = str(result.get("session_id") or session_id)
            if result.get("status") in {"APPROVED_FOR_PLANNING", "FAILED"}:
                return result
            user_reply = yield result
            rounds += 1
        if session_id:
            return self.force_termination(session_id)
        return result
