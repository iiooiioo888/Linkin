"""Requirement Auditor 的問題產生與 LLM 追問（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.company.raho.protocol import GrillQuestion, RahoLayer
from backend.services.auditor_prompt import SYSTEM_PROMPT

from .bank import _CHOICES_BY_DIMENSION, _CHOICES_BY_QUESTION_ID
from .constants import _VAGUE_VERB_PRIORITY, PHASE_LABELS, logger


def _normalize_choices(
    raw: list[dict[str, str]] | None,
    dimension: str,
    question_id: int | None = None,
) -> list[dict[str, str]]:
    if raw:
        cleaned = [
            {"key": str(c.get("key") or f"opt{i}"), "label": str(c.get("label") or "").strip()}
            for i, c in enumerate(raw)
            if str(c.get("label") or "").strip()
        ]
        if cleaned:
            return cleaned[:4]
    if question_id is not None and question_id in _CHOICES_BY_QUESTION_ID:
        return list(_CHOICES_BY_QUESTION_ID[question_id])
    return list(_CHOICES_BY_DIMENSION.get(dimension, _CHOICES_BY_DIMENSION["specificity"]))


def _make_question(
    question: str,
    *,
    why: str = "",
    dimension: str = "specificity",
    choices: list[dict[str, str]] | None = None,
    question_id: int | None = None,
) -> GrillQuestion:
    return GrillQuestion(
        question=question,
        why=why,
        dimension=dimension,
        choices=_normalize_choices(choices, dimension, question_id),
    )


def _l0_knowledge_cite(query: str) -> str:
    """L4 開場引用知識庫定義，避免雙方對基礎名詞各說各話。"""
    try:
        from backend.company.raho.l0 import match_knowledge

        hits = match_knowledge(query)
    except Exception:
        return ""
    if not hits:
        return ""
    return f"知識庫已有定義：「{hits[0].content}」請用這個定義回答，不要各說各話。"


def _opening_hook(query: str) -> str:
    """第一問開場：拒絕模糊動詞，對齊規格中的「被烤」體驗。"""
    text = (query or "").strip()
    lead = "收到需求。"
    for verb in _VAGUE_VERB_PRIORITY:
        if verb in text:
            lead = f"收到需求。我不接受「{verb}」這個模糊動詞。"
            break
    cite = _l0_knowledge_cite(query)
    return f"{lead}{cite}" if cite else lead


def _contextual_first_question(query: str) -> GrillQuestion | None:
    """粉絲／管粉類模糊需求：第一問直接用規格範例話術，不先丟題庫 Q1。"""
    text = (query or "").strip()
    if any(verb in text for verb in ("管粉絲", "管粉丝", "管粉", "自動管", "自动管", "幫我管", "帮我管")):
        return _make_question(
            "收到需求。我不接受「管粉絲」這個模糊動詞。請用「最終用戶（粉絲）」的視角描述：在你介入前他們得不到什麼？在你介入後他們獲得了什麼具體好處？",
            why="沒有前後對照，目標只是口號。",
            dimension="specificity",
            question_id=1,
        )
    return None


def _vague_prefix(phase: int) -> str:
    if int(phase or 1) >= 2:
        return "量化失敗。請填入數字："
    return "量化失敗。我不接受『大概／盡量／好一點』。"


def _with_phase_tag(question: str, phase: int) -> str:
    tag = f"（Phase {int(phase or 1)}）"
    raw = (question or "").rstrip()
    if re.search(r"（Phase [1-4]）|\(Phase [1-4]\)", raw):
        return raw
    return f"{raw}{tag}"


def extract_json(text: str) -> dict[str, Any] | None:
    """從回應中擷取戰術指令 JSON。"""
    raw = text or ""
    if "APPROVED_FOR_PLANNING" not in raw and "```json" not in raw:
        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if not fence:
            return None
        raw = fence.group(1)
    try:
        from backend.core.llm import parse_json_response

        data = parse_json_response(raw)
    except Exception:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if data.get("status") != "APPROVED_FOR_PLANNING":
        return None
    return data


def _llm_question(query: str, transcript: str, gaps: list[str], phase: int) -> GrillQuestion | None:
    try:
        from backend.core.llm import call_llm, parse_json_response

        prompt = (
            f"目前階段：{PHASE_LABELS.get(phase, phase)}\n"
            f"【任務】{query}\n"
            f"【未達標維度】{', '.join(gaps) or '語意仍不夠鎖定'}\n"
            f"【對話】\n{transcript or '（尚無）'}\n\n"
            "一次只問一個具體、可證偽的問題。禁止說『明白了』。"
            "若用戶回答含『大概／盡量／好一點』，要求量化。"
            "只輸出 JSON：{\"question\":\"...\",\"why\":\"...\","
            "\"dimension\":\"specificity|boundary|constraints|risk|success\","
            "\"choices\":[{\"key\":\"a\",\"label\":\"...\"},{\"key\":\"b\",\"label\":\"...\"}]}"
            "（choices 2~4 項，含一項明確模糊選項供用戶自選，其餘為可驗收答案）"
        )
        from backend.company.raho.l0 import inject_l0

        raw = call_llm(prompt, system=inject_l0(SYSTEM_PROMPT, int(RahoLayer.L4_AUDITOR), query))
        parsed = extract_json(raw)
        if parsed:
            return None
        data = parse_json_response(raw) or {}
        question = str(data.get("question") or "").strip()
        if not question:
            return None
        raw_choices = data.get("choices")
        choices = raw_choices if isinstance(raw_choices, list) else None
        return _make_question(
            question,
            why=str(data.get("why") or ""),
            dimension=str(data.get("dimension") or "specificity"),
            choices=choices,
        )
    except Exception as exc:
        logger.debug("需求審計官 LLM 降級為題庫：%s", exc)
        return None
