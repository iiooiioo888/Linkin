"""強制質詢協議（Mandatory Grill Protocol）。

L2 執行前／執行產出中以 [GRILL] 標記向上質詢。
未標記的產出視為隱式 [CLEAR]，以相容既有協調器測試。
"""

from __future__ import annotations

import re
from typing import Any

from backend.company.raho.protocol import (
    CLEAR_MARK,
    ESCALATE_MARK,
    GRILL_MARK,
    GrillIssue,
    MGP_EXECUTOR_PREAMBLE,
    MGP_SUPERIOR_PREAMBLE,
    mgp_enabled,
)

_GRILL_LINE = re.compile(
    rf"(?:{re.escape(GRILL_MARK)}|{re.escape(ESCALATE_MARK)})\s*[:：]?\s*(.+)",
)


def apply_mgp_system(system_prompt: str, *, superior: bool = False) -> str:
    """將 MGP 硬編碼到 System Prompt 最前方。"""
    if not mgp_enabled():
        return system_prompt
    preamble = MGP_SUPERIOR_PREAMBLE if superior else MGP_EXECUTOR_PREAMBLE
    body = (system_prompt or "").strip()
    if preamble in body:
        return body
    return f"{preamble}\n\n{body}".strip()


def parse_grill_output(text: str) -> tuple[str, list[GrillIssue]]:
    """解析執行產出。回傳 (kind, issues)。

    kind: clear | grill | escalate
    無標記 → clear（向後相容）。
    """
    raw = text or ""
    stripped = raw.lstrip()
    issues: list[GrillIssue] = []
    if stripped.startswith(ESCALATE_MARK) or f"\n{ESCALATE_MARK}" in raw:
        kind = "escalate"
    elif stripped.startswith(GRILL_MARK) or f"\n{GRILL_MARK}" in raw:
        kind = "grill"
    else:
        return "clear", []

    for match in _GRILL_LINE.finditer(raw):
        message = match.group(1).strip()
        if message:
            issues.append(GrillIssue(message=message[:500]))
    if not issues:
        issues.append(GrillIssue(message=stripped[:500] or "指令不完整，請補充"))
    return kind, issues


def strip_protocol_marks(text: str) -> str:
    """移除協議標記，留下交付物本文。"""
    cleaned = text or ""
    for mark in (CLEAR_MARK, GRILL_MARK, ESCALATE_MARK):
        cleaned = cleaned.replace(mark, "")
    return cleaned.strip()


def rule_inspect_instruction(
    title: str,
    description: str,
    tools_allowed: list[str] | None = None,
    requested_tools: list[str] | None = None,
) -> list[GrillIssue]:
    """執行前規則檢查（不呼叫 LLM）。空描述等硬缺陷才攔截。"""
    issues: list[GrillIssue] = []
    desc = (description or "").strip()
    if not desc or len(desc) < 8:
        issues.append(
            GrillIssue(
                "工作項描述過短或缺失，無法確認交付物規格。",
                kind="spec",
                field="description",
            )
        )
    if not (title or "").strip():
        issues.append(GrillIssue("缺少任務標題。", kind="spec", field="title"))
    allowed = set(tools_allowed or [])
    for tool in requested_tools or []:
        if allowed and tool not in allowed:
            issues.append(
                GrillIssue(
                    f"指定工具「{tool}」不在權限白名單。",
                    kind="tool",
                    field="tools",
                )
            )
    return issues


def issues_to_prompt(issues: list[GrillIssue]) -> str:
    if not issues:
        return ""
    lines = [f"{GRILL_MARK} {issue.message}" for issue in issues]
    return "下層質詢：\n" + "\n".join(lines)


def parse_superior_reply(text: str) -> dict[str, Any]:
    """解析 L3/L4 對質詢的回覆。"""
    raw = (text or "").strip()
    if raw.startswith(ESCALATE_MARK) or ESCALATE_MARK in raw[:80]:
        return {"action": "escalate", "reply": strip_protocol_marks(raw)}
    return {"action": "resolve", "reply": strip_protocol_marks(raw) or raw}
