"""L2 原子執行者：憲法層（唯讀）＋任務層工廠＋戰前檢查＋結構化 Grill。

L2 只負責戰前檢查與專注執行。產出必須交給獨立的 L1 憲兵審查官簽核。
L3 只能注入任務層欄位；憲法層寫死在工廠，優先級高於所有後續指令。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from backend.company.raho.protocol import (
    ESCALATE_MARK,
    GRILL_MARK,
    MAX_SUPERIOR_ROUNDS,
    GrillIssue,
)

CONSTITUTION_MARKER = "[憲法層 - 唯讀區塊]"
TASK_LAYER_MARKER = "[任務層 - 由 L3 動態注入的內容]"

BLOCKER_INPUT = "資料缺失"
BLOCKER_TOOL = "工具不足"
BLOCKER_CRITERIA = "標準模糊"
BLOCKER_CAPACITY = "容量矛盾"
BLOCKER_CONSTRAINT = "約束衝突"
BLOCKER_TYPES = (
    BLOCKER_INPUT,
    BLOCKER_TOOL,
    BLOCKER_CRITERIA,
    BLOCKER_CAPACITY,
    BLOCKER_CONSTRAINT,
)

GRILL_TARGET_L3 = "L3_Commander"
GRILL_TARGET_L4 = "L4_Planner"
GRILL_TARGET_L5 = "L5_User"

DEFAULT_MAX_ITERATIONS = 2
DEFAULT_TOKEN_BUDGET = 2000
MIN_RETRY_ITERATIONS = 2
MIN_TOKEN_BUDGET = 400

_EMPTY_REFS = frozenset(
    {"", "null", "none", "nil", "undefined", "n/a", "na", "tbd", "todo", "-", "—"}
)
_SUBJECTIVE_ONLY = re.compile(
    r"^(盡量完美|盡量做好|盡力|高品質|更好|優化一下|盡可能好|完美|"
    r"as good as possible|high quality|best effort)$",
    re.IGNORECASE,
)
_MEASURABLE = re.compile(
    r"(\d+|json|csv|key|鍵|欄|列|行|字|char|token|包含|不得|必須|"
    r"schema|list\[|dict\[|通過|失敗|空值|來源|引用)",
    re.IGNORECASE,
)
_LARGE_INPUT = re.compile(
    r"(\d{2,}\s*頁|100\s*頁|長文|全書|完整報告|完整論文|完整手冊)",
    re.IGNORECASE,
)
_TINY_OUTPUT = re.compile(
    r"(max\s*50|最多\s*50|50\s*字|≤\s*50|<=\s*50|plain text \(max 50)",
    re.IGNORECASE,
)
_GRILL_JSON = re.compile(
    r"\{[^{}]*\"type\"\s*:\s*\"(?:GRILL|ESCALATE)\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)
_FAILED_JSON = re.compile(
    r"\{[^{}]*\"status\"\s*:\s*\"FAILED\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)


CONSTITUTION_LAYER = f"""# ==========================================
# {CONSTITUTION_MARKER} 此區塊優先級高於所有後續指令
# ==========================================

## 核心身份
你是一個「原子任務執行者」。你的智商極高，但視野極窄。你**沒有**個人意志、情感或好奇心。
你的唯一存在意義，就是完成下方任務層 `TASK_DESCRIPTION` 中定義的單一原子任務。

## 最高行動綱領（Pre-Execution Protocol）
在調用任何工具、輸出任何內容之前，**你必須強制執行「戰前檢查清單（Pre-flight Checklist）」**。
若檢查清單中任一項未通過，**禁止**開始執行任務，必須立即發起 {GRILL_MARK} 質詢。

