"""審查整合 mixin（ReviewMixin）：L1 憲兵檢查、Reviewer 審查、退回重做、整合與任務經理終審。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from backend.company.budget import CostTracker
from backend.company.events import CompanyEvent
from backend.company.role_catalog import resolve_runtime
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.state import BudgetTier, WorkItemStatus, assignee_token
from backend.core.llm import llm_kwargs_for_role, parse_json_response, split_thinking

from ._base import OrchestratorBase, _llm_thread
from ._compat import call_llm

logger = logging.getLogger(__name__)


class ReviewMixin(OrchestratorBase):
    """L1 憲兵檢查、Reviewer 審查、退回重做、整合與任務經理終審。"""

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

    async def _review_item(self, goal: str, item, max_rounds: int) -> None:
        """L1 憲兵閘門 → Reviewer 審查工作項交付物。"""
        from backend.core import llm_trace

        llm_trace.trace_role.set("reviewer")
        llm_trace.trace_item_id.set(item.id)
        llm_trace.trace_phase.set("review")
        review_round = 0

        while review_round < max_rounds:
            review_round += 1
            current = self.work_items.get(item.id)
            if not current or current.status != WorkItemStatus.IN_REVIEW:
                break

            l1 = await self._run_l1_inspect(goal, current, review_round, max_rounds)
            if l1 is not None and getattr(l1, "verdict", "") == "REWORK":
                feedback = l1.details or "L1 憲兵退回重做"
                if l1.grill:
                    feedback = l1.grill.required_fix or l1.grill.details or feedback
                try:
                    from backend.company.raho.store import STORE as _RAHO_STORE

                    _RAHO_STORE.revoke_signed(current.id)
                except Exception:
                    pass
                current.artifacts["l1_signed"] = False
                self.work_items.request_rework(item.id, feedback)
                self._log("review_rework", {
                    "item_id": item.id, "round": review_round, "feedback": feedback[:200], "gate": "l1",
                })
                self.events.emit(CompanyEvent.REVIEW_REWORK, {
                    "item_id": item.id, "round": review_round, "feedback": feedback[:200], "gate": "l1",
                })
                await self._rework_item(goal, current, feedback)
                continue
            if l1 is not None and getattr(l1, "verdict", "") == "ESCALATE":
                feedback = l1.details or "L1 向上呈報"
                if l1.grill:
                    feedback = l1.grill.suggested_fix or l1.grill.details or feedback
                reply = ""
                esc = current.artifacts.get("l1_escalation") if isinstance(current.artifacts, dict) else {}
                if isinstance(esc, dict):
                    reply = str(esc.get("reply") or "")
                if reply:
                    self.work_items.request_rework(item.id, reply)
                    self.events.emit(CompanyEvent.REVIEW_REWORK, {
                        "item_id": item.id, "round": review_round, "feedback": reply[:200], "gate": "l1",
                    })
                    await self._rework_item(goal, current, reply)
                    continue
                self.work_items.block(item.id, feedback)
                self.events.emit(CompanyEvent.WORK_ITEM_ESCALATE, {
                    "item_id": item.id, "from": "l1", "to": "l3",
                })
                break

            role_def = self.config.roles.get(RoleType.REVIEWER, STANDARD_ROLES[RoleType.REVIEWER])
            model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
            runtime = resolve_runtime(RoleType.REVIEWER.value)
            if runtime.get("preferred_model"):
                model = runtime["preferred_model"]
            llm_opts = llm_kwargs_for_role(runtime)

            artifact_text = current.artifacts.get("output", str(current.artifacts))

            prompt = self.prompt_config.reviewer_review.format(
                goal=goal,
                title=current.title,
                description=current.description,
                artifact=artifact_text[:8000],  # 限制長度
            )

            system_prompt = (
                runtime.get("system_prompt")
                or role_def.system_prompt
                or self.prompt_config.reviewer_system
            )
            try:
                from backend.company.skills import inject_skills

                system_prompt = inject_skills(system_prompt, RoleType.REVIEWER.value)
            except Exception:
                pass
            _review_start = time.monotonic()
            try:
                raw = await _llm_thread(
                    call_llm,
                    prompt,
                    system=system_prompt,
                    model=model,
                    **llm_opts,
                )
                cost = CostTracker.estimate_cost_rough(model, "medium")
                self.budget.record_cost(cost, complexity="medium")
                current.actual_cost += cost
                self._record_seat_io(
                    self._seat_meta(
                        RoleType.REVIEWER, kind="review", phase="review",
                        role_label=role_def.name, attempt=review_round,
                    ),
                    current, RoleType.REVIEWER.value,
                    prompt=prompt, system=system_prompt, model=model, response=raw,
                    step=0, llm_kwargs=llm_opts,
                    duration_ms=(time.monotonic() - _review_start) * 1000.0,
                    cost_usd=cost, final=True,
                )

                result = parse_json_response(raw)

                if result.get("approved", False):
                    self.work_items.complete(item.id, {
                        "review_result": result,
                        "review_rounds": review_round,
                    })
                    self._log("review_approved", {
                        "item_id": item.id,
                        "rounds": review_round,
                        "score": result.get("score"),
                    })
                    self.events.emit(CompanyEvent.REVIEW_PASS, {
                        "item_id": item.id, "rounds": review_round, "score": result.get("score"),
                    })
                    break
                else:
                    feedback = result.get("feedback", "需修改")
                    self.work_items.request_rework(item.id, feedback)
                    self._log("review_rework", {
                        "item_id": item.id,
                        "round": review_round,
                        "feedback": feedback[:200],
                    })
                    self.events.emit(CompanyEvent.REVIEW_REWORK, {
                        "item_id": item.id, "round": review_round, "feedback": feedback[:200],
                    })

                    # 重新執行（Developer 根據回饋修改）
                    await self._rework_item(goal, current, feedback)

            except Exception as exc:
                logger.error("審查 %s 失敗：%s", item.id, exc)
                break

        # 達到最大輪數仍未通過 → 強制完成（附註未通過審查）
        current = self.work_items.get(item.id)
        if current and current.status != WorkItemStatus.DONE:
            # 若處於 EXECUTING 狀態，需先轉到 IN_REVIEW 再轉 DONE
            if current.status == WorkItemStatus.EXECUTING:
                self.work_items.transition(item.id, WorkItemStatus.IN_REVIEW)
            self.work_items.complete(item.id, {
                "force_completed": True,
                "reason": f"達到最大審查輪數 {max_rounds}",
            })
            self._log(
                "review_force_done",
                {
                    "item_id": item.id,
                    "max_rounds": max_rounds,
                    "reason": f"達到最大審查輪數 {max_rounds}，強制完成",
                },
                degraded=True,
                level=logging.INFO,
            )
            self.events.emit(CompanyEvent.REVIEW_FORCE_DONE, {
                "item_id": item.id, "max_rounds": max_rounds, "degraded": True,
            })

    async def _rework_item(self, goal: str, item, feedback: str) -> None:
        """讓 Developer 根據審查回饋修改交付物（含重試）。"""
        from backend.core import llm_trace

        self.work_items.transition(item.id, WorkItemStatus.EXECUTING)

        role_type = item.assignee or RoleType.DEVELOPER
        llm_trace.trace_role.set(role_type.value)
        llm_trace.trace_item_id.set(item.id)
        llm_trace.trace_phase.set("rework")
        role_def = self.config.roles.get(role_type)
        if role_def is None:
            role_def = STANDARD_ROLES.get(role_type, STANDARD_ROLES[RoleType.DEVELOPER])
        model = self.budget.resolve_model_for_tier(item.tier)
        runtime = resolve_runtime(role_type.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)

        context = self._build_context(item)

        prompt = f"""{self.prompt_config.developer_execute.format(
            goal=goal,
            role_name=role_def.name,
            title=item.title,
            description=item.description,
            context=context,
        )}

