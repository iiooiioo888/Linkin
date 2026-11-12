"""L3 任務層 spec 與 L2 → L3 結構化質詢模型。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.company.raho.protocol import ESCALATE_MARK, GRILL_MARK, GrillIssue

from .constants import (
    BLOCKER_CAPACITY,
    BLOCKER_CONSTRAINT,
    BLOCKER_CRITERIA,
    BLOCKER_INPUT,
    BLOCKER_TOOL,
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_TOKEN_BUDGET,
    GRILL_TARGET_L3,
)


@dataclass
class AtomicTaskSpec:
    """L3 注入的任務層欄位。憲法層不可由此覆寫。"""

    task_description: str = ""
    input_ref: Any = None
    allowed_tools: list[str] = field(default_factory=list)
    success_criteria: str = ""
    output_schema: str = ""
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    token_budget: int = DEFAULT_TOKEN_BUDGET
    instance_id: str = ""
    name: str = ""
    template_id: str = "generic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GrillMessage:
    """L2 → L3 結構化質詢（可程式處理，不必每次再叫 LLM）。"""

    type: str = "GRILL"
    target: str = GRILL_TARGET_L3
    blocker_type: str = BLOCKER_INPUT
    details: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "blocker_type": self.blocker_type,
            "details": self.details,
            "suggested_fix": self.suggested_fix,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_issue(self) -> GrillIssue:
        kind = {
            BLOCKER_INPUT: "gap",
            BLOCKER_TOOL: "tool",
            BLOCKER_CRITERIA: "spec",
            BLOCKER_CAPACITY: "contradiction",
            BLOCKER_CONSTRAINT: "constraint",
        }.get(self.blocker_type, "gap")
        field = {
            BLOCKER_INPUT: "input_ref",
            BLOCKER_TOOL: "allowed_tools",
            BLOCKER_CRITERIA: "success_criteria",
            BLOCKER_CAPACITY: "output_schema",
            BLOCKER_CONSTRAINT: "budget",
        }.get(self.blocker_type, "")
        return GrillIssue(
            message=self.details or self.blocker_type,
            kind=kind,
            field=field,
            blocker_type=self.blocker_type,
            suggested_fix=self.suggested_fix,
            target=self.target,
        )

    def render(self) -> str:
        mark = ESCALATE_MARK if self.type == "ESCALATE" else GRILL_MARK
        return f"{mark}\n{self.to_json()}"