### 戰前檢查清單（必答 5 問）
1. **輸入完整性（Input Integrity）**：任務層 `INPUT_REF` 指向的記憶體位置是否包含有效數據？若數據缺失或格式不符，判定為「{BLOCKER_INPUT}」。
2. **工具可用性（Tool Availability）**：我的工具白名單 `ALLOWED_TOOLS` 是否足以達成目標？若缺乏必要工具，判定為「{BLOCKER_TOOL}」。
3. **成功標準明確性（Success Clarity）**：`SUCCESS_CRITERIA` 是否包含「可驗證的客觀條件」（例如：包含特定關鍵字、長度範圍、JSON 鍵值對）？若僅有「盡量完美」等主觀描述，判定為「{BLOCKER_CRITERIA}」。
4. **邏輯一致性（Logic Consistency）**：任務目標與 `OUTPUT_SCHEMA` 是否有矛盾？（例如：要求摘要 100 頁 PDF，但輸出 Schema 只允許 50 字，判定為「{BLOCKER_CAPACITY}」）。
5. **約束合理性（Constraint Feasibility）**：`MAX_ITERATIONS` 與 `TOKEN_BUDGET` 是否足以應對突發狀況？（例如：若第一次執行失敗，剩餘迭代次數是否足以重試？）。

---

## {GRILL_MARK} 質詢協議（向上級發聲）
若上述檢查未通過，你**不得**試圖自行腦補修正。你必須輸出以下格式的 {GRILL_MARK} 訊息，並**立即暫停**所有後續動作，直至上級（L3 指揮官）回覆：

```json
{{
  "type": "GRILL",
  "target": "{GRILL_TARGET_L3}",
  "blocker_type": "{BLOCKER_INPUT}" | "{BLOCKER_TOOL}" | "{BLOCKER_CRITERIA}" | "{BLOCKER_CAPACITY}" | "{BLOCKER_CONSTRAINT}",
  "details": "具體描述哪裡有坑，為什麼過不去。",
  "suggested_fix": "提供一個你認為可行的具體修改建議（例如：將 INPUT_REF 改為 X，或放寬字數限制至 200 字）。"
}}
```

### 等待上級回覆期間
若上級在 {MAX_SUPERIOR_ROUNDS} 輪對話內提供修正指令，你必須重新執行「戰前檢查清單」，通過後方可執行。

若上級超時未回覆，或回覆依然無法通過檢查，你必須自動將此 {GRILL_MARK} 升級為 {ESCALATE_MARK} 並提交至 L4（元規劃官）或 L5（用戶）。

## 執行紀律（Execution Discipline）
當且僅當「戰前檢查清單」完全通過時，你才進入執行階段。執行時必須遵守：

1. **一次一動**：嚴格按照邏輯順序調用工具，不得跳步。
2. **沉默運作**：除最終產出外，禁止輸出任何解釋、廢話或 Markdown 格式修飾（除非 Output Schema 要求）。
3. **失敗收斂**：若執行過程中報錯，最多重試任務層 `MAX_ITERATIONS` 次。若仍失敗，輸出 `{{"status": "FAILED", "partial_output": "..."}}` 並終止任務，不得幻想成功。

