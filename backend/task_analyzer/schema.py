"""任務分析器 v0.1 JSON Schema。

涵蓋具名實體與接口 A／B／C。每個物件 additionalProperties 為 false。
具名實體、接口與會獨立演進的組件必帶 schema_version。
版本政策是只增不刪：可加選填欄位與枚舉值，不可刪除或改名。

金額區間、選項、網路與敏感度是值物件，沒有自己的版號。
驗證在 validate.py。這裡不執行規則、狀態機、配置或權限。
"""

from __future__ import annotations

from typing import Any

from backend.task_analyzer.enums import ENUMS

SCHEMA_VERSION = "v0.1"
CHANGE_POLICY = "additive-only"
_SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
_BUNDLE_ID = "https://linkin.local/schemas/task-analyzer/v0.1/bundle.schema.json"


def _enum(name: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(ENUMS[name])}


def _str(*, min_length: int = 1) -> dict[str, Any]:
    return {"type": "string", "minLength": min_length}


def _ref(name: str) -> dict[str, str]:
    return {"$ref": f"#/$defs/{name}"}


def _arr(items: dict[str, Any], *, min_items: int = 0) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if min_items:
        schema["minItems"] = min_items
    return schema


def _obj(
    title: str,
    properties: dict[str, Any],
    required: list[str],
    description: str,
) -> dict[str, Any]:
    return {
        "title": title,
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required,
    }


def _entity(
    title: str,
    properties: dict[str, Any],
    required: list[str],
    description: str,
) -> dict[str, Any]:
    props = {"schema_version": {"const": SCHEMA_VERSION}, **properties}
    return _obj(title, props, ["schema_version", *required], description)


def _nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"anyOf": [schema, {"type": "null"}]}


