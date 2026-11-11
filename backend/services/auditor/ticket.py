"""Requirement Auditor 的門票組裝與鎖定簡報（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.company.raho.store import UserGrillSession

from .constants import _FALLBACK, _RISK, DIM_KEYS
from .scoring import (
    _has_review_gate,
    _is_fan_scenario,
    _joined,
    _user_answers,
    all_dims_locked,
    score_dimensions,
)


def _audit_trail(sess: UserGrillSession) -> list[str]:
    trail: list[str] = []
    last_q = ""
    for turn in sess.turns:
        if turn.get("role") == "assistant":
            last_q = str(turn.get("content") or "")
        elif turn.get("role") == "user" and last_q:
            trail.append(f"Q: {last_q} A: {turn.get('content', '')}")
            last_q = ""
    return trail[:16]


def _extract_field(pattern: str, text: str, default: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return default
    if match.lastindex:
        return match.group(1).strip()[:180]
    return match.group(0).strip()[:180]


def build_ticket(sess: UserGrillSession) -> dict[str, Any]:
    """組裝進入 Planner 的戰術指令 JSON。"""
    text = _joined(sess.query, _user_answers(sess))
    scores = sess.scores or score_dimensions(sess.query, _user_answers(sess))
    confidence = round(min(float(scores[k]) for k in DIM_KEYS), 1)
    hours = re.search(
        r"(?:目前|現需|现需)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(小時|小时|分鐘|分钟).{0,40}?"
        r"(?:目標|目标|壓縮|压缩)[^\d]{0,8}(\d+(?:\.\d+)?)\s*(小時|小时|分鐘|分钟)",
        text,
    )
    acc = re.search(r"(準確率|准确率|誤報率|误报率)[^\d]{0,6}(\d+(?:\.\d+)?)\s*%", text)
    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    unit_cost = re.search(r"(\d+(?:\.\d+)?)\s*(元|塊|块)", text)
    if hours:
        quantified = (
            f"目前每日人工 {hours.group(1)}{hours.group(2)}，"
            f"目標壓縮至 {hours.group(3)}{hours.group(4)}"
        )
        if acc:
            quantified += f"，{acc.group(1)} {acc.group(2)}%"
    elif _is_fan_scenario(sess.query) and len(rates) >= 2:
        quantified = f"目前復購率 {rates[0]}%，目標提升至 {rates[-1]}%"
        if unit_cost:
            quantified += f"，單粉行銷成本 {unit_cost.group(1)} 元"
        if _has_review_gate(text):
            quantified += "，關鍵推播需經人工審核"
    else:
        quantified = _extract_field(
            r"(.{0,40}\d+(?:\.\d+)?\s*(?:小時|小时|%|％).{0,40})",
            text,
            "需以對話中的量化指標作為驗收標準",
        )
    budget = _extract_field(
        r"((?:預算|预算)[^。\n]{0,40}\d+[^。\n]{0,20})",
        text,
        "未明示預算區間",
    )
    if budget == "未明示預算區間" and unit_cost:
        budget = f"單粉行銷成本 {unit_cost.group(1)} 元"
    deadline = _extract_field(r"(\d{4}-\d{2}-\d{2})", text, "未明示截止日期")
    exclusions = [m.group(0) for m in re.finditer(r"(不(?:做|使用|開發|开发|包含)[^，。,\n]{2,30})", text)]
    if _is_fan_scenario(sess.query) and _has_review_gate(text):
        gate = "不自動推播（關鍵內容需人工審核）"
        if gate not in exclusions:
            exclusions.append(gate)
    techs = []
    for name in ("Python", "PostgreSQL", "Line Notify", "Excel", "API"):
        if re.search(name, text, re.IGNORECASE):
            techs.append(name)
    risks = []
    if _is_fan_scenario(sess.query) and _has_review_gate(text):
        risks.append("老粉退粉（備案：關鍵推播改為人工審核）")
    if _RISK.search(text) or _FALLBACK.search(text):
        risks.append(_extract_field(r"(.{0,20}(?:備案|备案|人工確認|人工确认|CSV|人工審核|人工审核)[^。\n]{0,40})", text, "已標示備案"))
    if not risks:
        risks.append("用戶已承認主要失敗模式並提供備案")
    priority = "Cost > Time > Quality (在預算內，稍微延後可接受)"
    if re.search(r"(延後|延后).{0,8}(可接受|其次)", text):
        priority = "Cost > Time > Quality (在預算內，稍微延後可接受)"
    elif re.search(r"(時程|时程|上線|上线).{0,12}(不可|不能|優先|优先)", text):
        priority = "Time > Cost > Quality"
    ticket = {
        "status": "APPROVED_FOR_PLANNING",
        "confidence_score": confidence,
        "clarified_goal": {
            "target_audience": _extract_field(
                r"((?:用戶|用户|客群|賣家|卖家|粉絲|粉丝|終端|终端)[^。\n]{0,40})",
                text,
                "內容創作者的粉絲（終端用戶）" if _is_fan_scenario(sess.query) else sess.query[:80],
            ),
            "core_action": _extract_field(
                r"((?:自動|自动|生成|預警|预警|調價|调价|壓縮|压缩)[^。\n]{0,50})",
                text,
                "以人工審核把關的自動粉絲經營與復購提升"
                if _is_fan_scenario(sess.query)
                else sess.query[:120],
            ),
            "quantified_success": quantified,
        },
        "hard_constraints": {
            "deadline": deadline,
            "budget_range": budget,
            "must_use_tech": techs or ["依現有技術棧"],
            "absolute_exclusions": exclusions[:6],
        },
        "risk_register": {
            "identified_risks": risks[:6],
            "user_priority": priority,
        },
        "audit_trail": _audit_trail(sess),
        "dimension_scores": dict(scores),
    }
    return ticket


def format_locked_brief(sess: UserGrillSession, ticket: dict[str, Any]) -> str:
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    risks = ticket.get("risk_register") or {}
    parts = [
        "【需求審計官戰術指令｜APPROVED_FOR_PLANNING】",
        f"目標受眾：{goal.get('target_audience', '')}",
        f"核心行動：{goal.get('core_action', '')}",
        f"量化成功：{goal.get('quantified_success', '')}",
        f"截止：{constraints.get('deadline', '')}",
        f"預算：{constraints.get('budget_range', '')}",
        f"必須使用：{', '.join(constraints.get('must_use_tech') or [])}",
        f"絕對不做：{', '.join(constraints.get('absolute_exclusions') or [])}",
        f"風險備案：{'; '.join(risks.get('identified_risks') or [])}",
        f"取捨順序：{risks.get('user_priority', '')}",
        f"置信度：{ticket.get('confidence_score')}",
        "【原始需求】" + sess.query,
        "```json\n" + json.dumps(ticket, ensure_ascii=False, indent=2) + "\n```",
    ]
    return "\n".join(parts)


def _phase_gate(phase: int, scores: dict[str, float]) -> bool:
    if phase <= 1:
        return float(scores.get("specificity", 0)) >= 70
    if phase == 2:
        return float(scores.get("constraints", 0)) >= 70 and float(scores.get("success", 0)) >= 70
    if phase == 3:
        return float(scores.get("risk", 0)) >= 70 and float(scores.get("boundary", 0)) >= 60
    return all_dims_locked(scores)


def _infer_phase(scores: dict[str, float]) -> int:
    if float(scores.get("specificity", 0)) < 70:
        return 1
    if float(scores.get("constraints", 0)) < 70 or float(scores.get("success", 0)) < 70:
        return 2
    if float(scores.get("risk", 0)) < 70 or float(scores.get("boundary", 0)) < 60:
        return 3
    return 4