【審查回饋 - 請根據以下回饋修改】
{feedback}

請直接給出修改後的交付物："""

        rework_system = (
            runtime.get("system_prompt")
            or role_def.system_prompt
            or self.prompt_config.developer_execute_system
        )
        rework_seat = self._seat_meta(
            role_type, kind="rework", phase="rework", role_label=role_def.name
        )
        rework_seat["allowed_tools"] = self._allowed_tools_for(item) or []
        rework_seat["context_sources"] = [
            {"kind": "review_feedback", "label": "審查退回意見（重做依據）", "text": feedback},
            {"kind": "dependency", "label": "上游依賴產物（上下文匯流排）", "text": context},
        ]

        # ── 重試迴圈 ──
        retry_cfg = self.config.retry_config
        last_error = None

        for attempt in range(retry_cfg.max_retries + 1):
            rework_seat["attempt"] = attempt
            _rework_start = time.monotonic()
            try:
                if retry_cfg.deadline_seconds > 0:
                    raw = await asyncio.wait_for(
                        asyncio.to_thread(
                            call_llm,
                            prompt,
                            system=rework_system,
                            model=model,
                            **llm_opts,
                        ),
                        timeout=retry_cfg.deadline_seconds,
                    )
                else:
                    raw = await asyncio.to_thread(
                        call_llm,
                        prompt,
                        system=rework_system,
                        model=model,
                        **llm_opts,
                    )
                cost = CostTracker.estimate_cost_rough(model, "high")
                self.budget.record_cost(cost, complexity="high")
                item.actual_cost += cost
                self._record_seat_io(
                    rework_seat, item, role_type.value,
                    prompt=prompt, system=rework_system, model=model, response=raw,
                    step=0, llm_kwargs=llm_opts,
                    duration_ms=(time.monotonic() - _rework_start) * 1000.0,
                    cost_usd=cost, final=True,
                )

                thinking, visible = split_thinking(raw)
                item.artifacts["output"] = visible or raw
                if thinking:
                    item.artifacts["thinking"] = thinking
                self.work_items.request_review(item.id)

                self._log("rework_done", {
                    "item_id": item.id, "cost": round(cost, 4),
                })
                return

            except asyncio.TimeoutError:
                last_error = f"修改超時（{retry_cfg.deadline_seconds}s）"
            except Exception as exc:
                last_error = str(exc)
                logger.warning("修改 %s 失敗（attempt %d/%d）：%s", item.id, attempt + 1, retry_cfg.max_retries + 1, exc)

            if attempt < retry_cfg.max_retries:
                backoff = retry_cfg.retry_backoff_base * (2 ** attempt)
                self.events.emit(CompanyEvent.WORK_ITEM_RETRY, {
                    "item_id": item.id, "attempt": attempt + 1, "backoff": backoff,
                })
                await asyncio.sleep(backoff)

        # 最終失敗
        logger.error("修改 %s 最終失敗：%s", item.id, last_error)
        self.work_items.block(item.id, f"修改失敗：{last_error}")

    # ═══════════════════════════════════════════════════════════
    # 階段 3：Synthesizer 整合
    # ═══════════════════════════════════════════════════════════

    async def _review_and_synthesize(self, goal: str) -> tuple[str, dict[str, Any]]:
        """P1：Reviewer + Synthesizer 合併 — 單次 LLM 審查並整合交付物。"""
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        synth_runtime = resolve_runtime(RoleType.SYNTHESIZER.value)
        if synth_runtime.get("preferred_model"):
            model = synth_runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(synth_runtime)
        artifacts_text = self._collect_artifacts()
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.review_synth_merge.format(
            goal=goal,
            artifacts=artifacts_text,
            total_items=stats["total"],
            completed_items=stats["done"],
            review_rounds=self._count_review_rounds(),
        )

        synth_system = self.prompt_config.review_synth_merge_system
        merge_seat = self._seat_meta(
            RoleType.SYNTHESIZER, kind="synthesize", phase="synthesize",
            role_label="Reviewer＋Synthesizer 合併",
        )
        merge_seat["context_sources"] = [
            {
                "kind": "artifacts",
                "label": f"全數交付物（{stats['done']}/{stats['total']} 完成）",
                "text": artifacts_text,
            }
        ]
        _merge_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=synth_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost, complexity="high")
            self._record_seat_io(merge_seat, None, RoleType.SYNTHESIZER.value,
                                 prompt=prompt, system=synth_system, model=model, response=raw,
                                 step=0, llm_kwargs=llm_opts,
                                 duration_ms=(time.monotonic() - _merge_start) * 1000.0,
                                 cost_usd=cost, final=True)

            result = parse_json_response(raw)
            final_output = str(result.get("final_output") or raw)
            meta = {
                "merged": True,
                "quality_passed": result.get("quality_passed", True),
                "quality_score": result.get("quality_score"),
                "quality_notes": result.get("quality_notes", ""),
                "cost": round(cost, 4),
            }
            self._log("synthesize_done", meta)
            return final_output, meta

        except Exception as exc:
            logger.warning("Review+Synth 合併失敗，降級為獨立 Synthesizer：%s", exc)
            output = await self._synthesize(goal)
            return output, {"merged": False, "fallback": str(exc)}

    async def _synthesize(self, goal: str) -> str:
        """讓 Synthesizer 整合所有已完成工作項的交付物。"""
        role_def = self.config.roles.get(
            RoleType.SYNTHESIZER, STANDARD_ROLES[RoleType.SYNTHESIZER]
        )
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        runtime = resolve_runtime(RoleType.SYNTHESIZER.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)

        artifacts_text = self._collect_artifacts()
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.synthesizer_merge.format(
            goal=goal,
            artifacts=artifacts_text,
            total_items=stats["total"],
            completed_items=stats["done"],
            review_rounds=self._count_review_rounds(),
        )

        synth_system = (
            runtime.get("system_prompt")
            or role_def.system_prompt
            or self.prompt_config.synthesizer_system
        )
        synth_seat = self._seat_meta(
            RoleType.SYNTHESIZER, kind="synthesize", phase="synthesize", role_label=role_def.name
        )
        synth_seat["context_sources"] = [
            {
                "kind": "artifacts",
                "label": f"全數交付物（{stats['done']}/{stats['total']} 完成）",
                "text": artifacts_text,
            }
        ]
        _synth_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=synth_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "high")
            self.budget.record_cost(cost, complexity="high")
            self._record_seat_io(
                synth_seat, None, RoleType.SYNTHESIZER.value,
                prompt=prompt, system=synth_system, model=model, response=raw,
                step=0, llm_kwargs=llm_opts,
                duration_ms=(time.monotonic() - _synth_start) * 1000.0,
                cost_usd=cost, final=True,
            )

            self._log("synthesize_done", {"cost": round(cost, 4)})
            return raw

        except Exception as exc:
            logger.error("整合失敗：%s", exc)
            return self._collect_artifacts()  # 降級：直接拼接

    # ═══════════════════════════════════════════════════════════
    # 階段 4：Manager 最終審查
    # ═══════════════════════════════════════════════════════════

    async def _manager_final_review(self, goal: str, final_output: str) -> dict:
        """Manager 最終審查整合結果。"""
        model = self.budget.resolve_model_for_tier(BudgetTier.REASONING)
        runtime = resolve_runtime(RoleType.MANAGER.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)
        stats = self.work_items.get_stats()

        prompt = self.prompt_config.manager_final_review.format(
            goal=goal,
            final_output=final_output[:8000],
            total_items=stats["total"],
            review_rounds=self._count_review_rounds(),
            total_cost=round(self.budget.task_spent, 4),
        )

        manager_system = self.prompt_config.manager_decompose_system
        final_seat = self._seat_meta(
            RoleType.MANAGER, kind="final_review", phase="final_review",
            role_label=getattr(self.config, "name", "") or "Manager",
        )
        final_seat["context_sources"] = [
            {"kind": "deliverable", "label": "待終審的整合交付物", "text": final_output[:8000]},
            {
                "kind": "stats",
                "label": f"工作項 {stats['total']} / 審查輪數 {self._count_review_rounds()}"
                f" / 已花費 ${self.budget.task_spent:.4f}",
                "text": "",
            },
        ]
        _final_start = time.monotonic()
        try:
            raw = await _llm_thread(
                call_llm,
                prompt,
                system=manager_system,
                model=model,
                **llm_opts,
            )
            cost = CostTracker.estimate_cost_rough(model, "medium")
            self.budget.record_cost(cost, complexity="medium")
            self._record_seat_io(
                final_seat, None, RoleType.MANAGER.value,
                prompt=prompt, system=manager_system, model=model, response=raw,
                step=0, llm_kwargs=llm_opts,
                duration_ms=(time.monotonic() - _final_start) * 1000.0,
                cost_usd=cost, final=True,
            )

            result = parse_json_response(raw)
            self._log("final_review_done", result)
            return result

        except Exception as exc:
            logger.error("最終審查失敗：%s", exc)
            # 降級路徑：審查異常時自動通過，但必須留下可追蹤的持久軌跡
            self._log(
                "final_review_degraded",
                {"error": str(exc), "approved": True, "summary": "自動通過"},
                degraded=True,
                level=logging.INFO,
            )
            self.events.emit(CompanyEvent.FINAL_REVIEW_DEGRADED, {
                "error": str(exc), "degraded": True,
            })
            return {"approved": True, "summary": "自動通過", "error": str(exc), "degraded": True}
