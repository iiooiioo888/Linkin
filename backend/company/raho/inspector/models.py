"""審查官資料模型（自 backend.company.raho.inspector 抽出）。

ReworkRequired／EscalateRequired 例外與 InspectorGrill／InspectorVerdict dataclass。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import ESCALATE_MARK, GRILL_MARK, GrillIssue

from .constants import (
    GRILL_TARGET_L2,
    INSPECTOR_ID,
    TEST_EDGE,
    TEST_FACTUAL,
    TEST_SCHEMA,
    TEST_SEMANTIC,
    VERDICT_APPROVED,
    VERDICT_REWORK,
)


class ReworkRequired(Exception):
    """L1 要求 L2 重做。"""

    def __init__(self, verdict: InspectorVerdict):
        super().__init__(verdict.details or "L1 退回重做")
        self.verdict = verdict


class EscalateRequired(Exception):
    """L1 向上呈報 L3／L4／L5。"""

    def __init__(self, verdict: InspectorVerdict):
        super().__init__(verdict.details or "L1 向上呈報")
        self.verdict = verdict


@dataclass
class InspectorGrill:
    """L1 雙向質詢：L2 重做 或 L3 改指令。"""

    type: str = "GRILL"
    target: str = GRILL_TARGET_L2
    failed_test: str = TEST_SCHEMA
    details: str = ""
    required_fix: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "target": self.target,
            "failed_test": self.failed_test,
            "details": self.details,
        }
        if self.target == GRILL_TARGET_L2:
            payload["required_fix"] = self.required_fix or self.suggested_fix
        else:
            payload["suggested_fix"] = self.suggested_fix or self.required_fix
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_issue(self) -> GrillIssue:
        kind = {
            TEST_SCHEMA: "spec",
            TEST_SEMANTIC: "spec",
            TEST_FACTUAL: "contradiction",
            TEST_EDGE: "constraint",
        }.get(self.failed_test, "spec")
        field = {
            TEST_SCHEMA: "output_schema",
            TEST_SEMANTIC: "task_description",
            TEST_FACTUAL: "input_ref",
            TEST_EDGE: "edge_case",
        }.get(self.failed_test, "")
        blocker = {
            TEST_SCHEMA: "標準模糊" if "模糊" in self.details else "容量矛盾",
            TEST_SEMANTIC: "標準模糊",
            TEST_FACTUAL: "資料缺失",
            TEST_EDGE: "約束衝突",
        }.get(self.failed_test, "")
        return GrillIssue(
            message=self.details or self.failed_test,
            kind=kind,
            field=field,
            blocker_type=blocker,
            suggested_fix=self.suggested_fix or self.required_fix,
            target=self.target,
        )

    def render(self) -> str:
        mark = ESCALATE_MARK if self.type == "ESCALATE" else GRILL_MARK
        return f"{mark}\n{self.to_json()}"


@dataclass
class InspectorVerdict:
    verdict: str = VERDICT_REWORK
    inspector_id: str = INSPECTOR_ID
    test_results: dict[str, str] = field(default_factory=dict)
    final_approved_data: str = ""
    quality_score: float = 0.0
    details: str = ""
    grill: InspectorGrill | None = None
    signature: str = ""
    node_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "verdict": self.verdict,
            "inspector_id": self.inspector_id,
            "test_results": dict(self.test_results),
            "final_approved_data": self.final_approved_data,
            "quality_score": self.quality_score,
        }
        if self.details:
            payload["details"] = self.details
        if self.signature:
            payload["signature"] = self.signature
        if self.node_id:
            payload["node_id"] = self.node_id
        if self.grill is not None:
            payload["grill"] = self.grill.to_dict()
        return payload

    def approved(self) -> bool:
        return self.verdict == VERDICT_APPROVED
