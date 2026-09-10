"""L1 憲兵審查官：憲法層（唯讀）＋四維度驗收＋雙向 Grill＋簽核閘門。

L1 不隸屬 L3，直接對最終交付品質負責。
禁止同理心、禁止跨級代勞；只有 VERDICT: APPROVED 的數據可寫入共享記憶體。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.atomic_executor import (
    AtomicTaskSpec,
    spec_from_mapping,
)
from backend.company.raho.protocol import (
    ESCALATE_MARK,
    GRILL_MARK,
    GrillIssue,
)

INSPECTOR_ID = "L1-CONSTITUTIONAL"
INSPECTOR_MARKER = "[憲法層 - 唯讀區塊] 最高獨立審查權"
INSPECTION_LAYER_MARKER = "[驗收層 - 由 L3 規格與 L2 產出動態注入]"

VERDICT_APPROVED = "APPROVED"
VERDICT_REWORK = "REWORK"
VERDICT_ESCALATE = "ESCALATE"
VERDICTS = (VERDICT_APPROVED, VERDICT_REWORK, VERDICT_ESCALATE)

TEST_SCHEMA = "結構合規性"
TEST_SEMANTIC = "語義完整性"
TEST_FACTUAL = "事實一致性"
TEST_EDGE = "極限邊界檢驗"
TEST_KEYS = (
    "schema_validation",
    "semantic_integrity",
    "factual_consistency",
    "edge_case",
)
TEST_LABELS = {
    "schema_validation": TEST_SCHEMA,
    "semantic_integrity": TEST_SEMANTIC,
    "factual_consistency": TEST_FACTUAL,
    "edge_case": TEST_EDGE,
}

GRILL_TARGET_L2 = "L2_Executor"
GRILL_TARGET_L3 = "L3_Commander"
GRILL_TARGET_L4 = "L4_Planner"
GRILL_TARGET_L5 = "L5_User"

PASS = "PASS"
FAIL = "FAIL"

_JSON_SCHEMA = re.compile(
    r"(json|list\s*\[|dict\s*\[|object|array|\{\s*[\"'])",
    re.IGNORECASE,
)
_KEY_IN_SCHEMA = re.compile(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*:")
_REQUIRED_FIELD = re.compile(
    r"(必填|必須包含|需包含|required)\s*[「『\"']?([A-Za-z_\u4e00-\u9fff][\w\u4e00-\u9fff]*)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w./:])(\d+(?:\.\d+)?)(?![\w./:%])")
_TRACE = re.compile(
    r"(traceback|exception|error:|崩潰|報錯崩潰|TypeError|ValueError|KeyError|NullPointer)",
    re.IGNORECASE,
)
_MAX_LEN = re.compile(
    r"(?:max\s*(\d+)\s*char|最多\s*(\d+)\s*字|≤\s*(\d+)\s*字|<=\s*(\d+)\s*字|"
    r"plain text \(max\s*(\d+))",
    re.IGNORECASE,
)
_PERIOD_HINT = re.compile(
    r"(上個月|上月|本月|本週|上週|去年|前年|last\s+month|this\s+month)",
    re.IGNORECASE,
)
_GROWTH_CLAIM = re.compile(
    r"(成長|增長|下降|下滑|同比|環比|\d+\s*%|percent)",
    re.IGNORECASE,
)
_VERDICT_JSON = re.compile(
    r"\{[^{}]*\"verdict\"\s*:\s*\"(?:APPROVED|REWORK|ESCALATE)\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)
_GRILL_JSON = re.compile(
    r"\{[^{}]*\"type\"\s*:\s*\"(?:GRILL|ESCALATE)\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)


CONSTITUTION_LAYER = f"""# ==========================================
# {INSPECTOR_MARKER}
# ==========================================

## 角色定位
你是 L1 憲兵審查官。你不隸屬於 L3 指揮官，而是直接向「最終交付品質」負責。你的天性極度悲觀、挑剔且不近人情。對你來說，沒有「還不錯」，只有「合格」與「不合格」。你必須假設 L2 原子執行者是一個「經常說謊的實習生」，而 L3 指揮官是一個「偶爾粗心大意的參謀」。

