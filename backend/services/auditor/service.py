"""Requirement Auditor 的會話流程：提問、審計、終止、核准與狀態（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import (
    LAYER_LABELS,
    GrillQuestion,
    RahoLayer,
    SemanticLock,
    user_grill_enabled,
)
from backend.company.raho.store import STORE, UserGrillSession

from .bank import OVER_AUTH_REPLY
from .constants import (
    _CONFIRM,
    AUDITOR_DIM_THRESHOLD,
    CONFIDENCE_THRESHOLD,
    DIM_KEYS,
    DIM_LABELS,
    MAX_AUDITOR_ROUNDS,
    MAX_PHASE_ROUNDS,
    PHASE_LABELS,
    logger,
)
from .questions import (
    _contextual_first_question,
    _llm_question,
    _make_question,
    _opening_hook,
    _vague_prefix,
    _with_phase_tag,
)
from .scenario import _next_question, _scenario_next
from .scoring import (
    _fan_contract_ready,
    _is_contradiction,
    _is_over_auth,
    _is_unquantified,
    _joined,
    _user_answers,
    all_dims_locked,
    score_dimensions,
)
from .ticket import _infer_phase, _phase_gate, build_ticket, format_locked_brief


def should_grill_user(query: str, execution_strategy: str = "auto") -> bool:
    """對話不再先走指揮鏈審計。任務由任務經理在公司運行時裡分析。"""
    del query, execution_strategy
    return False


def _transcript(sess: UserGrillSession) -> str:
    lines = []
    for turn in sess.turns:
        tag = "用戶" if turn.get("role") == "user" else "審計官"
        lines.append(f"【{tag}】{turn.get('content', '')}")
    return "\n".join(lines)


def _append_assistant(sess: UserGrillSession, question: GrillQuestion) -> None:
    sess.turns.append(
        {
            "role": "assistant",
            "content": question.question,
            "dimension": question.dimension,
            "why": question.why,
            "phase": str(sess.phase),
        }
    )


def _trace_l4_question(sess: UserGrillSession, question: GrillQuestion) -> None:
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=(question.question or "")[:240],
        status="open",
        from_layer=int(RahoLayer.L4_AUDITOR),
        to_layer=int(RahoLayer.L5_USER),
        payload={"phase": sess.phase, "dimension": question.dimension},
    )


def _trace_l5_answer(sess: UserGrillSession, text: str) -> None:
    STORE.resolve_user_grill(sess.session_id)
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=(text or "")[:240],
        status="resolved",
        from_layer=int(RahoLayer.L5_USER),
        to_layer=int(RahoLayer.L4_AUDITOR),
    )


def _trace_close(sess: UserGrillSession, summary: str, status: str) -> None:
    STORE.resolve_user_grill(sess.session_id, "resolved" if status == "resolved" else status)
    STORE.record_user_grill(
        sess.session_id,
        sess.query,
        summary=summary[:240],
        status=status,
        from_layer=int(RahoLayer.L4_AUDITOR),
        to_layer=int(RahoLayer.L5_USER),
        payload={"locked": sess.locked, "terminated": sess.terminated},
    )


def _failure_report(sess: UserGrillSession, reason: str) -> str:
    scores = sess.scores or {}
    lines = [
        "需求審計失敗報告",
        f"原因：{reason}",
        "禁止進入 Planner 階段。",
        "五維評分：",
    ]
    for key in DIM_KEYS:
        lines.append(f"- {DIM_LABELS[key]}：{scores.get(key, 0)}")
    return "\n".join(lines)


def _pack(
    sess: UserGrillSession,
    question: GrillQuestion | None,
    *,
    closed: bool = False,
    terminated: bool = False,
    reason: str = "",
) -> dict[str, Any]:
    overall = 0.0
    if sess.scores:
        overall = min(float(sess.scores.get(k, 0)) for k in DIM_KEYS) / 100.0
    sess.confidence = overall
    lock = SemanticLock(
        locked=sess.locked,
        confidence=sess.confidence,
        brief=sess.brief,
        session_id=sess.session_id,
        turns=sum(1 for t in sess.turns if t.get("role") == "user"),
        gaps=[k for k, v in (sess.scores or {}).items() if float(v) <= AUDITOR_DIM_THRESHOLD],
    )
    payload = lock.to_dict()
    status = "AUDITING"
    if terminated:
        status = "FAILED"
    elif sess.locked:
        status = "APPROVED_FOR_PLANNING"
    payload.update(
        {
            "should_grill": (not sess.locked) and (not terminated) and user_grill_enabled(),
            "question": question.to_dict() if question else None,
            "closed": closed or terminated or sess.locked,
            "max_turns": MAX_AUDITOR_ROUNDS,
            "phase": sess.phase,
            "phase_label": PHASE_LABELS.get(int(sess.phase or 1), ""),
            "phase_rounds": sess.phase_rounds,
            "scores": dict(sess.scores or {}),
            "ticket": sess.ticket,
            "planner": sess.planner,
            "terminated": terminated,
            "termination_reason": reason,
            "termination_report": _failure_report(sess, reason) if terminated else "",
            "status": status,
            "role": "requirement_auditor",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L4_AUDITOR), "L4 需求審計官"),
            "user_rounds": sess.user_rounds,
        }
    )
    try:
        from backend.company.raho.l0 import kernel_snapshot

        payload["l0"] = kernel_snapshot(query=sess.query)
    except Exception:
        pass
    return payload


def _terminate(sess: UserGrillSession, reason: str) -> dict[str, Any]:
    sess.terminated = True
    sess.termination_reason = reason
    report = _failure_report(sess, reason)
    sess.turns.append({"role": "assistant", "content": report, "dimension": "terminate", "why": reason})
    question = _make_question(report, why=reason, dimension="terminate", choices=[])
    _trace_close(sess, reason or "需求審計失敗", "blocked")
    return _pack(sess, question, closed=True, terminated=True, reason=reason)


def trigger_planner(final_plan: dict[str, Any]) -> dict[str, Any]:
    """五維達標後自動觸發 Dynamic Planner（L4 戰役 DAG + L3 原子拆解）。"""
    ticket = dict(final_plan or {})
    if ticket.get("status") != "APPROVED_FOR_PLANNING":
        return {"status": "REJECTED", "reason": "缺少 status=APPROVED_FOR_PLANNING 的門票"}
    try:
        score = float(ticket.get("confidence_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    if score < AUDITOR_DIM_THRESHOLD:
        return {"status": "REJECTED", "reason": f"confidence_score {score} < {AUDITOR_DIM_THRESHOLD}"}

    goal = ""
    clarified = ticket.get("clarified_goal") or {}
    if isinstance(clarified, dict):
        goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "").strip()
    if not goal:
        goal = str(ticket.get("clarified_goal") or "")[:240]

    try:
        from backend.company.raho.planner import plan_campaign

        campaign = plan_campaign(goal or "已鎖定需求")
        campaign_data = campaign.to_dict() if hasattr(campaign, "to_dict") else campaign
    except Exception as exc:
        logger.warning("L4 戰役規劃失敗，仍保留門票：%s", exc)
        campaign_data = {"status": "PLANNER_DEFERRED", "error": str(exc)}

    try:
        from backend.company.raho.commander import command_from_ticket

        commander = command_from_ticket(ticket, use_llm=False)
    except Exception as exc:
        logger.warning("L3 戰術拆解失敗，仍保留門票：%s", exc)
        commander = {"status": "COMMANDER_DEFERRED", "error": str(exc)}

    return {
        "status": "PLANNER_TRIGGERED",
        "ticket": ticket,
        "campaign": campaign_data,
        "commander": commander,
    }


def _approve(sess: UserGrillSession) -> dict[str, Any]:
    ticket = build_ticket(sess)
    sess.ticket = ticket
    sess.locked = True
    sess.brief = format_locked_brief(sess, ticket)
    sess.confidence = min(float(sess.scores.get(k, 0)) for k in DIM_KEYS) / 100.0
    try:
        sess.planner = trigger_planner(ticket)
    except Exception as exc:
        logger.warning("自動觸發 Planner 失敗：%s", exc)
        sess.planner = {"status": "PLANNER_DEFERRED", "error": str(exc)}
    _trace_close(sess, "五維達標，門票已核發", "resolved")
    return _pack(sess, None, closed=True)


def _ask_next(sess: UserGrillSession, *, prefix: str = "") -> dict[str, Any]:
    gaps = [k for k, v in (sess.scores or {}).items() if float(v) <= AUDITOR_DIM_THRESHOLD]
    phase = int(sess.phase or 1)
    if not sess.user_rounds and not prefix:
        contextual = _contextual_first_question(sess.query)
        if contextual:
            if 1 not in sess.asked_ids:
                sess.asked_ids.append(1)
            text = _with_phase_tag(contextual.question, phase)
            question = _make_question(
                text,
                why=contextual.why,
                dimension=contextual.dimension,
                choices=contextual.choices,
                question_id=1,
            )
            sess.phase_rounds = int(sess.phase_rounds or 0) + 1
            _append_assistant(sess, question)
            _trace_l4_question(sess, question)
            return _pack(sess, question)
    scenario = _scenario_next(sess)
    if scenario is not None:
        phase = int(sess.phase or 1)
        text = scenario.question
        if prefix and prefix.rstrip("：:") not in text:
            text = f"{prefix}{text}" if not text.startswith("量化失敗") else text
        text = _with_phase_tag(text, phase)
        question = _make_question(
            text,
            why=scenario.why,
            dimension=scenario.dimension,
            choices=scenario.choices,
        )
        sess.phase_rounds = int(sess.phase_rounds or 0) + 1
        _append_assistant(sess, question)
        _trace_l4_question(sess, question)
        return _pack(sess, question)
    llm_question = _llm_question(sess.query, _transcript(sess), gaps, phase)
    if llm_question is None:
        question = _next_question(sess)
    else:
        question = llm_question
        if not sess.asked_ids:
            sess.asked_ids.append(0)
    text = f"{prefix}{question.question}" if prefix else question.question
    if not sess.asked_ids or (len(sess.asked_ids) == 1 and not sess.user_rounds):
        hook = _opening_hook(sess.query)
        if hook and hook not in text:
            text = f"{hook}{text}"
    text = _with_phase_tag(text, phase)
    question = _make_question(
        text,
        why=question.why,
        dimension=question.dimension,
        choices=question.choices,
    )
    sess.phase_rounds = int(sess.phase_rounds or 0) + 1
    _append_assistant(sess, question)
    _trace_l4_question(sess, question)
    return _pack(sess, question)


def auditor_start(query: str) -> dict[str, Any]:
    """開一場需求審計。第一次絕不放行。"""
    text = (query or "").strip()
    if not text:
        raise ValueError("query 不可為空")
    try:
        from backend.company.raho.l0 import remember_query

        remember_query(text, task_id="auditor")
    except Exception:
        pass
    sess = STORE.new_user_session(text)
    sess.phase = 1
    sess.phase_rounds = 0
    sess.scores = score_dimensions(text, [])
    sess.confidence = min(sess.scores.values()) / 100.0
    return _ask_next(sess)


def auditor_turn(session_id: str, answer: str, *, force_lock: bool = False) -> dict[str, Any]:
    sess = STORE.get_user_session(session_id)
    if sess is None:
        raise KeyError(f"審計會話不存在或已過期：{session_id}")
    if sess.terminated:
        return _pack(sess, None, closed=True, terminated=True, reason=sess.termination_reason)
    if sess.locked:
        return _pack(sess, None, closed=True)

    text = (answer or "").strip()
    if not text:
        raise ValueError("answer 不可為空")

    if force_lock or _is_over_auth(text):
        _trace_l5_answer(sess, text)
        return _terminate(sess, OVER_AUTH_REPLY)

    joined_so_far = _joined(sess.query, _user_answers(sess) + [text])
    if _is_contradiction(joined_so_far) or _is_contradiction(text):
        _trace_l5_answer(sess, text)
        return _terminate(sess, "明顯矛盾：預算無限卻要求開源免費方案。需求不可行。")

    if sess.last_user_text and sess.last_user_text == text:
        sess.repeat_count = int(sess.repeat_count or 0) + 1
        if sess.repeat_count >= 1:
            _trace_l5_answer(sess, text)
            return _terminate(sess, "重複跳針：連續 2 輪重複相同句子並拒絕量化。")
    else:
        sess.repeat_count = 0
        sess.last_user_text = text

    sess.turns.append({"role": "user", "content": text})
    sess.user_rounds = int(sess.user_rounds or 0) + 1
    _trace_l5_answer(sess, text)
    answers = _user_answers(sess)
    sess.scores = score_dimensions(sess.query, answers)

    if sess.user_rounds >= MAX_AUDITOR_ROUNDS:
        if all_dims_locked(sess.scores) and (_CONFIRM.search(text) or len(text) <= 50):
            return _approve(sess)
        return _terminate(sess, f"超過 {MAX_AUDITOR_ROUNDS} 輪仍未達五維 > 90，強制終止。")

    if _fan_contract_ready(sess) and (
        _CONFIRM.search(text) or (int(sess.phase or 1) >= 4 and len(text) <= 50)
    ):
        sess.scores = {key: max(float(sess.scores.get(key, 0)), 91.0) for key in DIM_KEYS}
        return _approve(sess)

    if _is_unquantified(text, int(sess.phase or 1)):
        if int(sess.phase_rounds or 0) >= MAX_PHASE_ROUNDS:
            return _terminate(sess, f"{PHASE_LABELS.get(sess.phase)} 連續 {MAX_PHASE_ROUNDS} 輪仍在繞圈子（含無效模糊回答）。")
        return _ask_next(sess, prefix=_vague_prefix(int(sess.phase or 1)))

    target_phase = _infer_phase(sess.scores)
    if all_dims_locked(sess.scores):
        target_phase = 4
        if int(sess.phase or 1) == 4 and (_CONFIRM.search(text) or "合約" in text or "承擔" in text):
            return _approve(sess)
        if int(sess.phase or 1) == 4 and int(sess.phase_rounds or 0) >= 1 and len(text) <= 50:
            return _approve(sess)

    if target_phase > int(sess.phase or 1) and _phase_gate(int(sess.phase or 1), sess.scores):
        sess.phase = target_phase
        sess.phase_rounds = 0
    elif target_phase < int(sess.phase or 1):
        # 不後退；缺的維度用當前階段題庫補
        pass
    else:
        if int(sess.phase_rounds or 0) >= MAX_PHASE_ROUNDS and not _phase_gate(int(sess.phase or 1), sess.scores):
            return _terminate(
                sess,
                f"{PHASE_LABELS.get(sess.phase)} 已追問 {MAX_PHASE_ROUNDS} 輪仍不完整，觸發終止協議。",
            )

    if all_dims_locked(sess.scores) and int(sess.phase or 1) >= 4 and _CONFIRM.search(text):
        return _approve(sess)

    return _ask_next(sess)


def auditor_lock(session_id: str, note: str = "") -> dict[str, Any]:
    """前端『直接執行』視同過度授權，不得繞過五維門檻。"""
    sess = STORE.get_user_session(session_id)
    if sess is None:
        raise KeyError(f"審計會話不存在或已過期：{session_id}")
    text = (note or "").strip() or "你看著辦吧"
    return auditor_turn(session_id, text, force_lock=True)


def auditor_status() -> dict[str, Any]:
    return {
        "enabled": user_grill_enabled(),
        "lock_threshold": CONFIDENCE_THRESHOLD,
        "dim_threshold": AUDITOR_DIM_THRESHOLD,
        "max_rounds": MAX_AUDITOR_ROUNDS,
        "max_phase_rounds": MAX_PHASE_ROUNDS,
        "active_sessions": len(STORE.user_sessions),
        "role": "requirement_auditor",
    }
