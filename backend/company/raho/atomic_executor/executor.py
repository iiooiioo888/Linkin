"""戰前檢查、結構化協議解析與 L2 原子執行者工廠。"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.company.raho.protocol import MAX_SUPERIOR_ROUNDS, GrillIssue

from .constants import (
    _FAILED_JSON,
    _GRILL_JSON,
    _LARGE_INPUT,
    _SUBJECTIVE_ONLY,
    _TINY_OUTPUT,
    BLOCKER_CAPACITY,
    BLOCKER_CONSTRAINT,
    BLOCKER_CRITERIA,
    BLOCKER_INPUT,
    BLOCKER_TOOL,
    BLOCKER_TYPES,
    CONSTITUTION_MARKER,
    GRILL_TARGET_L3,
    GRILL_TARGET_L4,
    MIN_RETRY_ITERATIONS,
    MIN_TOKEN_BUDGET,
)
from .helpers import _is_empty_ref, spec_from_mapping
from .models import AtomicTaskSpec, GrillMessage
from .prompt import CONSTITUTION_LAYER, render_task_layer


def run_preflight(spec: AtomicTaskSpec | dict[str, Any]) -> list[GrillMessage]:
    """執行前規則檢查（不呼叫 LLM）。未通過則回傳結構化 Grill。"""
    task = spec_from_mapping(spec)
    hits: list[GrillMessage] = []

    if _is_empty_ref(task.input_ref):
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_INPUT,
                details="INPUT_REF 為空值或占位符，無法定位任何輸入資料。",
                suggested_fix="請提供有效的共享記憶體路徑（例如 shared_memory://uploads/sales.csv），或直接把資料附在指令中。",
            )
        )

    needs_tool = bool(
        re.search(
            r"(pdf|csv|url|http|檔案|文件|爬取|擷取|讀檔|解析|下載|寫入)",
            task.task_description,
            re.IGNORECASE,
        )
    )
    if not task.allowed_tools and needs_tool:
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_TOOL,
                details="ALLOWED_TOOLS 為空，但任務描述需要讀檔／擷取／解析類工具。",
                suggested_fix="請重發工具白名單，至少包含完成此任務所需的一個已知工具。",
            )
        )

    criteria = task.success_criteria.strip()
    if not criteria or _SUBJECTIVE_ONLY.match(criteria):
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_CRITERIA,
                details=f"SUCCESS_CRITERIA「{criteria or '（空）'}」缺少可驗證的客觀條件。",
                suggested_fix="請改寫為可檢查條件，例如「產出 CSV 至少 10 行且無空值」或指定必填 JSON 鍵。",
            )
        )

    blob = f"{task.task_description} {task.output_schema}"
    if _LARGE_INPUT.search(task.task_description) and _TINY_OUTPUT.search(task.output_schema):
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_CAPACITY,
                details=f"任務要求處理大規模輸入，但 OUTPUT_SCHEMA「{task.output_schema}」容量過小，判定為容量矛盾。",
                suggested_fix="請放寬輸出上限（例如至少 400 字），或把任務改成擷取單頁／單表。",
            )
        )
    elif "摘要" in task.task_description and _TINY_OUTPUT.search(task.output_schema) and _LARGE_INPUT.search(blob):
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_CAPACITY,
                details="摘要目標與輸出 Schema 容量互相矛盾。",
                suggested_fix="放寬字數限制，或縮小輸入範圍。",
            )
        )

    if task.max_iterations < MIN_RETRY_ITERATIONS or task.token_budget < MIN_TOKEN_BUDGET:
        hits.append(
            GrillMessage(
                blocker_type=BLOCKER_CONSTRAINT,
                details=(
                    f"MAX_ITERATIONS={task.max_iterations}、TOKEN_BUDGET={task.token_budget}，"
                    f"第一次失敗後沒有足夠餘量重試。"
                ),
                suggested_fix=f"請至少給 {MIN_RETRY_ITERATIONS} 次迭代與 {MIN_TOKEN_BUDGET} token 預算。",
            )
        )

    return hits


def preflight_issues(spec: AtomicTaskSpec | dict[str, Any]) -> list[GrillIssue]:
    return [msg.to_issue() for msg in run_preflight(spec)]


def escalate_grill(message: GrillMessage, *, to: str = GRILL_TARGET_L4) -> GrillMessage:
    """把未解的 Grill 升級為 Escalate。"""
    return GrillMessage(
        type="ESCALATE",
        target=to,
        blocker_type=message.blocker_type,
        details=f"上級 {MAX_SUPERIOR_ROUNDS} 輪內未能解除阻塞：{message.details}",
        suggested_fix=message.suggested_fix,
    )


def parse_structured_protocol(text: str) -> GrillMessage | None:
    """從產出抽出結構化 GRILL / ESCALATE JSON。"""
    raw = text or ""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else None
    if blob is None:
        match = _GRILL_JSON.search(raw)
        blob = match.group(0) if match else None
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    kind = str(data.get("type") or "").upper()
    if kind not in {"GRILL", "ESCALATE"}:
        return None
    blocker = str(data.get("blocker_type") or BLOCKER_INPUT)
    if blocker not in BLOCKER_TYPES:
        blocker = BLOCKER_INPUT
    target = str(data.get("target") or (GRILL_TARGET_L4 if kind == "ESCALATE" else GRILL_TARGET_L3))
    return GrillMessage(
        type=kind,
        target=target,
        blocker_type=blocker,
        details=str(data.get("details") or "")[:800],
        suggested_fix=str(data.get("suggested_fix") or "")[:400],
    )


def parse_failed_output(text: str) -> dict[str, Any] | None:
    raw = text or ""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else None
    if blob is None:
        match = _FAILED_JSON.search(raw)
        blob = match.group(0) if match else None
    if not blob:
        stripped = raw.strip()
        if stripped.startswith("{") and "FAILED" in stripped:
            blob = stripped
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("status") or "").upper() != "FAILED":
        return None
    return {
        "status": "FAILED",
        "partial_output": str(data.get("partial_output") or "")[:4000],
    }


class AtomicExecutorFactory:
    """孵化 L2 原子執行者：憲法層唯讀，任務層由 L3 填入。"""

    CONSTITUTION_LAYER = CONSTITUTION_LAYER
    CONSTITUTION_MARKER = CONSTITUTION_MARKER

    @classmethod
    def spawn(cls, task_spec: dict[str, Any] | AtomicTaskSpec) -> str:
        """輸入 L3 atomic_role_instances 單項，輸出完整 System Prompt。"""
        spec = spec_from_mapping(task_spec)
        return f"{cls.CONSTITUTION_LAYER.rstrip()}\n\n{render_task_layer(spec)}"

    @classmethod
    def spawn_card(cls, task_spec: dict[str, Any] | AtomicTaskSpec) -> dict[str, Any]:
        spec = spec_from_mapping(task_spec)
        if not spec.allowed_tools:
            try:
                from backend.services.commander import fill_allowed_tools

                spec.allowed_tools = fill_allowed_tools(spec.task_description)
            except Exception:
                pass
        prompt = cls.spawn(spec)
        grills = run_preflight(spec)
        return {
            "template_id": spec.template_id or spec.instance_id or "generic",
            "name": spec.name or spec.instance_id or "原子執行員",
            "kpi": spec.success_criteria,
            "system_prompt": prompt,
            "task_layer": spec.to_dict(),
            "allowed_tools": list(spec.allowed_tools),
            "input_ref": spec.input_ref,
            "output_schema": spec.output_schema,
            "success_criteria": spec.success_criteria,
            "max_iterations": spec.max_iterations,
            "token_budget": spec.token_budget,
            "constitution_locked": True,
            "preflight_ok": not grills,
            "preflight": [g.to_dict() for g in grills],
            "disposable": True,
        }
