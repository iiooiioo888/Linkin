"""Requirement Auditor 的五維評分與追問判分 helper（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

import re

from backend.company.raho.store import UserGrillSession

from .constants import (
    _ACTION,
    _BEFORE_AFTER,
    _BOUNDARY,
    _BUDGET,
    _CONFIRM,
    _FALLBACK,
    _FAN_COST,
    _FAN_KEYS,
    _FAN_METRIC,
    _FREE_OSS,
    _METRIC_WORD,
    _MONEY,
    _OVER_AUTH_PHRASE,
    _QUALITY_BOUND,
    _QUANT,
    _RATE_PAIR,
    _RESOURCE,
    _REVIEW_GATE,
    _RISK,
    _SOFT_GOAL,
    _SUBJECT,
    _SUCCESS,
    _TIME,
    _TRADEOFF,
    _UNLIMITED_BUDGET,
    _VAGUE,
    AUDITOR_DIM_THRESHOLD,
    DIM_KEYS,
)


def _joined(query: str, answers: list[str] | None) -> str:
    return (query or "").strip() + "\n" + "\n".join(answers or [])


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, score))


def _has_rate_pair(text: str) -> bool:
    raw = text or ""
    if _RATE_PAIR.search(raw):
        return True
    return len(re.findall(r"\d+(?:\.\d+)?\s*%", raw)) >= 2


def _has_money(text: str) -> bool:
    return bool(_MONEY.search(text or "") or _BUDGET.search(text or ""))


def _has_review_gate(text: str) -> bool:
    return bool(_REVIEW_GATE.search(text or "") or _FALLBACK.search(text or ""))


def score_dimensions(query: str, answers: list[str] | None = None) -> dict[str, float]:
    """五維 0–100 評分（規則引擎，測試可重現、不呼叫 LLM）。"""
    text = _joined(query, answers)
    answers = answers or []
    last = answers[-1] if answers else ""
    fan = _is_fan_scenario(query)
    rate_pair = _has_rate_pair(text)
    money = _has_money(text)
    review_gate = _has_review_gate(text)
    metric = bool(_FAN_METRIC.search(text) or (fan and rate_pair))

    spec = 18.0
    if _SUBJECT.search(text):
        spec += 22.0
    if _ACTION.search(text):
        spec += 16.0
    if _QUANT.search(text):
        spec += 28.0
    elif _METRIC_WORD.search(text):
        spec += 8.0
    if _BEFORE_AFTER.search(text):
        spec += 18.0
    if metric and _QUANT.search(text):
        spec += 12.0
    if rate_pair:
        spec += 10.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        spec = min(spec, 38.0)
    if len(text) < 16:
        spec = min(spec, 32.0)

    boundary = 12.0
    if _BOUNDARY.search(text):
        boundary += 42.0
    if re.search(r"(80%|20%|犧牲|牺牲)", text):
        boundary += 24.0
    if review_gate or re.search(r"(絕對可控|绝对可控)", text):
        boundary += 40.0
    if _QUALITY_BOUND.search(text):
        boundary += 24.0
    if len(re.findall(r"(不做|不使用|不開發|不开发|絕對不|绝对不)", text)) >= 2:
        boundary += 18.0
    if _VAGUE.search(last) and not _BOUNDARY.search(last) and not review_gate:
        boundary = min(boundary, 40.0)

    constraints = 10.0
    if _BUDGET.search(text) or money:
        constraints += 28.0
    if _TIME.search(text):
        constraints += 26.0
    if _RESOURCE.search(text):
        constraints += 18.0
    if _TRADEOFF.search(text):
        constraints += 20.0
    if metric and (_FAN_COST.search(text) or money):
        constraints += 40.0
    if fan and rate_pair and money:
        constraints += 16.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        constraints = min(constraints, 35.0)

    risk = 10.0
    if _RISK.search(text):
        risk += 32.0
    if _FALLBACK.search(text) or review_gate:
        risk += 36.0
    if re.search(r"(聽誰|听谁|人工|停損|停损|衝突|冲突)", text):
        risk += 16.0
    if review_gate:
        risk += 28.0
    if _VAGUE.search(last) and not _RISK.search(last) and not review_gate:
        risk = min(risk, 36.0)

    success = 10.0
    if re.search(r"(目前.{0,20}\d+.{0,20}(目標|目标|壓縮|压缩).{0,20}\d+)", text):
        success += 32.0
    elif _BEFORE_AFTER.search(text) and _QUANT.search(text):
        success += 24.0
    if _SUCCESS.search(text) or rate_pair:
        success += 28.0
    if re.search(r"(Excel|Prototype|報表|报表|備忘錄|备忘录|JSON)", text, re.IGNORECASE):
        success += 18.0
    if any(_CONFIRM.search(a.strip()) for a in answers):
        success += 12.0
    if metric and _QUANT.search(text):
        success += 22.0
    if fan and rate_pair and review_gate:
        success += 16.0
    if _VAGUE.search(last) and not _QUANT.search(last):
        success = min(success, 36.0)

    return {
        "specificity": round(_clamp(spec), 1),
        "boundary": round(_clamp(boundary), 1),
        "constraints": round(_clamp(constraints), 1),
        "risk": round(_clamp(risk), 1),
        "success": round(_clamp(success), 1),
    }


def score_requirement(query: str, answers: list[str] | None = None) -> tuple[float, list[str]]:
    """向後相容：回傳 (0–1 綜合置信度, 缺口維度)。鎖定仍看五維皆 > 90。"""
    dims = score_dimensions(query, answers)
    if not dims:
        return 0.05, list(DIM_KEYS)
    overall = sum(float(v) for v in dims.values()) / (100.0 * len(dims))
    gaps = [key for key, val in dims.items() if val <= AUDITOR_DIM_THRESHOLD]
    legacy = []
    if "success" in gaps or "specificity" in gaps:
        legacy.append("metric")
    if "constraints" in gaps:
        legacy.append("tradeoff")
    if "boundary" in gaps:
        legacy.append("scope")
    return max(0.05, min(0.99, overall)), legacy or gaps


def all_dims_locked(scores: dict[str, float]) -> bool:
    return bool(scores) and all(float(scores.get(k, 0)) > AUDITOR_DIM_THRESHOLD for k in DIM_KEYS)


def _is_vague(text: str) -> bool:
    return bool(_VAGUE.search(text or "")) and not _QUANT.search(text or "")


def _is_fan_scenario(query: str) -> bool:
    return any(key in (query or "") for key in _FAN_KEYS)


def _fan_contract_ready(sess: UserGrillSession) -> bool:
    """規格第 6 節：復購率 + 單粉成本 + 人工審核備案齊了，才准進語義鎖定放行。"""
    if not _is_fan_scenario(sess.query):
        return False
    text = _joined(sess.query, _user_answers(sess))
    if not _has_rate_pair(text):
        return False
    if not _has_money(text):
        return False
    if not _has_review_gate(text):
        return False
    return not (int(sess.phase or 1) < 4 and 10 not in sess.asked_ids)


def _is_unquantified(text: str, phase: int = 1) -> bool:
    """無數字的軟目標／模糊詞視為無效；Phase 2 起更嚴格要求量化。"""
    raw = (text or "").strip()
    if not raw:
        return True
    if _QUANT.search(raw):
        return False
    if _CONFIRM.search(raw):
        return False
    if _is_vague(raw) or _SOFT_GOAL.search(raw):
        return True
    return bool(int(phase or 1) >= 2 and not (_TRADEOFF.search(raw) or _FALLBACK.search(raw) or _BOUNDARY.search(raw)))


def _synthesize_fan_lock(sess: UserGrillSession) -> str:
    text = _joined(sess.query, _user_answers(sess))
    rates = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    target = rates[-1] if rates else "目標值"
    cost = re.search(r"(\d+(?:\.\d+)?)\s*(元|塊|块)", text)
    cost_s = f"{cost.group(1)} 元" if cost else "已標示單粉成本"
    review = "且關鍵推播需經人工審核" if re.search(r"人工", text) else "且需有停損備案"
    return (
        f"語義鎖定：請用 50 字總結：「此專案是為提升復購率至 {target}%，"
        f"預算單粉 {cost_s}，{review}」。確認無誤我將產出作戰圖。"
    )


def _is_over_auth(text: str) -> bool:
    stripped = (text or "").strip()
    if stripped in {"直接執行", "直接执行", "結束", "结束", "夠了", "够了", "锁定", "鎖定"}:
        return True
    return bool(_OVER_AUTH_PHRASE.search(stripped))


def _is_contradiction(text: str) -> bool:
    return bool(_UNLIMITED_BUDGET.search(text) and _FREE_OSS.search(text))


def _user_answers(sess: UserGrillSession) -> list[str]:
    return [str(t.get("content") or "") for t in sess.turns if t.get("role") == "user"]
