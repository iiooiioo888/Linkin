"""長度護欄（自 backend.core.nodes 抽出）。

長度護欄：門檻解析、合規狀態、改寫預算與最終交付守門。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from backend.core.pipeline_trace import log_node
from backend.core.state import StateInput
from backend.prompts import templates

logger = logging.getLogger(__name__)


# 超長回答最多丢回反思閉環重寫的次數。執行時以 _max_length_rewrites() 為準。
MAX_LENGTH_REWRITES = int(os.getenv("EVOL_MAX_LENGTH_REWRITES", "2"))


def _env_bool(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "on"}


def _max_length_rewrites() -> int:
    raw = os.getenv("EVOL_MAX_LENGTH_REWRITES", str(MAX_LENGTH_REWRITES)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return MAX_LENGTH_REWRITES


def _min_length_accept_ratio() -> float:
    """EVOL_MIN_LENGTH_ACCEPT_RATIO 語義（寫死）。

    這是超限容忍倍數，不是過短門檻，也不是「實際長度 / 上限 >= ratio 才通過」。
    通過條件永遠是 len(answer) <= limit。
    ratio <= 0（預設 0）：不套用比例。預算用盡後仍可帶 length_warning 交付最短版。
    ratio > 0：僅當 len(best) <= limit * ratio 才允許帶警告交付。
    例：limit=1000、ratio=1.2 → 最短版 <= 1200 才可帶警告交付；更長則拒絕交付。
    """
    raw = os.getenv("EVOL_MIN_LENGTH_ACCEPT_RATIO", "0").strip()
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _fail_closed_on_length() -> bool:
    """EVOL_FAIL_CLOSED_ON_LENGTH 預設 false：標記失敗，仍交付最短版。"""
    return _env_bool("EVOL_FAIL_CLOSED_ON_LENGTH")


def _length_compliance(status: str, actual: int, limit: int, rewrites: int) -> dict:
    return {
        "status": status,
        "actual_chars": actual,
        "target_chars": limit,
        "rewrites": rewrites,
    }


def length_gate_event_fields(state: StateInput) -> dict[str, Any]:
    """從圖狀態擷取長度守門結果，供 Task API / SSE 事件附加（僅增欄位、不刪既有鍵）。"""
    out: dict[str, Any] = {}
    compliance = state.get("length_compliance")
    if isinstance(compliance, dict) and compliance:
        out["length_compliance"] = dict(compliance)
    if state.get("length_warning"):
        out["length_warning"] = True
    if state.get("length_refused"):
        out["length_refused"] = True
    return out


def _resolve_output_limit(state: StateInput) -> int:
    """解析本次任務的輸出長度上限（依複雜度動態，可由配置熱重載覆寫）。"""
    from backend.core.cost_speed_router import (
        classify_task_complexity,
        max_output_chars_for_complexity,
    )

    complexity = state.get("task_complexity") or classify_task_complexity(state.get("query", ""))
    return max_output_chars_for_complexity(complexity)  # type: ignore[arg-type]


def _enforce_output_length(state: StateInput, field: str) -> dict:
    answer = str(state.get(field) or "")
    limit = _resolve_output_limit(state)
    used = int(state.get("length_rewrites") or 0)
    if state.get("length_refused"):
        return {
            "length_directive": "",
            "length_refused": True,
            "length_warning": False,
            "max_output_chars": limit,
            "length_compliance": state.get("length_compliance") or _length_compliance(
                "failed", len(answer), limit, used,
            ),
        }
    if len(answer) <= limit:
        cleared = {
            "max_output_chars": limit,
            "length_compliance": _length_compliance("ok", len(answer), limit, used),
            "length_warning": False,
        }
        if not state.get("length_directive"):
            return cleared
        return {**cleared, "length_directive": ""}

    best = str(state.get("length_best_answer") or "")
    if not best or len(answer) < len(best):
        best = answer

    if used >= _max_length_rewrites():
        ratio = _min_length_accept_ratio()
        # ratio <= 0 表示不套用「len(best) <= limit * ratio」這條容忍帶。
        within_ratio = ratio <= 0 or len(best) <= limit * ratio
        refuse = _fail_closed_on_length() or not within_ratio
        warnings = list(state.get("length_warnings", []))
        if refuse:
            warnings.append(
                f"已重寫 {used} 次仍有 {len(answer)} 字，超過 {limit} 字上限，拒絕交付。"
            )
        else:
            warnings.append(
                f"已重寫 {used} 次仍有 {len(answer)} 字，超過 {limit} 字上限，"
                f"改交付最短版本（{len(best)} 字）。"
            )
        log_node(
            state, "enforce_output_length",
            gate=field, length=len(answer), limit=limit, exhausted=True, refused=refuse,
        )
        exhausted: dict = {
            "length_directive": "",
            "length_warnings": warnings,
            "length_best_answer": best,
            "max_output_chars": limit,
            "length_compliance": _length_compliance("failed", len(answer), limit, used),
            "length_warning": not refuse,
            "length_refused": refuse,
            field: "" if refuse else best,
        }
        if field == "final_answer":
            exhausted["current_answer"] = "" if refuse else best
        return exhausted

    directive = templates.LENGTH_DIRECTIVE.format(
        max_chars=limit,
        actual_chars=len(answer),
        excess_chars=len(answer) - limit,
    )
    log_node(
        state,
        "enforce_output_length",
        gate=field,
        length=len(answer),
        limit=limit,
        length_rewrites=used + 1,
    )
    rewrite: dict = {
        "length_directive": directive,
        "length_rewrites": used + 1,
        "length_best_answer": best,
        "max_output_chars": limit,
    }
    if field == "final_answer":
        # 閉環要壓縮的是真正會交付的那份（可能是降級而來的 initial_answer）
        rewrite["current_answer"] = answer
    return rewrite


def enforce_output_length(state: StateInput) -> dict:
    """節點 4.5：評估前的長度守門（看 current_answer）。

    未超限 → 放行且不消耗 LLM 呼叫（並清掉已消化的長度指令）；
    超限 → 寫入長度硬性要求與重寫計數，由圖路由丢回 reflect 重寫；
    重寫預算用盡仍超限 → 改交付歷次最短的一版並記警告，不再回環。
    """
    return _enforce_output_length(state, "current_answer")


def enforce_final_length(state: StateInput) -> dict:
    """節點 5.5：交付端的長度守門（看 final_answer）。

    攔下 decide_final_answer 因空回答降級使用 initial_answer 造成的超長交付。
    """
    return _enforce_output_length(state, "final_answer")
