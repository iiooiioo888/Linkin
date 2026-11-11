"""L3 戰術指揮官（自 backend.services.commander 抽出）。

TacticalCommander 類與系統提示套用。
"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import MGP_SUPERIOR_PREAMBLE, GrillIssue

from .grill import respond_to_grill
from .plan import build_escalation, plan_from_ticket
from .prompts import SYSTEM_PROMPT
from .rules import MAX_L2_PROMPT_TOKENS
from .ticket import estimate_tokens


class TacticalCommander:
    """L3 戰術指揮官。無狀態；會話資料由 RAHO STORE 持有。"""

    def __init__(self) -> None:
        self.system_prompt = SYSTEM_PROMPT
        self.max_l2_tokens = MAX_L2_PROMPT_TOKENS

    def plan(self, ticket: dict[str, Any] | str, *, use_llm: bool = True) -> dict[str, Any]:
        return plan_from_ticket(ticket, use_llm=use_llm)

    def grill(
        self,
        issues: list[GrillIssue] | list[str] | str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return respond_to_grill(issues, **kwargs)

    def escalate(self, reason: str, details: str, alternatives: list[str] | None = None) -> dict[str, Any]:
        return build_escalation(reason=reason, details=details, alternatives=alternatives)


def apply_commander_system(system_prompt: str) -> str:
    """把 L3 鐵律接到既有上級 System Prompt 前方。"""
    body = (system_prompt or "").strip()
    if "戰術指揮官" in body and "Atomic SRP" in body and "微雕與偏執" in body:
        return body
    return f"{MGP_SUPERIOR_PREAMBLE}\n\n{SYSTEM_PROMPT}\n\n{body}".strip()


def l2_brief_ok(prompt: str) -> bool:
    return estimate_tokens(prompt) <= MAX_L2_PROMPT_TOKENS
