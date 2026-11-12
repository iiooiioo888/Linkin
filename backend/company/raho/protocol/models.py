"""RAHO 資料模型：質詢題目／問題、升級選項、語意鎖與 MGP 前置提示詞。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .layers import CHOICE_MARK, CLEAR_MARK, ESCALATE_MARK, GRILL_MARK, MAX_SUPERIOR_ROUNDS

MGP_EXECUTOR_PREAMBLE = (
    "【強制質詢協議 MGP】"
    "在執行任何操作前，你必須先對上級指令進行完整性與邏輯性審查。"
    "若發現缺失、矛盾、工具權限不符或輸出規格不足以決策，"
    f"必須先以 {GRILL_MARK} 提出質疑（每條一行），待上級回覆確認後方可執行。"
    "禁止盲目執行。若指令完整可執行，直接產出交付物"
    f"（可選於首行標 {CLEAR_MARK}）。"
    "執行中若遇非預期分支，暫停並以 "
    f"{ESCALATE_MARK} 或 {CHOICE_MARK} 上交 2~3 個方案（A/B/C），禁止自行亂選。"
)

MGP_SUPERIOR_PREAMBLE = (
    "【強制質詢協議 MGP｜上級】"
    f"當收到下層 {GRILL_MARK} 質詢時，你必須在 {MAX_SUPERIOR_ROUNDS} 輪內給出明確答覆。"
    f"若無法答覆，必須輸出 {ESCALATE_MARK} 並附上無法決策的原因與 2~3 個建議方案。"
)


@dataclass
class GrillQuestion:
    question: str
    why: str = ""
    dimension: str = ""
    choices: list[dict[str, str]] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": self.question,
            "why": self.why,
            "dimension": self.dimension,
        }
        if self.choices:
            payload["choices"] = self.choices
        return payload


@dataclass
class GrillIssue:
    """L2 對 L3 指令的一條質詢。"""

    message: str
    kind: str = "gap"  # gap | contradiction | tool | spec | constraint
    field: str = ""
    blocker_type: str = ""
    suggested_fix: str = ""
    target: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {"message": self.message, "kind": self.kind, "field": self.field}
        if self.blocker_type:
            payload["blocker_type"] = self.blocker_type
        if self.suggested_fix:
            payload["suggested_fix"] = self.suggested_fix
        if self.target:
            payload["target"] = self.target
        return payload


@dataclass
class EscalationChoice:
    key: str
    label: str
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "label": self.label, "rationale": self.rationale}


@dataclass
class SemanticLock:
    locked: bool
    confidence: float
    brief: str
    session_id: str = ""
    turns: int = 0
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locked": self.locked,
            "confidence": round(self.confidence, 4),
            "locked_brief": self.brief,
            "session_id": self.session_id,
            "turns": self.turns,
            "gaps": self.gaps,
        }
