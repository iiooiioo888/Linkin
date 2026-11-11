"""L1 審查主流程（自 backend.company.raho.inspector 抽出）。

Prompt 組裝、四維度規則驗收、裁決解析、簽核記憶體與 input_ref 解析。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from backend.company.raho.atomic_executor import AtomicTaskSpec, spec_from_mapping

from .constants import (
    _GRILL_JSON,
    _GROWTH_CLAIM,
    _MAX_LEN,
    _PERIOD_HINT,
    _TRACE,
    _VERDICT_JSON,
    CONSTITUTION_LAYER,
    FAIL,
    GRILL_TARGET_L2,
    GRILL_TARGET_L3,
    INSPECTION_LAYER_MARKER,
    INSPECTOR_ID,
    INSPECTOR_MARKER,
    PASS,
    TEST_EDGE,
    TEST_FACTUAL,
    TEST_KEYS,
    TEST_SCHEMA,
    TEST_SEMANTIC,
    VERDICT_APPROVED,
    VERDICT_ESCALATE,
    VERDICT_REWORK,
    VERDICTS,
)
from .models import InspectorGrill, InspectorVerdict
from .schema import _schema_result
from .similarity import _as_text, _numbers, compare_facts


def l1_llm_enabled() -> bool:
    return os.getenv("EVOL_RAHO_L1_LLM", "false").lower() in {"1", "true", "yes", "on"}


def has_inspector_constitution(prompt: str) -> bool:
    return INSPECTOR_MARKER in (prompt or "")


def sign_payload(data: str, inspector_id: str = INSPECTOR_ID) -> str:
    digest = hashlib.sha256(f"{inspector_id}|{data}".encode()).hexdigest()
    return f"L1:{digest[:20]}"


def _empty_source(source: Any) -> bool:
    if source is None:
        return False
    if isinstance(source, (list, tuple)):
        return not any(str(x).strip() for x in source)
    text = str(source).strip().lower()
    return text in {"", "null", "none", "nil", "n/a", "[]", "{}"}


def render_inspection_layer(
    spec: AtomicTaskSpec,
    l2_output: str,
    *,
    source_preview: str = "",
) -> str:
    tools = spec.allowed_tools or []
    return f"""# ==========================================
# {INSPECTION_LAYER_MARKER}
# ==========================================

## 本次驗收依據（由 L3 提供）
任務描述：{spec.task_description or "（未提供 TASK_DESCRIPTION）"}
輸出規範：{spec.output_schema or "（未提供 OUTPUT_SCHEMA）"}
輸入來源：{_as_text(spec.input_ref) or "null"}
成功標準：{spec.success_criteria or "（未提供 SUCCESS_CRITERIA）"}
工具白名單：{json.dumps(tools, ensure_ascii=False) if tools else "[]"}

## 來源數據摘要（供事實交叉比對）
{source_preview or "（未注入來源正文；若 INPUT_REF 無效，視為規劃端缺陷）"}