## 核心鐵律（不可違反）
1. **禁止同理心**：無論 L2 耗費多少心力，只要產出不符合規格，一律打回。
2. **禁止跨級代勞**：你絕對**不**能自己動手修改 L2 的產出。你的天職是「指出錯誤」並「要求重做」，而不是「幫忙做完」。
3. **雙向質詢權（Bidirectional Grill Right）**：
   - 若問題出在**執行端（L2）**（如：格式跑掉、數據算錯），你向 L2 發起 {GRILL_MARK} 要求修正。
   - 若問題出在**規劃端（L3）**（如：給的輸入數據本身就是錯的、成功標準不合理），你向 L3 發起 {GRILL_MARK} 要求修正指令。
4. **簽核即責任（Sign-off Liability）**：只有當你輸出 `VERDICT: {VERDICT_APPROVED}` 時，該節點的數據才能被寫入共享記憶體供下游使用。未經 L1 蓋章的數據，下游 L2 不得引用。
5. **態勢感知（Environment Bias）**：審查時必須參考 L0 態勢雷達。結構合規與事實一致性失敗一律不得放行。僅當系統負載過高、且失敗僅為極限邊界、產出已達可接受下限時，才可「降級通過（CONDITIONAL_PASS）」以節省資源，禁止為 80 分反覆重做。

---

## 驗收程序（四維度壓力測試）
在收到 L2 的產出後，你必須**按順序**執行以下 4 項測試。若任一測試失敗，立即中斷後續測試，進入質詢流程。

### 測試 1：{TEST_SCHEMA}（Schema Validation）
- **檢查點**：產出是否嚴格符合 L3 定義的 `OUTPUT_SCHEMA`？（例如：型別是否正確、必填欄位是否存在、陣列長度是否合理）。
- **失敗標準**：缺少欄位、型別錯誤（如字串變數字）、JSON 格式解析失敗。

### 測試 2：{TEST_SEMANTIC}（Semantic Integrity）
- **檢查點**：產出的「語意內容」是否真正回應了 L3 的 `TASK_DESCRIPTION`？（例如：要求「分析趨勢」，結果只給原始數據，視為未完成）。
- **失敗標準**：答非所問、只複製貼上未經處理、內容空洞無具體論述。

### 測試 3：{TEST_FACTUAL}（Factual Consistency） - *這是 L1 的殺手鐧*
- **檢查點**：將 L2 的產出與其 `INPUT_REF` 指向的來源數據進行**交叉比對**。
- **操作方式**：調用比對工具（如 `semantic_similarity` 或 `exact_match`），檢查是否存在「幻覺（Hallucination）」或「與原始數據矛盾的表述」。
- **失敗標準**：產出中的關鍵數據（數字、日期、名稱）無法在輸入來源中找到對應依據。

### 測試 4：{TEST_EDGE}（Edge Case Robustness）
- **檢查點**：檢查 L2 是否處理了常見的極端情況。
- **失敗標準**：例如輸入為空值時是否報錯崩潰；數值超出預期區間時是否給出警告；文字超出字數限制時是否截斷或摘要。

---

## {GRILL_MARK} 質詢協議（針對 L2 執行者與 L3 指揮官）

### 針對 L2（要求重做）
當測試 1 或 2 失敗時，你向 L2 發起 {GRILL_MARK}，要求其利用剩餘的迭代次數修正產出。
```json
{{
  "type": "GRILL",
  "target": "{GRILL_TARGET_L2}",
  "failed_test": "{TEST_SCHEMA}",
  "details": "你的產出缺少 'total_price' 欄位，且 'items' 陣列為空。",
  "required_fix": "請補齊所有必填欄位，並確保 items 至少包含 1 筆資料後重新提交。"
}}
```

### 針對 L3（質疑規劃）
當測試 3 或 4 失敗，且明顯非 L2 能力所及（例如輸入數據本身就是錯的，或要求 10 秒內爬完 1000 個網站），你向 L3 發起 {GRILL_MARK}。
```json
{{
  "type": "GRILL",
  "target": "{GRILL_TARGET_L3}",
  "failed_test": "{TEST_FACTUAL}",
  "details": "L2 產出的『競品價格 99 美元』與你提供給它的輸入數據（競品價格 149 美元）不符。若來源本身缺欄，請修正 INPUT_REF。",
  "suggested_fix": "請修正 INPUT_REF 指向最新的數據源，並通知 L2 重新執行。"
}}
```

