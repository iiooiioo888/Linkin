"""強制質詢協議（Mandatory Grill Protocol）。

L2 執行前／執行產出中以 [GRILL] 標記向上質詢。
未標記的產出視為隱式 [CLEAR]，以相容既有協調器測試。
"""

from __future__ import annotations

import re
from typing import Any

from backend.company.raho.protocol import (
    CHOICE_MARK,
    CLEAR_MARK,
    ESCALATE_MARK,
    GRILL_MARK,
    EscalationChoice,
    GrillIssue,
    MGP_EXECUTOR_PREAMBLE,
    MGP_SUPERIOR_PREAMBLE,
    mgp_enabled,
)

_GRILL_LINE = re.compile(
    rf"(?:{re.escape(GRILL_MARK)}|{re.escape(ESCALATE_MARK)}|{re.escape(CHOICE_MARK)})\s*[:：]?\s*(.+)",
)
_CHOICE_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?([A-Ca-c])[:：.、)\]]\s*(.+)$",
    re.MULTILINE,
)


def apply_mgp_system(system_prompt: str, *, superior: bool = False) -> str:
    """將 MGP 硬編碼到 System Prompt 最前方。

    L2 若已由 AtomicExecutorFactory 鎖定憲法層，不再疊加短前言，避免雙重協議。
    """
    if not mgp_enabled():
        return system_prompt
    body = (system_prompt or "").strip()
    if not superior:
        from backend.company.raho.atomic_executor import has_constitution
        from backend.company.raho.inspector import has_inspector_constitution

        if has_constitution(body) or has_inspector_constitution(body):
            layer = 1 if has_inspector_constitution(body) else 2
            try:
                from backend.company.raho.l0 import inject_l0

                return inject_l0(body, layer, "")
            except Exception:  # noqa: BLE001
                return body
    preamble = MGP_SUPERIOR_PREAMBLE if superior else MGP_EXECUTOR_PREAMBLE
    if preamble in body:
        assembled = body
    else:
        assembled = f"{preamble}\n\n{body}".strip()
    if superior:
        try:
            from backend.company.raho.l0 import inject_l0

            assembled = inject_l0(assembled, 3, "")
        except Exception:  # noqa: BLE001
            pass
    return assembled


def parse_grill_output(text: str) -> tuple[str, list[GrillIssue]]:
    """解析執行產出。回傳 (kind, issues)。

    kind: clear | grill | escalate
    優先解析結構化 JSON；無標記 → clear（向後相容）。
    """
    raw = text or ""
    stripped = raw.lstrip()
    from backend.company.raho.atomic_executor import parse_structured_protocol
    from backend.company.raho.inspector import parse_inspector_grill

    inspector = parse_inspector_grill(raw)
    if inspector is not None:
        kind = "escalate" if inspector.type == "ESCALATE" else "grill"
        return kind, [inspector.to_issue()]

    structured = parse_structured_protocol(raw)
    if structured is not None:
        kind = "escalate" if structured.type == "ESCALATE" else "grill"
        return kind, [structured.to_issue()]

    issues: list[GrillIssue] = []
    if (
        stripped.startswith(ESCALATE_MARK)
        or stripped.startswith(CHOICE_MARK)
        or f"\n{ESCALATE_MARK}" in raw
        or f"\n{CHOICE_MARK}" in raw
    ):
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
    for mark in (CLEAR_MARK, GRILL_MARK, ESCALATE_MARK, CHOICE_MARK):
        cleaned = cleaned.replace(mark, "")
    return cleaned.strip()


def parse_choices(text: str) -> list[EscalationChoice]:
    """從上交正文抽出 A/B/C 方案。"""
    choices: list[EscalationChoice] = []
    seen: set[str] = set()
    for match in _CHOICE_LINE.finditer(text or ""):
        key = match.group(1).lower()
        label = match.group(2).strip()[:160]
        if key in seen or not label:
            continue
        seen.add(key)
        choices.append(EscalationChoice(key=key, label=label))
        if len(choices) >= 3:
            break
    return choices


def rule_inspect_instruction(
    title: str,
    description: str,
    tools_allowed: list[str] | None = None,
    requested_tools: list[str] | None = None,
    task_spec: dict[str, Any] | None = None,
) -> list[GrillIssue]:
    """執行前規則檢查（不呼叫 LLM）。空描述等硬缺陷才攔截。

    若提供 L3 任務層 `task_spec`，改走戰前檢查清單五問。
    """
    if task_spec:
        from backend.company.raho.atomic_executor import preflight_issues

        return preflight_issues(task_spec)

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