def _build() -> dict[str, dict[str, Any]]:
    text = _str()
    blank = _str(min_length=0)
    band = _obj(
        "MoneyBand",
        {"low": {"type": "number", "minimum": 0}, "high": {"type": "number", "minimum": 0}},
        ["low", "high"],
        "金額區間，含下緣與上緣。",
    )
    option = _obj(
        "QuestionOption",
        {"id": text, "label": text},
        ["id", "label"],
        "反問的一個選項。",
    )
    network = _obj(
        "Network",
        {"zone": blank, "egress": blank},
        ["zone", "egress"],
        "網路位置與對外連線。空字串表示尚未填寫。",
    )
    sensitivity = _obj(
        "Sensitivity",
        {
            "score": {"type": "number", "minimum": 0},
            "threshold": {"type": "number", "minimum": 0},
            "drivers": _arr(text),
        },
        ["score", "threshold", "drivers"],
        "預算敏感度。score 為區間寬度比，threshold 為當時採用的門檻。",
    )
    criterion = _entity(
        "Criterion",
        {
            "id": text,
            "metric": _enum("criterion.metric"),
            "hard_or_soft": _enum("hard_or_soft"),
            "target": text,
            "unit": blank,
        },
        ["id", "metric", "hard_or_soft", "target", "unit"],
        "一條可衡量的成功標準。",
    )
    goal = _entity(
        "TaskGoal",
        {"id": text, "statement": text, "criteria": _arr(_ref("Criterion"))},
        ["id", "statement", "criteria"],
        "任務目標，可帶零到多條衡量標準。",
    )
    environment = _entity(
        "EnvironmentSpec",
        {
            "deployment": _enum("deployment"),
            "tenant_id": text,
            "region": blank,
            "network": _ref("Network"),
            "compliance_regimes": _arr(text),
        },
        ["deployment", "tenant_id", "region", "network", "compliance_regimes"],
        "部署、網路、合規與租戶。",
    )
    resource = _entity(
        "ResourceSpec",
        {
            "id": text,
            "kind": _enum("resource.kind"),
            "name": text,
            "disposition": _enum("gap.disposition"),
            "endpoint": blank,
            "tenant_id": text,
        },
        ["id", "kind", "name", "disposition", "endpoint", "tenant_id"],
        "已盤點的 Server、API 或其他資源。",
    )
    hardware = _entity(
        "HardwareSpec",
        {
            "id": text,
            "deployment": _enum("deployment"),
            "kind": _enum("hardware.kind"),
            "quantity": {"type": "integer", "minimum": 0},
            "notes": blank,
        },
        ["id", "deployment", "kind", "quantity", "notes"],
        "硬體或算力位置。",
    )
    question = _entity(
        "Question",
        {
            "id": text,
            "category": _enum("question.category"),
            "prompt": text,
            "options": _arr(_ref("QuestionOption"), min_items=1),
            "recommended_default": text,
            "if_unanswered": text,
            "gap_id": text,
        },
        ["id", "category", "prompt", "options", "recommended_default", "if_unanswered", "gap_id"],
        "一題阻塞反問：選項、推薦預設、不答後果。",
    )
    red_line = _entity(
        "RedLine",
        {
            "id": text,
            "category": _enum("redline.category"),
            "hard_or_soft": _enum("hard_or_soft"),
            "status": _enum("rule.status"),
            "evidence": text,
        },
        ["id", "category", "hard_or_soft", "status", "evidence"],
        "一條底線的結構。status 為 pass、fail 或 unknown。",
    )
    budget = _entity(
        "BudgetEstimate",
        {
            "currency": text,
            "one_time": _ref("MoneyBand"),
            "runtime": _ref("MoneyBand"),
            "labor": _ref("MoneyBand"),
            "risk_maintenance": _ref("MoneyBand"),
            "assumptions": _arr(text, min_items=1),
            "sensitivity": _ref("Sensitivity"),
        },
        [
            "currency",
            "one_time",
            "runtime",
            "labor",
            "risk_maintenance",
            "assumptions",
            "sensitivity",
        ],
        "一次性、運行、人力、風險維護四段區間，附假設與敏感度。",
    )
    summary_props = {
        "task_type": _enum("task_type"),
        "priority": _enum("priority"),
        "title": text,
        "statement": text,
        "goals": _arr(_ref("TaskGoal")),
        "boundaries": _arr(text),
        "environment": _ref("EnvironmentSpec"),
        "resources": _arr(_ref("ResourceSpec")),
        "hardware": _arr(_ref("HardwareSpec")),
        "persistence": _enum("persistence"),
    }
    summary_required = list(summary_props)
    summary = _entity("TaskSummary", summary_props, summary_required, "接口 A 的任務摘要。")
    gap = _entity(
        "Gap",
        {
            "id": text,
            "disposition": _enum("gap.disposition"),
            "severity": _enum("gap.severity"),
            "summary": text,
            "blocking": {"type": "boolean"},
        },
        ["id", "disposition", "severity", "summary", "blocking"],
        "一條缺口：已有、需適配、需採購或缺失。",
    )
    request = _entity(
        "TaskRequest",
        {
            "tenant_id": text,
            "request_id": text,
            "input_channel": _enum("input_channel"),
            "priority": _enum("priority"),
            "task_type": _enum("task_type"),
            "title": text,
            "statement": text,
            "goals": summary_props["goals"],
            "boundaries": summary_props["boundaries"],
            "environment": summary_props["environment"],
            "resources": summary_props["resources"],
            "hardware": summary_props["hardware"],
            "persistence": _enum("persistence"),
        },
        [
            "tenant_id",
            "request_id",
            "input_channel",
            "priority",
            "task_type",
            "title",
            "statement",
            "goals",
            "boundaries",
            "environment",
            "resources",
            "hardware",
            "persistence",
        ],
        "進入分析器的請求。",
    )
    interface_a = _entity(
        "InterfaceA",
        {
            "interface": {"const": "A"},
            "tenant_id": text,
            "request_id": text,
            "task_summary": _ref("TaskSummary"),
            "gaps": _arr(_ref("Gap")),
        },
        ["interface", "tenant_id", "request_id", "task_summary", "gaps"],
        "接口 A：任務摘要與缺口清單。不含反問、底線與預算。",
    )
    constraints = _entity(
        "ConstraintPack",
        {
            "summary": _ref("TaskSummary"),
            "boundaries": _arr(text),
            "priority": _enum("priority"),
            "persistence": _enum("persistence"),
            "accepted_defaults": _arr(text),
        },
        ["summary", "boundaries", "priority", "persistence", "accepted_defaults"],
        "接口 B 的約束包。",
    )
    interface_b = _entity(
        "InterfaceB",
        {
            "interface": {"const": "B"},
            "tenant_id": text,
            "request_id": text,
            "constraints": _ref("ConstraintPack"),
            "baseline_passed": {"type": "boolean"},
            "redlines": _arr(_ref("RedLine")),
        },
        ["interface", "tenant_id", "request_id", "constraints", "baseline_passed", "redlines"],
        "接口 B：約束包與底線結果。不含預算。",
    )
    condition = _entity(
        "Condition",
        {"id": text, "summary": text, "owner": text},
        ["id", "summary", "owner"],
        "有條件放行時的一條補齊條件與責任人。",
    )
    handoff = _entity(
        "Handoff",
        {
            "execution_path": _enum("execution_path"),
            "company_template": blank,
            "budget_locked": {"type": "boolean"},
            "query": text,
        },
        ["execution_path", "company_template", "budget_locked", "query"],
        "交給既有編排時要帶的欄位。本模組不執行交接。",
    )
    execution_path_record = _obj(
        "ExecutionPathRecord",
        {
            "chosen": _enum("execution_path"),
            "source": _enum("decision_source"),
            "suggested": _enum("execution_path"),
            "reason": text,
        },
        ["chosen", "source", "suggested", "reason"],
        "已採用的路徑、決策來源、系統建議與理由。報告只記錄，不在這裡重選。",
    )
    feasibility_input = _entity(
        "FeasibilityInput",
        {"decision_source": _enum("decision_source")},
        ["decision_source"],
        "子圖三（可行性）的輸入。decision_source 說明路徑如何定案，本輸入不重新選路。",
    )
    report = _entity(
        "TaskAnalysisReport",
        {
            "tenant_id": text,
            "request_id": text,
            "feasibility": _enum("feasibility"),
            "next_action": _enum("next_action"),
            "priority": _enum("priority"),
            "interface_a": _ref("InterfaceA"),
            "interface_b": _nullable(_ref("InterfaceB")),
            "budget": _nullable(_ref("BudgetEstimate")),
            "conditions": _arr(_ref("Condition")),
            "handoff": _nullable(_ref("Handoff")),
            "execution_path": _ref("ExecutionPathRecord"),
        },
        [
            "tenant_id",
            "request_id",
            "feasibility",
            "next_action",
            "priority",
            "interface_a",
            "interface_b",
            "budget",
            "conditions",
            "handoff",
        ],
        "任務分析報告。可同時嵌接口 A、B 與預算，因而一份 JSON 能表達 A／B／C。"
        "execution_path 為選填，舊報告不必補上。",
    )
    interface_c = _entity(
        "InterfaceC",
        {"interface": {"const": "C"}, "report": _ref("TaskAnalysisReport")},
        ["interface", "report"],
        "接口 C：包住任務分析報告。",
    )
    return {
        "MoneyBand": band,
        "QuestionOption": option,
        "Network": network,
        "Sensitivity": sensitivity,
        "Criterion": criterion,
        "TaskGoal": goal,
        "EnvironmentSpec": environment,
        "ResourceSpec": resource,
        "HardwareSpec": hardware,
        "Question": question,
        "RedLine": red_line,
        "BudgetEstimate": budget,
        "TaskSummary": summary,
        "Gap": gap,
        "TaskRequest": request,
        "InterfaceA": interface_a,
        "ConstraintPack": constraints,
        "InterfaceB": interface_b,
        "Condition": condition,
        "Handoff": handoff,
        "ExecutionPathRecord": execution_path_record,
        "FeasibilityInput": feasibility_input,
        "TaskAnalysisReport": report,
        "InterfaceC": interface_c,
    }


SCHEMAS: dict[str, dict[str, Any]] = _build()


def schema_document() -> dict[str, Any]:
    """整包 JSON Schema。$defs 與 SCHEMAS 是同一份物件。"""
    return {
        "$schema": _SCHEMA_DIALECT,
        "$id": _BUNDLE_ID,
        "title": "LinkinTaskAnalyzerV01",
        "description": "任務分析器底層規格 v0.1。變更政策：只增不刪。",
        "$defs": SCHEMAS,
    }