## 最終裁決（Final Verdict）
- **通過（{VERDICT_APPROVED}）**：所有測試通過。輸出帶有簽章的 JSON。
- **退回重做（{VERDICT_REWORK}）**：測試 1/2 失敗，由 L2 修正（計入迭代次數）。
- **向上呈報（{VERDICT_ESCALATE}）**：測試 3/4 失敗且指向 L3 指令缺陷，或 L2 修正次數已耗盡仍未達標。此時必須向上呈報至 L4 或 L5（用戶），請求裁定是否降低標準或調整任務目標。

## 最終輸出格式（簽核文件）
```json
{{
  "verdict": "{VERDICT_APPROVED}" | "{VERDICT_REWORK}" | "{VERDICT_ESCALATE}",
  "inspector_id": "{INSPECTOR_ID}",
  "test_results": {{
    "schema_validation": "PASS",
    "semantic_integrity": "PASS",
    "factual_consistency": "PASS",
    "edge_case": "PASS"
  }},
  "final_approved_data": "<若通過，此處存放 L2 的原始產出，並加上數位簽章>",
  "quality_score": 96.5
}}
```
未經 `VERDICT: {VERDICT_APPROVED}` 蓋章的數據，禁止寫入黑板，下游 L2 不得引用。
"""


class ReworkRequired(Exception):
    """L1 要求 L2 重做。"""

    def __init__(self, verdict: InspectorVerdict):
        super().__init__(verdict.details or "L1 退回重做")
        self.verdict = verdict


class EscalateRequired(Exception):
    """L1 向上呈報 L3／L4／L5。"""

    def __init__(self, verdict: InspectorVerdict):
        super().__init__(verdict.details or "L1 向上呈報")
        self.verdict = verdict


@dataclass
class InspectorGrill:
    """L1 雙向質詢：L2 重做 或 L3 改指令。"""

    type: str = "GRILL"
    target: str = GRILL_TARGET_L2
    failed_test: str = TEST_SCHEMA
    details: str = ""
    required_fix: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "type": self.type,
            "target": self.target,
            "failed_test": self.failed_test,
            "details": self.details,
        }
        if self.target == GRILL_TARGET_L2:
            payload["required_fix"] = self.required_fix or self.suggested_fix
        else:
            payload["suggested_fix"] = self.suggested_fix or self.required_fix
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_issue(self) -> GrillIssue:
        kind = {
            TEST_SCHEMA: "spec",
            TEST_SEMANTIC: "spec",
            TEST_FACTUAL: "contradiction",
            TEST_EDGE: "constraint",
        }.get(self.failed_test, "spec")
        field = {
            TEST_SCHEMA: "output_schema",
            TEST_SEMANTIC: "task_description",
            TEST_FACTUAL: "input_ref",
            TEST_EDGE: "edge_case",
        }.get(self.failed_test, "")
        blocker = {
            TEST_SCHEMA: "標準模糊" if "模糊" in self.details else "容量矛盾",
            TEST_SEMANTIC: "標準模糊",
            TEST_FACTUAL: "資料缺失",
            TEST_EDGE: "約束衝突",
        }.get(self.failed_test, "")
        return GrillIssue(
            message=self.details or self.failed_test,
            kind=kind,
            field=field,
            blocker_type=blocker,
            suggested_fix=self.suggested_fix or self.required_fix,
            target=self.target,
        )

    def render(self) -> str:
        mark = ESCALATE_MARK if self.type == "ESCALATE" else GRILL_MARK
        return f"{mark}\n{self.to_json()}"


@dataclass
class InspectorVerdict:
    verdict: str = VERDICT_REWORK
    inspector_id: str = INSPECTOR_ID
    test_results: dict[str, str] = field(default_factory=dict)
    final_approved_data: str = ""
    quality_score: float = 0.0
    details: str = ""
    grill: InspectorGrill | None = None
    signature: str = ""
    node_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "verdict": self.verdict,
            "inspector_id": self.inspector_id,
            "test_results": dict(self.test_results),
            "final_approved_data": self.final_approved_data,
            "quality_score": self.quality_score,
        }
        if self.details:
            payload["details"] = self.details
        if self.signature:
            payload["signature"] = self.signature
        if self.node_id:
            payload["node_id"] = self.node_id
        if self.grill is not None:
            payload["grill"] = self.grill.to_dict()
        return payload

    def approved(self) -> bool:
        return self.verdict == VERDICT_APPROVED


def l1_llm_enabled() -> bool:
    return os.getenv("EVOL_RAHO_L1_LLM", "false").lower() in {"1", "true", "yes", "on"}


def has_inspector_constitution(prompt: str) -> bool:
    return INSPECTOR_MARKER in (prompt or "")


def sign_payload(data: str, inspector_id: str = INSPECTOR_ID) -> str:
    digest = hashlib.sha256(f"{inspector_id}|{data}".encode()).hexdigest()
    return f"L1:{digest[:20]}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(x).strip() for x in value if str(x).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _extract_json(text: str) -> Any | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else None
    if blob is None:
        if raw.startswith(("{", "[")):
            blob = raw
        else:
            match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
            blob = match.group(1) if match else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _schema_keys(schema: str) -> list[str]:
    keys = _KEY_IN_SCHEMA.findall(schema or "")
    keys.extend(m.group(2) for m in _REQUIRED_FIELD.finditer(schema or ""))
    seen: list[str] = []
    for key in keys:
        if key not in seen:
            seen.append(key)
    return seen


def _looks_json_schema(schema: str) -> bool:
    return bool(_JSON_SCHEMA.search(schema or ""))


def _numbers(text: str) -> set[str]:
    return {m.group(1) for m in _NUMBER.finditer(text or "")}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()) if t}


def exact_match(left: str, right: str) -> float:
    """精確比對：完全一致為 1.0，否則 0.0。"""
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return 0.0
    return 1.0 if a == b else 0.0


def semantic_similarity(left: str, right: str) -> float:
    """無嵌入的交叉比對：詞彙 Jaccard 0.6 + 數字覆蓋 0.4。"""
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    jaccard = len(a & b) / len(a | b)
    claimed = _numbers(left)
    available = _numbers(right)
    if claimed:
        coverage = len(claimed & available) / len(claimed)
    else:
        coverage = 1.0
    return round(min(1.0, 0.6 * jaccard + 0.4 * coverage), 3)


def compare_facts(output: str, source: str) -> dict[str, float]:
    """測試 3 的比對工具包：exact_match + semantic_similarity。"""
    return {
        "exact_match": exact_match(output, source),
        "semantic_similarity": semantic_similarity(output, source),
    }


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


def _schema_result(spec: AtomicTaskSpec, output: str) -> tuple[str, str]:
    raw = (output or "").strip()
    if not raw:
        return FAIL, "產出為空，無法通過結構合規性。"
    if raw.upper().startswith('{"STATUS": "FAILED"') or '"status": "FAILED"' in raw:
        return FAIL, "L2 主動宣告 FAILED，結構視為不合格。"
    schema = spec.output_schema or ""
    if _looks_json_schema(schema):
        parsed = _extract_json(raw)
        if parsed is None:
            return FAIL, f"OUTPUT_SCHEMA「{schema}」要求結構化資料，但產出無法解析為 JSON。"
        if isinstance(parsed, list) and "list" in schema.lower() and not parsed:
            return FAIL, "產出陣列為空，未滿足最小資料列。"
        required = _schema_keys(schema)
        if required and isinstance(parsed, dict):
            missing = [k for k in required if k not in parsed]
            if missing:
                return FAIL, f"產出缺少必填欄位：{', '.join(missing)}。"
        if required and isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            missing = [k for k in required if k not in parsed[0]]
            if missing:
                return FAIL, f"陣列列缺少必填欄位：{', '.join(missing)}。"
    return PASS, ""


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
    tests = data.get("test_results") if isinstance(data.get("test_results"), dict) else {}
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
    layer = blob.get("task_layer") if isinstance(blob.get("task_layer"), dict) else {}
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


class InspectorGate:
    """L1 審查閘門：組裝憲法層 Prompt、規則驗收、可選 LLM、簽核路由。"""

    CONSTITUTION_LAYER = CONSTITUTION_LAYER
    INSPECTOR_MARKER = INSPECTOR_MARKER

    def __init__(self, llm: Callable[..., str] | None = None):
        self.system_prompt = CONSTITUTION_LAYER
        self.llm = llm

    @classmethod
    def spawn(cls, task_spec: dict[str, Any] | AtomicTaskSpec, l2_output: str, *, source_preview: str = "") -> str:
        """輸入 L3 規格 + L2 產出，輸出完整 L1 System Prompt（憲法層唯讀）。"""
        return compose_inspector_prompt(task_spec, l2_output, source_preview=source_preview)

    def compose(self, task_spec: dict[str, Any] | AtomicTaskSpec, l2_output: str, *, source_preview: str = "") -> str:
        return self.spawn(task_spec, l2_output, source_preview=source_preview)

    def inspect(
        self,
        task_spec: dict[str, Any] | AtomicTaskSpec,
        l2_output: str,
        *,
        source_data: Any = None,
        rework_rounds: int = 0,
        max_rework: int = 2,
        node_id: str = "",
        title: str = "",
        use_llm: bool | None = None,
    ) -> InspectorVerdict:
        """規則優先；僅在環境開啟且規則無法決時才呼叫 LLM。"""
        verdict = run_inspection(
            task_spec,
            l2_output,
            source_data=source_data,
            rework_rounds=rework_rounds,
            max_rework=max_rework,
            node_id=node_id,
        )
        want_llm = l1_llm_enabled() if use_llm is None else use_llm
        if want_llm and verdict.verdict == VERDICT_APPROVED:
            llm_verdict = self._llm_inspect(task_spec, l2_output, source_data)
            if llm_verdict is not None and llm_verdict.verdict != VERDICT_APPROVED:
                verdict = llm_verdict
        try:
            from backend.company.raho.l0 import apply_radar_bias

            verdict = apply_radar_bias(verdict)
        except Exception:
            pass
        if verdict.verdict == VERDICT_APPROVED:
            write_signed_memory(node_id or verdict.node_id, verdict, title=title)
        return verdict

    def inspect_or_raise(self, *args: Any, **kwargs: Any) -> InspectorVerdict:
        verdict = self.inspect(*args, **kwargs)
        if verdict.verdict == VERDICT_REWORK:
            raise ReworkRequired(verdict)
        if verdict.verdict == VERDICT_ESCALATE:
            raise EscalateRequired(verdict)
        return verdict

    def _llm_inspect(
        self,
        task_spec: dict[str, Any] | AtomicTaskSpec,
        l2_output: str,
        source_data: Any,
    ) -> InspectorVerdict | None:
        prompt = self.compose(task_spec, l2_output, source_preview=_as_text(source_data)[:2000])
        started = time.monotonic()
        try:
            if self.llm is not None:
                raw = self.llm(prompt)
            else:
                from backend.core.llm import call_llm

                raw = call_llm(prompt, system=self.system_prompt)
        except Exception:
            return None
        try:
            from backend.company.raho.protocol import RahoLayer, layer_label
            from backend.company.seat_io import record_seat_io

            spec = task_spec if isinstance(task_spec, dict) else getattr(task_spec, "__dict__", {})
            record_seat_io({
                "item_id": str(spec.get("node_id") or spec.get("item_id") or ""),
                "title": str(spec.get("title") or "")[:80],
                "role": "constitutional_inspector",
                "role_label": "L1 憲兵（獨立審查）",
                "layer": int(RahoLayer.L1_INSPECTOR),
                "layer_label": layer_label(int(RahoLayer.L1_INSPECTOR)),
                "lane": "inspect",
                "kind": "inspect",
                "system": self.system_prompt,
                "prompt": prompt,
                "response": raw,
                "duration_ms": round((time.monotonic() - started) * 1000.0, 1),
                "context_sources": [
                    {"kind": "constitution", "label": "憲法層唯讀區塊（L3 規格＋L2 產出動態注入）", "text": self.system_prompt},
                    {"kind": "deliverable", "label": "被審查的 L2 產出", "text": _as_text(l2_output)[:4000]},
                ],
            })
        except Exception:
            pass
        return parse_verdict(raw)


__all__ = [
    "CONSTITUTION_LAYER",
    "ESCALATE_MARK",
    "FAIL",
    "GRILL_TARGET_L2",
    "GRILL_TARGET_L3",
    "INSPECTION_LAYER_MARKER",
    "INSPECTOR_ID",
    "INSPECTOR_MARKER",
    "PASS",
    "TEST_EDGE",
    "TEST_FACTUAL",
    "TEST_SCHEMA",
    "TEST_SEMANTIC",
    "VERDICT_APPROVED",
    "VERDICT_ESCALATE",
    "VERDICT_REWORK",
    "EscalateRequired",
    "InspectorGate",
    "InspectorGrill",
    "InspectorVerdict",
    "ReworkRequired",
    "compare_facts",
    "compose_inspector_prompt",
    "exact_match",
    "has_inspector_constitution",
    "l1_llm_enabled",
    "parse_inspector_grill",
    "parse_verdict",
    "read_signed_memory",
    "resolve_input_ref",
    "run_inspection",
    "semantic_similarity",
    "sign_payload",
    "source_for_artifacts",
    "write_signed_memory",
]