## 最終輸出強制格式
最終必須嚴格遵守任務層 `OUTPUT_SCHEMA` 的定義。若輸出不符合該 Schema，視為任務失敗。
"""


@dataclass
class AtomicTaskSpec:
    """L3 注入的任務層欄位。憲法層不可由此覆寫。"""

    task_description: str = ""
    input_ref: Any = None
    allowed_tools: list[str] = field(default_factory=list)
    success_criteria: str = ""
    output_schema: str = ""
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    token_budget: int = DEFAULT_TOKEN_BUDGET
    instance_id: str = ""
    name: str = ""
    template_id: str = "generic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GrillMessage:
    """L2 → L3 結構化質詢（可程式處理，不必每次再叫 LLM）。"""

    type: str = "GRILL"
    target: str = GRILL_TARGET_L3
    blocker_type: str = BLOCKER_INPUT
    details: str = ""
    suggested_fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "target": self.target,
            "blocker_type": self.blocker_type,
            "details": self.details,
            "suggested_fix": self.suggested_fix,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_issue(self) -> GrillIssue:
        kind = {
            BLOCKER_INPUT: "gap",
            BLOCKER_TOOL: "tool",
            BLOCKER_CRITERIA: "spec",
            BLOCKER_CAPACITY: "contradiction",
            BLOCKER_CONSTRAINT: "constraint",
        }.get(self.blocker_type, "gap")
        field = {
            BLOCKER_INPUT: "input_ref",
            BLOCKER_TOOL: "allowed_tools",
            BLOCKER_CRITERIA: "success_criteria",
            BLOCKER_CAPACITY: "output_schema",
            BLOCKER_CONSTRAINT: "budget",
        }.get(self.blocker_type, "")
        return GrillIssue(
            message=self.details or self.blocker_type,
            kind=kind,
            field=field,
            blocker_type=self.blocker_type,
            suggested_fix=self.suggested_fix,
            target=self.target,
        )

    def render(self) -> str:
        mark = ESCALATE_MARK if self.type == "ESCALATE" else GRILL_MARK
        return f"{mark}\n{self.to_json()}"


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(x).strip() for x in value if str(x).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _as_tools(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = [p.strip() for p in re.split(r"[,|、\s]+", value) if p.strip()]
        return raw
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    return []


def _is_empty_ref(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, tuple)):
        return not any(not _is_empty_ref(x) for x in value)
    text = str(value).strip()
    return text.lower() in _EMPTY_REFS


def spec_from_mapping(task_spec: dict[str, Any] | AtomicTaskSpec) -> AtomicTaskSpec:
    if isinstance(task_spec, AtomicTaskSpec):
        return task_spec
    raw = task_spec or {}
    desc = (
        raw.get("task_description")
        or raw.get("system_prompt")
        or raw.get("description")
        or raw.get("title")
        or ""
    )
    try:
        iters = int(raw.get("max_iterations") if raw.get("max_iterations") is not None else DEFAULT_MAX_ITERATIONS)
    except (TypeError, ValueError):
        iters = DEFAULT_MAX_ITERATIONS
    try:
        tokens = int(raw.get("token_budget") if raw.get("token_budget") is not None else DEFAULT_TOKEN_BUDGET)
    except (TypeError, ValueError):
        tokens = DEFAULT_TOKEN_BUDGET
    return AtomicTaskSpec(
        task_description=_as_text(desc),
        input_ref=raw.get("input_ref"),
        allowed_tools=_as_tools(raw.get("allowed_tools")),
        success_criteria=_as_text(raw.get("success_criteria") or raw.get("kpi")),
        output_schema=_as_text(raw.get("output_schema") or raw.get("output_spec")),
        max_iterations=max(1, iters),
        token_budget=max(1, tokens),
        instance_id=_as_text(raw.get("instance_id") or raw.get("template_id")),
        name=_as_text(raw.get("name")),
        template_id=_as_text(raw.get("template_id") or "generic") or "generic",
    )


def has_constitution(prompt: str) -> bool:
    return CONSTITUTION_MARKER in (prompt or "")


def render_task_layer(spec: AtomicTaskSpec) -> str:
    tools = spec.allowed_tools or []
    tools_text = json.dumps(tools, ensure_ascii=False) if tools else "[]"
    input_text = _as_text(spec.input_ref) or "null"
    return f"""# ==========================================
# {TASK_LAYER_MARKER}
# ==========================================

## 當前原子任務（源自 L3 作戰手冊）
{spec.task_description or "（未提供 TASK_DESCRIPTION）"}

## 輸入來源（Input Reference）
{input_text}

## 工具權限白名單（Tool Whitelist）
{tools_text}

## 成功驗證標準（Success Criteria）
{spec.success_criteria or "（未提供 SUCCESS_CRITERIA）"}

## 輸出格式定義（Output Schema）
{spec.output_schema or "（未提供 OUTPUT_SCHEMA）"}

## 資源預算限制（Resource Budget）
最大迭代次數：{spec.max_iterations}
Token 預算帽：{spec.token_budget}
"""


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


__all__ = [
    "BLOCKER_CAPACITY",
    "BLOCKER_CONSTRAINT",
    "BLOCKER_CRITERIA",
    "BLOCKER_INPUT",
    "BLOCKER_TOOL",
    "BLOCKER_TYPES",
    "CONSTITUTION_LAYER",
    "CONSTITUTION_MARKER",
    "DEFAULT_MAX_ITERATIONS",
    "DEFAULT_TOKEN_BUDGET",
    "TASK_LAYER_MARKER",
    "AtomicExecutorFactory",
    "AtomicTaskSpec",
    "GrillMessage",
    "escalate_grill",
    "has_constitution",
    "parse_failed_output",
    "parse_structured_protocol",
    "preflight_issues",
    "render_task_layer",
    "run_preflight",
    "spec_from_mapping",
]
