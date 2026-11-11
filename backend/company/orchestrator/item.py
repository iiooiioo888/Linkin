"""工作項 mixin（ItemMixin）：單一工作項執行、席位 I/O 記錄、任務規格與工具權限判定。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.company.budget import CostTracker
from backend.company.events import CompanyEvent
from backend.company.role_catalog import resolve_runtime
from backend.company.role_memory import get_role_memory
from backend.company.roles import STANDARD_ROLES, RoleType
from backend.company.state import WorkItemStatus, assignee_token
from backend.core.llm import llm_kwargs_for_role, split_thinking

from ._base import OrchestratorBase

logger = logging.getLogger(__name__)


class ItemMixin(OrchestratorBase):
    """單一工作項執行、席位 I/O 記錄、任務規格與工具權限判定。"""

    async def _execute_single_item(self, goal: str, item) -> None:
        """根據指派角色執行單一工作項（含重試、超時、角色升級）。"""
        from backend.core import llm_trace

        self.work_items.transition(item.id, WorkItemStatus.EXECUTING)
        self.events.emit(CompanyEvent.WORK_ITEM_START, {
            "item_id": item.id, "title": item.title, "assignee": assignee_token(item.assignee),
        })

        # 取得角色定義
        role_type = item.assignee or RoleType.DEVELOPER
        # LLM 軌跡上下文：本協程內的所有 call_llm 自動帶 role/item/phase
        llm_trace.trace_role.set(role_type.value)
        llm_trace.trace_item_id.set(item.id)
        llm_trace.trace_phase.set("execute")
        role_def = self.config.roles.get(role_type)
        if role_def is None:
            role_def = STANDARD_ROLES.get(role_type, STANDARD_ROLES[RoleType.DEVELOPER])

        model = self.budget.resolve_model_for_tier(item.tier)
        runtime = resolve_runtime(role_type.value)
        if runtime.get("preferred_model"):
            model = runtime["preferred_model"]
        llm_opts = llm_kwargs_for_role(runtime)
        context = self._build_context(item)
        atomic = item.artifacts.get("atomic_role") or {}
        # 席位投遞脈絡：記錄 prompt 由哪些部分拼成，供監察頁展開「輸入」明細
        seat_ctx: dict[str, Any] = {
            "kind": "execute",
            "phase": "execute",
            "role_label": role_def.name,
            "tier": item.tier.value if item.tier else "",
            "temperature": runtime.get("temperature"),
            "allowed_tools": self._allowed_tools_for(item) or [],
            "input_ref": atomic.get("input_ref") or item.artifacts.get("input_ref"),
            "output_schema": str(atomic.get("output_schema") or item.artifacts.get("output_schema") or ""),
            "success_criteria": str(
                atomic.get("kpi") or atomic.get("success_criteria")
                or item.artifacts.get("success_criteria") or ""
            ),
            "context_sources": [],
        }
        try:
            from backend.company.raho.protocol import layer_label, role_to_raho_layer

            _layer = int(role_to_raho_layer(role_type))
            seat_ctx["layer"] = _layer
            seat_ctx["layer_label"] = layer_label(_layer)
        except Exception:
            seat_ctx["layer"] = None
        sources: list[dict[str, Any]] = seat_ctx["context_sources"]
        sources.append({
            "kind": "role_brief",
            "label": f"角色職責：{role_def.name}",
            "text": "；".join(role_def.responsibilities or []),
        })
        if context:
            sources.append({"kind": "dependency", "label": "上游依賴產物（上下文匯流排）", "text": context})
        try:
            from backend.company.raho.scorecard import record_execution

            record_execution(role_type.value)
        except Exception:
            pass

        # 使用角色專用執行提示（若有）
        role_specific_prompt = self.prompt_config.role_execute_prompts.get(role_type.value, "")

        if atomic.get("system_prompt") or atomic.get("input_ref"):
            from backend.services.commander import l2_task_brief

            prompt = l2_task_brief(
                title=item.title,
                input_ref=atomic.get("input_ref") or item.artifacts.get("input_ref"),
                output_schema=str(atomic.get("output_schema") or ""),
                success_criteria=str(atomic.get("kpi") or atomic.get("success_criteria") or ""),
                allowed_tools=list(atomic.get("allowed_tools") or item.artifacts.get("allowed_tools") or []),
            )
            if context and "輸入指標" not in context:
                prompt = f"{prompt}\n{context}"
            sources.append({"kind": "task_brief", "label": "L3 原子任務簡報（l2_task_brief）", "text": prompt})
        else:
            prompt = self.prompt_config.developer_execute.format(
                goal=goal,
                role_name=role_def.name,
                title=item.title,
                description=item.description,
                context=context,
            )
            sources.append({
                "kind": "template",
                "label": "通用執行模板（developer_execute）＋任務描述",
                "text": prompt,
            })
            if role_specific_prompt:
                prompt = prompt + "\n\n" + role_specific_prompt
                sources.append({"kind": "role_prompt", "label": "角色專用執行提示", "text": role_specific_prompt})
        if self._campaign and not atomic.get("input_ref"):
            try:
                from backend.company.raho.planner import CampaignMap

                campaign_brief = CampaignMap.from_dict(self._campaign, goal).brief()
                prompt = prompt + "\n\n" + campaign_brief
                sources.append({"kind": "campaign", "label": "L4 戰役簡報（CampaignMap）", "text": campaign_brief})
            except Exception:
                pass

        # ── 角色記憶注入：原子角色只讀 input_ref，不灌歷史對話 ──
        if not atomic.get("input_ref"):
            try:
                role_memory = get_role_memory(role_type.value)
                memory_context = await asyncio.to_thread(
                    role_memory.retrieve_formatted, item.title, 3
                )
                if memory_context:
                    prompt = prompt + "\n\n" + memory_context
                    sources.append({"kind": "role_memory", "label": "角色記憶注入（Chroma）", "text": memory_context})
                    self._log("role_memory_injected", {
                        "item_id": item.id, "role": role_type.value,
                    }, level=logging.DEBUG)
            except Exception:
                pass

        # 若角色有工具權限，附加工具說明（原子角色只列白名單）
        tools_text = self._get_docker_tools_for_role(role_type, item)
        if tools_text:
            prompt = prompt + "\n\n" + tools_text
            sources.append({"kind": "tools", "label": "工具白名單與用法", "text": tools_text})

        # ── 執行前憲兵檢查：走熱馬桶圈 L3→L4→L5，禁止就地吞掉上交 ──
        try:
            from backend.company.raho.escalation import resolve_grill
            from backend.company.raho.mgp import rule_inspect_instruction
            from backend.company.raho.protocol import mgp_enabled

            if mgp_enabled():
                atomic = item.artifacts.get("atomic_role") or {}
                task_spec = atomic.get("task_layer") if isinstance(atomic, dict) else None
                filled = self._allowed_tools_for(item)
                if filled and isinstance(task_spec, dict) and not task_spec.get("allowed_tools"):
                    task_spec["allowed_tools"] = list(filled)
                    if isinstance(atomic, dict):
                        atomic["allowed_tools"] = list(filled)
                pre_issues = rule_inspect_instruction(
                    item.title,
                    item.description,
                    tools_allowed=atomic.get("allowed_tools") if isinstance(atomic, dict) else None,
                    task_spec=task_spec,
                )
                if pre_issues:
                    self.events.emit(CompanyEvent.GRILL_RAISED, {
                        "item_id": item.id,
                        "title": item.title,
                        "role": role_type.value,
                        "phase": "preflight",
                        "issues": [i.to_dict() for i in pre_issues],
                    })
                    resolved = await resolve_grill(
                        run_id=self._run_id or item.id,
                        item_id=item.id,
                        goal=goal,
                        title=item.title,
                        description=item.description,
                        issues=pre_issues,
                        assignee=role_type.value,
                        superior="manager",
                        allowed_tools=self._allowed_tools_for(item),
                        on_user_pending=lambda p: self._emit_user_pending(
                            p, title=item.title, phase="preflight",
                        ),
                    )
                    self._apply_escalation_patch(item, resolved)
                    reply = str(resolved.get("reply") or "").strip()
                    if not reply:
                        reply = (
                            "指令規格不足。請依標題補齊最小交付規格，標註合理假設後繼續，"
                            "不得擴寫範圍。"
                        )
                    prompt = prompt + f"\n\n【上級對執行前質詢的裁決】\n{reply}"
                    item.description = (item.description or "") + f"\n【上級補件】{reply}"
                    sources.append({
                        "kind": "preflight_ruling",
                        "label": f"執行前質詢裁決（上級 layer={resolved.get('layer')}）",
                        "text": reply,
                    })
                    if resolved.get("timeout"):
                        self.events.emit(CompanyEvent.RAHO_TIMEOUT, {
                            "item_id": item.id, "choice": resolved.get("choice"),
                        })
                    self.events.emit(CompanyEvent.GRILL_RESOLVED, {
                        "item_id": item.id,
                        "layer": resolved.get("layer"),
                        "action": resolved.get("action"),
                        "phase": "preflight",
                        "timeout": bool(resolved.get("timeout")),
                    })
        except Exception:
            logger.debug("執行前 MGP 略過", exc_info=True)

        # ── 重試迴圈（含指數退避 + 超時 + 角色升級）──
        retry_cfg = self.config.retry_config
        last_error = None
        timeout_s = retry_cfg.deadline_seconds
        if runtime.get("timeout_ms"):
            timeout_s = max(5.0, float(runtime["timeout_ms"]) / 1000.0)
        max_retries = retry_cfg.max_retries
        if runtime.get("max_retries") is not None:
            try:
                max_retries = max(0, min(8, int(runtime["max_retries"])))
            except (TypeError, ValueError):
                max_retries = retry_cfg.max_retries
        if atomic.get("max_iterations") is not None:
            try:
                max_retries = max(0, min(max_retries, int(atomic["max_iterations"])))
            except (TypeError, ValueError):
                pass

        # 每次重試都會重算 system_prompt：先快照 user 側來源，避免跨 attempt 累積
        base_sources = list(sources)

        for attempt in range(max_retries + 1):
            import time as _time
            _start_time = _time.monotonic()
            try:
                # ── 工具調用閉環執行（含超時控制）──
                system_prompt = (
                    runtime.get("system_prompt")
                    or role_def.system_prompt
                    or self.prompt_config.developer_execute_system
                )
                system_origin = "席位 system_prompt（角色定義／運行時覆寫）"
                try:
                    from backend.company.raho.mgp import apply_mgp_system
                    from backend.company.raho.protocol import mgp_enabled

                    atomic = item.artifacts.get("atomic_role") or {}
                    if role_type == RoleType.TACTICAL_COMMANDER and not atomic.get("system_prompt"):
                        from backend.services.commander import apply_commander_system

                        system_prompt = apply_commander_system(system_prompt)
                        system_origin = "指揮官系統提示（apply_commander_system）"
                    if mgp_enabled():
                        if atomic.get("system_prompt"):
                            system_prompt = atomic["system_prompt"]
                            system_origin = "L3 原子角色實例 system_prompt"
                        system_prompt = apply_mgp_system(
                            system_prompt,
                            superior=role_type == RoleType.TACTICAL_COMMANDER,
                        )
                        system_origin += " ＋ MGP 憲法前導"
                    from backend.company.raho.l0 import inject_l0
                    from backend.company.raho.protocol import role_to_raho_layer

                    system_prompt = inject_l0(
                        system_prompt,
                        int(role_to_raho_layer(role_type)),
                        goal,
                        task_id=item.id,
                    )
                    system_origin += " ＋ L0 環境與記憶核心注入"
                    # 技能庫注入（角色可用技能 → 提示詞尾部；空庫零開銷）
                    try:
                        from backend.company.skills import inject_skills

                        before_len = len(system_prompt)
                        system_prompt = inject_skills(system_prompt, role_type.value)
                        if len(system_prompt) > before_len:
                            system_origin += " ＋ 技能庫"
                    except Exception:
                        pass
                except Exception:
                    pass
                seat_ctx["attempt"] = attempt
                seat_ctx["context_sources"] = base_sources + [
                    {"kind": "system", "label": f"系統提示詞：{system_origin}", "text": system_prompt}
                ]
                if timeout_s > 0:
                    raw = await asyncio.wait_for(
                        self._execute_with_tool_loop(
                            prompt, system_prompt, model, role_type.value, item,
                            llm_kwargs=llm_opts, seat=seat_ctx,
                        ),
                        timeout=timeout_s,
                    )
                else:
                    raw = await self._execute_with_tool_loop(
                        prompt, system_prompt, model, role_type.value, item,
                        llm_kwargs=llm_opts, seat=seat_ctx,
                    )
                raw, prompt = await self._maybe_resolve_mgp(
                    goal, item, role_type, raw, prompt, system_prompt, model, llm_opts, timeout_s,
                    seat=seat_ctx,
                )
                try:
                    from backend.company.raho.atomic_executor import parse_failed_output

                    failed = parse_failed_output(raw)
                except Exception:
                    failed = None
                if failed:
                    last_error = f"原子任務失敗：{(failed.get('partial_output') or '')[:240]}"
                    item.artifacts["partial_output"] = failed.get("partial_output") or ""
                    item.artifacts["atomic_status"] = "FAILED"
                    raise RuntimeError(last_error)

                # 記錄成功響應時間（優化 #6）
                elapsed = _time.monotonic() - _start_time
                self._concurrency_stats["success_times"].append(elapsed)

                cost = CostTracker.estimate_cost_rough(model, "high")
                self.budget.record_cost(cost, complexity="high")
                try:
                    from backend.billing.metering import meter_raho_layer

                    _raho_layer = seat_ctx.get("layer")
                    if _raho_layer is not None:
                        meter_raho_layer(
                            f"L{_raho_layer}",
                            task_id=self._run_id,
                            reference=item.id,
                            meta={"role": str(role_type), "item_id": item.id},
                        )
                except Exception:
                    pass
                item.actual_cost += cost
                item.artifacts["tokens"] = int(item.artifacts.get("tokens") or 0) + 16000

                thinking, visible = split_thinking(raw)
                item.artifacts["output"] = visible or raw
                if thinking:
                    item.artifacts["thinking"] = thinking
                self.work_items.request_review(item.id)

                self._log("execute_done", {
                    "item_id": item.id, "title": item.title, "cost": round(cost, 4),
                })
                self.events.emit(CompanyEvent.WORK_ITEM_DONE, {
                    "item_id": item.id,
                    "title": item.title,
                    "cost": round(cost, 4),
                    "role": role_type.value,
                    "output": (visible or raw)[:8000],
                    "thinking": thinking[:4000],
                    "tokens": int(item.artifacts.get("tokens") or 0),
                })

                # ── 角色記憶保存：將執行經驗存入角色記憶 ──
                try:
                    role_memory = get_role_memory(role_type.value)
                    await asyncio.to_thread(
                        role_memory.save_from_work_item,
                        item.title,
                        raw[:1000],
                        None,  # 審查結果稍後由 _review_item 補充
                        True,
                    )
                except Exception:
                    pass
                try:
                    from backend.company.raho.atomic_pool import recycle as recycle_atomic
                    from backend.company.raho.context_bus import blackboard_record
                    from backend.company.raho.protocol import RahoLayer, raho_enabled

                    if raho_enabled():
                        recycle_atomic(item)
                        blackboard_record(
                            task_id=self._run_id or item.id,
                            layer=RahoLayer.L2_EXECUTOR,
                            title=item.title,
                            content=str(item.artifacts.get("output") or "")[:800],
                            role=role_type.value,
                        )
                except Exception:
                    pass

                return  # 成功，退出

            except asyncio.TimeoutError:
                last_error = f"執行超時（{retry_cfg.deadline_seconds}s）"
                logger.warning("工作項 %s 超時（attempt %d/%d）", item.id, attempt + 1, retry_cfg.max_retries + 1)
            except Exception as exc:
                last_error = str(exc)
                logger.warning("工作項 %s 失敗（attempt %d/%d）：%s", item.id, attempt + 1, retry_cfg.max_retries + 1, exc)

            # 是否還有重試機會
            if attempt < retry_cfg.max_retries:
                backoff = retry_cfg.retry_backoff_base * (2 ** attempt)
                self.events.emit(CompanyEvent.WORK_ITEM_RETRY, {
                    "item_id": item.id, "attempt": attempt + 1, "backoff": backoff,
                })
                await asyncio.sleep(backoff)

        # ── 所有重試耗盡，嘗試角色升級 ──
        if retry_cfg.enable_escalation and role_type != RoleType.MANAGER:
            superior = self.config.get_superior(role_type)
            if superior and superior in self.config.roles:
                logger.info("工作項 %s 升級：%s → %s", item.id, role_type.value, superior.value)
                self.events.emit(CompanyEvent.WORK_ITEM_ESCALATE, {
                    "item_id": item.id, "from": role_type.value, "to": superior.value,
                })
                item.assignee = superior
                # 遞迴重試（最多一層升級）
                return await self._execute_single_item(goal, item)

        # 最終失敗
        logger.error("工作項 %s 最終失敗：%s", item.id, last_error)
        item.artifacts["error"] = last_error or "未知錯誤"
        self.work_items.block(item.id, f"執行失敗：{last_error}")
        self.events.emit(CompanyEvent.WORK_ITEM_ERROR, {
            "item_id": item.id, "title": item.title, "error": last_error,
        })

    def _record_seat_io(
        self,
        seat: dict | None,
        item,
        role_value: str,
        *,
        prompt: str,
        system: str,
        model: str | None,
        response: str,
        step: int,
        llm_kwargs: dict | None = None,
        duration_ms: float | None = None,
        tool_steps: int = 0,
        final: bool = True,
        error: str = "",
        degraded: bool = False,
        cost_usd: float | None = None,
    ) -> None:
        """落一筆席位投遞軌跡（全文 prompt/system/response + 來源分解）。

        同時寫入 seat_io 倉（監察餵給）與 tracer（/tasks/{id}/trace）；
        任何失敗都不得影響公司主流程。
        """
        meta = seat or {}
        record = {
            "run_id": self._run_id or "",
            "task_id": self.task_id or "",
            "item_id": getattr(item, "id", "") or "",
            "title": getattr(item, "title", "") or "",
            "role": role_value,
            "role_label": meta.get("role_label") or "",
            "layer": meta.get("layer"),
            "layer_label": meta.get("layer_label") or "",
            "lane": meta.get("lane") or "",
            "kind": meta.get("kind") or "execute",
            "attempt": meta.get("attempt", 0),
            "step": step,
            "tool_steps": tool_steps,
            "final": final,
            "model": model or "",
            "tier": meta.get("tier") or "",
            "temperature": (llm_kwargs or {}).get("temperature", meta.get("temperature")),
            "prompt": prompt,
            "system": system,
            "response": response,
            "duration_ms": round(float(duration_ms), 1) if duration_ms is not None else None,
            "cost_usd": round(float(cost_usd), 6) if cost_usd is not None else None,
            "error": error,
            "degraded": degraded,
            "allowed_tools": meta.get("allowed_tools") or [],
            "input_ref": meta.get("input_ref"),
            "output_schema": meta.get("output_schema") or "",
            "success_criteria": meta.get("success_criteria") or "",
            "context_sources": meta.get("context_sources") or [],
        }
        try:
            from backend.company.seat_io import record_seat_io

            record_seat_io(record)
        except Exception:
            logger.debug("席位 I/O 軌跡記錄異常（已忽略）", exc_info=True)
        try:
            if self.tracer is not None:
                self.tracer.log_llm_call(
                    prompt,
                    response,
                    model=model,
                    system=system,
                    duration_ms=duration_ms,
                    phase=str(meta.get("phase") or "execute"),
                    role=role_value,
                    item_id=str(record["item_id"]),
                    iteration=int(meta.get("attempt") or 0),
                )
        except Exception:
            logger.debug("席位 LLM 調用寫入 trace 異常（已忽略）", exc_info=True)

    def _seat_meta(
        self,
        role_type: RoleType,
        *,
        kind: str,
        phase: str,
        role_label: str = "",
        attempt: int = 0,
    ) -> dict[str, Any]:
        """非執行席位（審查／整合／終審）的投遞脈絡，無工具閉環故無來源分解。"""
        meta: dict[str, Any] = {
            "kind": kind,
            "phase": phase,
            "attempt": attempt,
            "role_label": role_label,
        }
        try:
            from backend.company.raho.protocol import layer_label, role_to_raho_layer

            layer = int(role_to_raho_layer(role_type))
            meta["layer"] = layer
            meta["layer_label"] = layer_label(layer)
        except Exception:
            meta["layer"] = None
        return meta

    def _task_spec_from_item(self, item) -> dict[str, Any]:
        artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
        layer = artifacts.get("task_layer")
        if isinstance(layer, dict) and layer:
            return layer
        atomic_raw = artifacts.get("atomic_role")
        atomic = atomic_raw if isinstance(atomic_raw, dict) else {}
        inner = atomic.get("task_layer")
        if isinstance(inner, dict) and inner:
            return inner
        return {
            "task_description": item.description or item.title,
            "input_ref": artifacts.get("input_ref"),
            "allowed_tools": artifacts.get("allowed_tools") or [],
            "success_criteria": artifacts.get("success_criteria") or "",
            "output_schema": artifacts.get("output_schema") or "",
        }

    def _allowed_tools_for(self, item) -> list[str] | None:
        artifacts = item.artifacts if isinstance(getattr(item, "artifacts", None), dict) else {}
        tools = artifacts.get("allowed_tools")
        if isinstance(tools, list) and tools:
            return [str(t) for t in tools]
        atomic = artifacts.get("atomic_role") if isinstance(artifacts.get("atomic_role"), dict) else {}
        nested = atomic.get("allowed_tools") if isinstance(atomic, dict) else None
        if isinstance(nested, list) and nested:
            return [str(t) for t in nested]
        blob = f"{getattr(item, 'title', '')}\n{getattr(item, 'description', '')}"
        try:
            from backend.services.commander import fill_allowed_tools

            inferred = fill_allowed_tools(blob)
        except Exception:
            inferred = []
        if inferred:
            artifacts["allowed_tools"] = list(inferred)
            if isinstance(atomic, dict):
                atomic["allowed_tools"] = list(inferred)
                layer = atomic.get("task_layer")
                if isinstance(layer, dict):
                    layer["allowed_tools"] = list(inferred)
            return inferred
        return None
