"""L1 憲兵巡檢 mixin：執行前先檢查、必要時退回或上拋。"""

from __future__ import annotations

import asyncio
import logging

from backend.company.events import CompanyEvent
from backend.company.state import assignee_token

from .._base import OrchestratorBase

logger = logging.getLogger("backend.company.orchestrator.review")


class _ReviewL1Mixin(OrchestratorBase):
    """L1 憲兵巡檢：執行前先檢查、必要時退回或上拋。"""

    async def _run_l1_inspect(self, goal: str, item, review_round: int, max_rounds: int):
        """L1 憲兵閘門。規則驗收，不額外呼叫 LLM（除非 EVOL_RAHO_L1_LLM）。"""
        try:
            from backend.company.raho.inspector import (
                VERDICT_APPROVED,
                VERDICT_ESCALATE,
                VERDICT_REWORK,
                InspectorGate,
                source_for_artifacts,
            )
            from backend.company.raho.protocol import RahoLayer, raho_enabled
            from backend.company.raho.store import STORE as _RAHO_STORE
        except Exception:
            return None
        if not raho_enabled():
            return None
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        if not (
            artifacts.get("task_layer")
            or artifacts.get("atomic_role")
            or artifacts.get("atomic_distill")
        ):
            return None
        output = str(artifacts.get("output") or "")
        spec = self._task_spec_from_item(item)
        source = source_for_artifacts(artifacts, output)
        gate = InspectorGate()
        verdict = await asyncio.to_thread(
            gate.inspect,
            spec,
            output,
            source_data=source,
            rework_rounds=max(0, review_round - 1),
            max_rework=max(1, max_rounds),
            node_id=item.id,
            title=item.title,
        )
        item.artifacts["l1_verdict"] = verdict.to_dict()
        item.artifacts["l1_signed"] = verdict.verdict == VERDICT_APPROVED
        self.events.emit(CompanyEvent.INSPECTOR_VERDICT, {
            "item_id": item.id,
            "title": item.title,
            "verdict": verdict.verdict,
            "quality_score": verdict.quality_score,
            "test_results": verdict.test_results,
            "round": review_round,
        })
        if self._run_id:
            target_layer = (
                int(RahoLayer.L2_EXECUTOR)
                if verdict.grill and verdict.grill.target.endswith("Executor")
                else int(RahoLayer.L3_COMMANDER)
            )
            node = _RAHO_STORE.add_node(
                self._run_id,
                from_layer=int(RahoLayer.L1_INSPECTOR),
                to_layer=target_layer if verdict.verdict != VERDICT_APPROVED else int(RahoLayer.L2_EXECUTOR),
                kind="inspect",
                summary=(verdict.details or verdict.verdict)[:240],
                status="resolved" if verdict.verdict == VERDICT_APPROVED else "open",
                payload={"item_id": item.id, "verdict": verdict.to_dict()},
                goal=goal,
                from_role="constitutional_inspector",
                to_role=(
                    "tactical_commander"
                    if target_layer == int(RahoLayer.L3_COMMANDER) and verdict.verdict != VERDICT_APPROVED
                    else "atomic_executor"
                ),
            )
            if verdict.verdict == VERDICT_APPROVED:
                _RAHO_STORE.resolve_node(self._run_id, node.node_id, "resolved")
        if verdict.verdict == VERDICT_APPROVED:
            return verdict
        if verdict.verdict == VERDICT_REWORK:
            feedback = verdict.details or "L1 憲兵退回重做"
            if verdict.grill:
                feedback = verdict.grill.required_fix or verdict.grill.details or feedback
                self.events.emit(CompanyEvent.GRILL_RAISED, {
                    "item_id": item.id,
                    "title": item.title,
                    "phase": "inspect",
                    "target": verdict.grill.target,
                    "issues": [verdict.grill.to_issue().to_dict()],
                })
            return verdict
        if verdict.verdict == VERDICT_ESCALATE:
            try:
                from backend.company.raho.escalation import resolve_grill

                issues = [verdict.grill.to_issue()] if verdict.grill else []
                if issues:
                    result = await resolve_grill(
                        run_id=self._run_id or item.id,
                        item_id=item.id,
                        goal=goal,
                        title=item.title,
                        description=item.description,
                        issues=issues,
                        assignee=assignee_token(item.assignee) or "",
                        superior="tactical_commander",
                        allowed_tools=self._allowed_tools_for(item),
                        on_user_pending=lambda p: self._emit_user_pending(
                            p, title=item.title, phase="inspect",
                        ),
                    )
                    item.artifacts["l1_escalation"] = result
                    reply = str(result.get("reply") or "").strip()
                    if reply:
                        item.description = (item.description or "") + f"\n【L1 呈報後裁決】{reply}"
            except Exception:
                logger.debug("L1 呈報裁決略過", exc_info=True)
            return verdict
        return verdict
