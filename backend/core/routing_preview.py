"""發送前路由＋成本預覽（純規則，不呼叫 LLM）。path 與 ``resolve_execution_path`` 同源。"""

from __future__ import annotations

from typing import Any, Literal

from backend.core.execution_path import (
    _COMPLEX_QUERY_LENGTH,
    ExecutionPath,
    _complex_query_length,
    is_complex_task,
    is_minecraft_heavy_task,
    needs_opc_context,
    resolve_execution_path,
)

EstimatedCostLevel = Literal["low", "medium", "high"]


def _classify_complexity(query: str, strategy: str) -> str:
    from backend.core.cost_speed_router import classify_task_complexity

    if (strategy or "auto").strip().lower() == "simple":
        return "simple"
    return classify_task_complexity(query or "")


def _resolve_template(
    path: ExecutionPath,
    query: str,
    strategy: str,
    *,
    company_template: str | None,
) -> str | None:
    if path != "company":
        return None
    requested = (company_template or "quick_task").strip() or "quick_task"
    state: dict[str, Any] = {
        "query": query,
        "execution_strategy": strategy,
        "company_template": requested,
    }
    try:
        from backend.linkin.pipeline import resolve_linkin_company_template

        linkin = resolve_linkin_company_template(state)
        if linkin:
            return linkin
    except Exception:
        pass
    return requested


def _effective_complexity_for_tier(complexity: str, path: ExecutionPath) -> str:
    try:
        from backend.core.routing_feedback import cost_speed_complexity_boost

        boosted = cost_speed_complexity_boost(
            complexity,
            execution_path=path if path in ("simple", "company") else None,
        )
        if boosted:
            return boosted
    except Exception:
        pass
    return complexity


def _tier_and_model_hint(complexity: str, path: ExecutionPath) -> tuple[str, str]:
    from backend.core.stage_router import resolve_stage_model

    comp = _effective_complexity_for_tier(complexity, path)
    model = resolve_stage_model(
        "generate",
        complexity=comp,
        execution_path=path,
    )
    tier = comp if comp in ("simple", "medium", "complex") else "simple"
    return tier, model


def _estimated_cost(path: ExecutionPath, complexity: str) -> dict[str, Any]:
    if path == "company":
        level: EstimatedCostLevel = "high"
        est_tokens = 12000
    elif path == "minecraft_ops":
        level = "medium"
        est_tokens = 2500
    elif path == "opc":
        level = "medium"
        est_tokens = 6000
    elif complexity == "medium":
        level = "medium"
        est_tokens = 3500
    elif complexity == "complex":
        level = "high"
        est_tokens = 5000
    else:
        level = "low"
        est_tokens = 1200
    return {"level": level, "est_tokens": est_tokens}


_PREVIEW_CONTEXT_ALLOWLIST: frozenset[str] = frozenset()


def _collect_reason_codes(
    query: str,
    strategy: str,
    path: ExecutionPath,
) -> list[str]:
    text = query or ""
    strat = (strategy or "auto").strip().lower()
    codes: list[str] = []

    if strat == "simple":
        codes.append("forced_simple")
        return codes
    if strat == "company":
        codes.append("forced_company")
        return codes

    try:
        from backend.core.routing_feedback import feedback_upgrade_state

        fb = feedback_upgrade_state()
        if fb.get("company_ratio_cap_hit"):
            codes.append("company_ratio_capped")
        if fb.get("company_escalation_allowed") and path == "company":
            threshold = _complex_query_length()
            if threshold > _COMPLEX_QUERY_LENGTH and len(text) >= threshold:
                codes.append("routing_feedback_escalated")
    except Exception:
        pass

    if needs_opc_context(text) and path == "opc":
        codes.append("opc_keyword")

    if path == "minecraft_ops":
        codes.append("mc_single_action")
        return codes

    if path == "company":
        try:
            from backend.linkin.pipeline import is_linkin_complex_task

            if is_linkin_complex_task(text):
                codes.append("linkin_complex")
        except Exception:
            pass
        if is_minecraft_heavy_task(text):
            codes.append("minecraft_heavy")
        if _COMPANY_KEYWORDS_hit(text):
            codes.append("company_keyword")
        threshold = _complex_query_length()
        if len(text) >= threshold:
            codes.append("length_over_threshold")
        if not codes:
            codes.append("rule_company")
    elif is_complex_task(text, use_routing_feedback=True) and path == "simple":
        # cost_speed 或規則將複雜查詢留在 simple
        if len(text) >= _complex_query_length():
            codes.append("length_over_threshold")

    return codes


def _COMPANY_KEYWORDS_hit(text: str) -> bool:
    from backend.core.execution_path import _COMPANY_KEYWORDS

    return bool(_COMPANY_KEYWORDS.search(text or ""))


def build_routing_preview(
    query: str,
    *,
    mode: str = "auto",
    context: dict[str, Any] | None = None,
    company_template: str | None = None,
    task_complexity: str | None = None,
) -> dict[str, Any]:
    """組裝與執行路徑一致的預覽 payload（供 ``POST /routing/preview`` 與 SSE）。"""
    strategy = (mode or "auto").strip().lower()
    complexity = (task_complexity or "").strip() or _classify_complexity(query, strategy)
    path = resolve_execution_path(
        query,
        strategy,
        task_complexity=complexity,
    )
    template = _resolve_template(path, query, strategy, company_template=company_template)
    tier, model_hint = _tier_and_model_hint(complexity, path)

    from backend.core.reflection_limits import reflection_max_iterations

    routing_state: dict[str, Any] = {
        "query": query,
        "execution_strategy": strategy,
        "task_complexity": complexity,
        "resolved_execution_path": path,
    }
    if context:
        for key in _PREVIEW_CONTEXT_ALLOWLIST:
            if key in context and key not in routing_state:
                routing_state[key] = context[key]

    return {
        "path": path,
        "template": template,
        "complexity": complexity,
        "tier": tier,
        "model_hint": model_hint,
        "max_reflection_rounds": reflection_max_iterations(
            routing_state,
            routing_preview=True,
        ),
        "reason_codes": _collect_reason_codes(query, strategy, path),
        "estimated_cost": _estimated_cost(path, complexity),
    }


__all__ = ["build_routing_preview"]