## L2 產出內容（待審查）
{l2_output or "（空產出）"}
"""


def compose_inspector_prompt(
    spec: AtomicTaskSpec | dict[str, Any],
    l2_output: str,
    *,
    source_preview: str = "",
) -> str:
    task = spec_from_mapping(spec)
    prompt = (
        f"{CONSTITUTION_LAYER.rstrip()}\n\n"
        f"{render_inspection_layer(task, l2_output, source_preview=source_preview)}"
    )
    try:
        from backend.company.raho.l0 import inject_l0

        return inject_l0(prompt, 1, task.task_description)
    except Exception:
        return prompt


def _semantic_result(spec: AtomicTaskSpec, output: str) -> tuple[str, str]:
    raw = (output or "").strip()
    if len(raw) < 4:
        return FAIL, "產出空洞，未回應任務描述。"
    ref = _as_text(spec.input_ref)
    desc = (spec.task_description or "").strip()
    if ref and raw == ref:
        return FAIL, "產出只複製 INPUT_REF，未經處理。"
    if desc and raw == desc:
        return FAIL, "產出只複製 TASK_DESCRIPTION，視為未完成。"
    action = re.search(r"(分析|趨勢|摘要|提取|轉換|計算|比對)", desc)
    if action and ref and raw.strip() == ref.strip():
        return FAIL, f"任務要求「{action.group(1)}」，結果只貼上原始輸入。"
    return PASS, ""


def _factual_result(
    spec: AtomicTaskSpec,
    output: str,
    source_data: Any,
) -> tuple[str, str, bool]:
    """回傳 (status, detail, planning_defect)。source_data is None 表示無法比對，略過。"""
    if source_data is None:
        return PASS, "", False
    raw = (output or "").strip()
    if _empty_source(source_data):
        if _GROWTH_CLAIM.search(raw) or _numbers(raw):
            return (
                FAIL,
                "INPUT_REF 指向的來源為空或缺資料，L2 卻輸出了具體數字／趨勢，判定為規劃端資料缺失導致的幻覺。",
                True,
            )
        return PASS, "", False
    source_text = _as_text(source_data)
    claimed = _numbers(raw)
    available = _numbers(source_text)
    invented = {n for n in claimed if n not in available and float(n) not in {0.0, 1.0}}
    period = _PERIOD_HINT.search(spec.task_description or "")
    if period and period.group(0) not in source_text and _GROWTH_CLAIM.search(raw):
        return (
            FAIL,
            f"來源數據缺少「{period.group(0)}」，L2 卻給出趨勢結論。這不是 L2 算錯，是 L3 的 INPUT_REF／任務目標有缺陷。",
            True,
        )
    if invented and available:
        sample = ", ".join(sorted(invented)[:4])
        return (
            FAIL,
            f"產出中的關鍵數據（{sample}）無法在 INPUT_REF 來源中找到對應依據，判定為幻覺。",
            False,
        )
    scores = compare_facts(raw, source_text)
    sim = scores["semantic_similarity"]
    return f"{PASS} (相似度 {sim:.2f})", "", False


def _edge_result(
    spec: AtomicTaskSpec,
    output: str,
    source_data: Any,
) -> tuple[str, str, bool]:
    raw = (output or "").strip()
    if _TRACE.search(raw):
        return FAIL, "輸入邊界情況下 L2 報錯崩潰，未做極端值處理。", False
    schema = spec.output_schema or ""
    match = _MAX_LEN.search(schema)
    if match:
        limit = next((int(g) for g in match.groups() if g), None)
        if limit and len(raw) > limit * 2 and "摘要" not in raw and "截斷" not in raw:
            return FAIL, f"產出遠超 OUTPUT_SCHEMA 上限（{limit}），且未截斷或摘要。", False
    if source_data is not None and _empty_source(source_data):
        if _GROWTH_CLAIM.search(raw) or (len(raw) > 40 and _numbers(raw)):
            return FAIL, "來源為空值時 L2 仍幻想出完整結論，應回報資料缺失而非編造。", True
    return PASS, "", False


def run_inspection(
    spec: AtomicTaskSpec | dict[str, Any],
    l2_output: str,
    *,
    source_data: Any = None,
    rework_rounds: int = 0,
    max_rework: int = 2,
    node_id: str = "",
) -> InspectorVerdict:
    """規則驗收（不呼叫 LLM）。四維度依序測試，失敗即中斷。"""
    task = spec_from_mapping(spec)
    results = {key: PASS for key in TEST_KEYS}
    grill: InspectorGrill | None = None
    details = ""
    planning = False

    status, detail = _schema_result(task, l2_output)
    results["schema_validation"] = status
    if status == FAIL:
        details = detail
        grill = InspectorGrill(
            target=GRILL_TARGET_L2,
            failed_test=TEST_SCHEMA,
            details=detail,
            required_fix="請依 OUTPUT_SCHEMA 補齊必填欄位並重新提交結構化產出。",
        )
    else:
        status, detail = _semantic_result(task, l2_output)
        results["semantic_integrity"] = status
        if status == FAIL:
            details = detail
            grill = InspectorGrill(
                target=GRILL_TARGET_L2,
                failed_test=TEST_SEMANTIC,
                details=detail,
                required_fix="請真正完成任務描述，禁止複製貼上或交空洞產出。",
            )
        else:
            status, detail, planning = _factual_result(task, l2_output, source_data)
            results["factual_consistency"] = status
            if status == FAIL:
                details = detail
                if planning:
                    grill = InspectorGrill(
                        target=GRILL_TARGET_L3,
                        failed_test=TEST_FACTUAL,
                        details=detail,
                        suggested_fix="請修正 INPUT_REF 指向有效數據源，或改寫任務目標以符合現有資料。",
                    )
                else:
                    grill = InspectorGrill(
                        target=GRILL_TARGET_L2,
                        failed_test=TEST_FACTUAL,
                        details=detail,
                        required_fix="請只使用 INPUT_REF 來源中可核對的數據，刪除無依據的數字與結論。",
                    )
            else:
                status, detail, planning = _edge_result(task, l2_output, source_data)
                results["edge_case"] = status
                if status == FAIL:
                    details = detail
                    if planning:
                        grill = InspectorGrill(
                            target=GRILL_TARGET_L3,
                            failed_test=TEST_EDGE,
                            details=detail,
                            suggested_fix="請補齊輸入或放寬不可能的約束後再通知 L2 重跑。",
                        )
                    else:
                        grill = InspectorGrill(
                            target=GRILL_TARGET_L2,
                            failed_test=TEST_EDGE,
                            details=detail,
                            required_fix="請處理空值／超限等極端情況，崩潰時回報 FAILED 而非幻想成功。",
                        )

    failed = [k for k, v in results.items() if v == FAIL]
    exhausted = rework_rounds >= max_rework and failed
    if not failed:
        signature = sign_payload(l2_output)
        return InspectorVerdict(
            verdict=VERDICT_APPROVED,
            test_results=results,
            final_approved_data=l2_output,
            quality_score=96.5,
            details="",
            signature=signature,
            node_id=node_id,
        )

    escalate = bool(
        exhausted
        or (grill and grill.target == GRILL_TARGET_L3)
        or planning
    )
    if escalate and grill is not None:
        grill.type = "ESCALATE" if exhausted or grill.target == GRILL_TARGET_L3 else "GRILL"
        if exhausted:
            grill.target = GRILL_TARGET_L3
            grill.type = "ESCALATE"
            details = f"L2 修正次數已耗盡仍未達標：{details}"
            grill.details = details
    verdict = VERDICT_ESCALATE if escalate else VERDICT_REWORK
    score = max(0.0, 60.0 - 15.0 * len(failed))
    return InspectorVerdict(
        verdict=verdict,
        test_results=results,
        final_approved_data="",
        quality_score=score,
        details=details,
        grill=grill,
        node_id=node_id,
    )


def parse_verdict(text: str) -> InspectorVerdict | None:
    raw = text or ""
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else None
    if blob is None:
        match = _VERDICT_JSON.search(raw)
        blob = match.group(0) if match else None
    if not blob:
        stripped = raw.strip()
        if stripped.startswith("{") and "verdict" in stripped:
            blob = stripped
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    kind = str(data.get("verdict") or "").upper()
    if kind not in VERDICTS:
        return None
    test_results = data.get("test_results")
    tests = test_results if isinstance(test_results, dict) else {}
    normalized = {key: str(tests.get(key) or PASS) for key in TEST_KEYS}
    try:
        score = float(data.get("quality_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return InspectorVerdict(
        verdict=kind,
        inspector_id=str(data.get("inspector_id") or INSPECTOR_ID),
        test_results=normalized,
        final_approved_data=str(data.get("final_approved_data") or ""),
        quality_score=score,
        details=str(data.get("details") or ""),
        signature=str(data.get("signature") or ""),
        node_id=str(data.get("node_id") or ""),
    )


def parse_inspector_grill(text: str) -> InspectorGrill | None:
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
    failed = str(data.get("failed_test") or "")
    if not failed and not data.get("target"):
        return None
    if "failed_test" not in data and "required_fix" not in data:
        return None
    target = str(data.get("target") or GRILL_TARGET_L2)
    return InspectorGrill(
        type=kind,
        target=target,
        failed_test=failed or TEST_SCHEMA,
        details=str(data.get("details") or "")[:800],
        required_fix=str(data.get("required_fix") or "")[:400],
        suggested_fix=str(data.get("suggested_fix") or "")[:400],
    )


def write_signed_memory(
    node_id: str,
    verdict: InspectorVerdict,
    *,
    title: str = "",
) -> dict[str, Any] | None:
    """只有 APPROVED 才能寫入共享記憶體。"""
    if verdict.verdict != VERDICT_APPROVED or not node_id:
        return None
    from backend.company.raho.blackboard import signed_entry
    from backend.company.raho.store import STORE

    signature = verdict.signature or sign_payload(verdict.final_approved_data)
    verdict.signature = signature
    record = signed_entry(
        node_id=node_id,
        data=verdict.final_approved_data,
        signature=signature,
        inspector_id=INSPECTOR_ID,
        quality_score=verdict.quality_score,
        test_results=dict(verdict.test_results),
        title=title,
        verdict=verdict.verdict,
    )
    STORE.write_signed(node_id, record)
    return record


def read_signed_memory(node_id: str) -> dict[str, Any] | None:
    from backend.company.raho.store import STORE

    record = STORE.read_signed(node_id)
    if not record or not record.get("signed"):
        return None
    return record


def source_for_artifacts(artifacts: dict[str, Any] | None, l2_output: str = "") -> Any:
    """從工作項 artifacts 取出可供事實比對的來源；無法比對則回 None。"""
    blob = artifacts if isinstance(artifacts, dict) else {}
    if "source_data" in blob:
        return blob.get("source_data")
    task_layer = blob.get("task_layer")
    layer = task_layer if isinstance(task_layer, dict) else {}
    ref = blob.get("input_ref") if "input_ref" in blob else layer.get("input_ref")
    signed = resolve_input_ref(ref)
    if signed:
        return signed.get("data")
    if _is_blank_ref(ref) and _GROWTH_CLAIM.search(l2_output or ""):
        return ""
    return None


def _is_blank_ref(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "null", "none", "nil", "n/a", "undefined", "tbd"}


def resolve_input_ref(ref: Any) -> dict[str, Any] | None:
    """解析 shared_memory:// 指標；未簽核則回傳 None。"""
    from backend.company.raho.blackboard import is_memory_uri, parse_node_id
    from backend.company.raho.store import STORE

    if not is_memory_uri(ref):
        return None
    return STORE.read_signed(parse_node_id(ref))
