"""任務分析器 v0.1：枚舉字典與 JSON Schema 契約。"""

from __future__ import annotations

import pytest

from backend.task_analyzer.enums import (
    COMPANION_ENUM_NAMES,
    ENUMS,
    PRIMARY_ENUM_NAMES,
    display_name,
)
from backend.task_analyzer.schema import CHANGE_POLICY, SCHEMA_VERSION, SCHEMAS, schema_document
from backend.task_analyzer.validate import SchemaError, validate

_PRIMARY = (
    "deployment",
    "task_type",
    "persistence",
    "criterion.metric",
    "hard_or_soft",
    "gap.severity",
    "question.category",
    "redline.category",
    "feasibility",
    "next_action",
    "input_channel",
    "priority",
)
_COMPANION = (
    "gap.disposition",
    "rule.status",
    "resource.kind",
    "hardware.kind",
    "execution_path",
    "decision_source",
)
_SHAPE: dict[str, list[str]] = {
    "MoneyBand": ["low", "high"],
    "QuestionOption": ["id", "label"],
    "Network": ["zone", "egress"],
    "Sensitivity": ["score", "threshold", "drivers"],
    "Criterion": ["schema_version", "id", "metric", "hard_or_soft", "target", "unit"],
    "TaskGoal": ["schema_version", "id", "statement", "criteria"],
    "EnvironmentSpec": [
        "schema_version",
        "deployment",
        "tenant_id",
        "region",
        "network",
        "compliance_regimes",
    ],
    "ResourceSpec": [
        "schema_version",
        "id",
        "kind",
        "name",
        "disposition",
        "endpoint",
        "tenant_id",
    ],
    "HardwareSpec": ["schema_version", "id", "deployment", "kind", "quantity", "notes"],
    "Question": [
        "schema_version",
        "id",
        "category",
        "prompt",
        "options",
        "recommended_default",
        "if_unanswered",
        "gap_id",
    ],
    "RedLine": ["schema_version", "id", "category", "hard_or_soft", "status", "evidence"],
    "BudgetEstimate": [
        "schema_version",
        "currency",
        "one_time",
        "runtime",
        "labor",
        "risk_maintenance",
        "assumptions",
        "sensitivity",
    ],
    "TaskSummary": [
        "schema_version",
        "task_type",
        "priority",
        "title",
        "statement",
        "goals",
        "boundaries",
        "environment",
        "resources",
        "hardware",
        "persistence",
    ],
    "Gap": ["schema_version", "id", "disposition", "severity", "summary", "blocking"],
    "TaskRequest": [
        "schema_version",
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
    "InterfaceA": [
        "schema_version",
        "interface",
        "tenant_id",
        "request_id",
        "task_summary",
        "gaps",
    ],
    "ConstraintPack": [
        "schema_version",
        "summary",
        "boundaries",
        "priority",
        "persistence",
        "accepted_defaults",
    ],
    "InterfaceB": [
        "schema_version",
        "interface",
        "tenant_id",
        "request_id",
        "constraints",
        "baseline_passed",
        "redlines",
    ],
    "Condition": ["schema_version", "id", "summary", "owner"],
    "Handoff": [
        "schema_version",
        "execution_path",
        "company_template",
        "budget_locked",
        "query",
    ],
    "ExecutionPathRecord": ["chosen", "source", "suggested", "reason"],
    "FeasibilityInput": ["schema_version", "decision_source"],
    "TaskAnalysisReport": [
        "schema_version",
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
        "execution_path",
    ],
    "InterfaceC": ["schema_version", "interface", "report"],
}
_VERSION = "v0.1"
# 只增不刪：新欄位可以不在 required，舊必填鍵保持原樣。
_OPTIONAL: dict[str, list[str]] = {
    "TaskAnalysisReport": ["execution_path"],
}


def _band(low: float = 1, high: float = 2) -> dict:
    return {"low": low, "high": high}


def _environment() -> dict:
    return {
        "schema_version": _VERSION,
        "deployment": "local",
        "tenant_id": "tenant-a",
        "region": "",
        "network": {"zone": "private", "egress": "restricted"},
        "compliance_regimes": [],
    }


def _criterion() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "c1",
        "metric": "pass_fail",
        "hard_or_soft": "soft",
        "target": "完成",
        "unit": "",
    }


def _goal() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "g1",
        "statement": "把報告交出去",
        "criteria": [_criterion()],
    }


def _resource() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "res-1",
        "kind": "mcp_server",
        "name": "opc-read",
        "disposition": "present",
        "endpoint": "",
        "tenant_id": "tenant-a",
    }


def _hardware() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "hw-1",
        "deployment": "local",
        "kind": "cpu",
        "quantity": 1,
        "notes": "",
    }


def _summary() -> dict:
    return {
        "schema_version": _VERSION,
        "task_type": "deliver",
        "priority": "P2",
        "title": "交一份說明",
        "statement": "說明既有介面",
        "goals": [_goal()],
        "boundaries": ["不改既有路由"],
        "environment": _environment(),
        "resources": [_resource()],
        "hardware": [_hardware()],
        "persistence": "audit_only",
    }


def _request() -> dict:
    summary = _summary()
    return {
        "schema_version": _VERSION,
        "tenant_id": "tenant-a",
        "request_id": "req-1",
        "input_channel": "task_api",
        "priority": summary["priority"],
        "task_type": summary["task_type"],
        "title": summary["title"],
        "statement": summary["statement"],
        "goals": summary["goals"],
        "boundaries": summary["boundaries"],
        "environment": summary["environment"],
        "resources": summary["resources"],
        "hardware": summary["hardware"],
        "persistence": summary["persistence"],
    }


def _gap() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "gap-1",
        "disposition": "missing",
        "severity": "blocking",
        "summary": "尚未指定部署位置",
        "blocking": True,
    }


def _interface_a() -> dict:
    return {
        "schema_version": _VERSION,
        "interface": "A",
        "tenant_id": "tenant-a",
        "request_id": "req-1",
        "task_summary": _summary(),
        "gaps": [_gap()],
    }


def _question() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "q1",
        "category": "goal",
        "prompt": "目標範圍？",
        "options": [
            {"id": "keep", "label": "維持原陳述"},
            {"id": "human", "label": "轉人工"},
        ],
        "recommended_default": "keep",
        "if_unanswered": "沒有目標就不能進入底線。",
        "gap_id": "gap-1",
    }


def _redline() -> dict:
    return {
        "schema_version": _VERSION,
        "id": "R-SEC-001",
        "category": "safety",
        "hard_or_soft": "hard",
        "status": "pass",
        "evidence": "未要求寫入。",
    }


def _budget() -> dict:
    return {
        "schema_version": _VERSION,
        "currency": "USD",
        "one_time": _band(),
        "runtime": _band(0, 1),
        "labor": _band(),
        "risk_maintenance": _band(0, 1),
        "assumptions": ["不含外購授權"],
        "sensitivity": {"score": 0.1, "threshold": 0.2, "drivers": []},
    }


def _interface_b() -> dict:
    return {
        "schema_version": _VERSION,
        "interface": "B",
        "tenant_id": "tenant-a",
        "request_id": "req-1",
        "constraints": {
            "schema_version": _VERSION,
            "summary": _summary(),
            "boundaries": ["不改既有路由"],
            "priority": "P2",
            "persistence": "audit_only",
            "accepted_defaults": [],
        },
        "baseline_passed": True,
        "redlines": [_redline()],
    }


def _report(*, budget: dict | None, interface_b: dict | None) -> dict:
    return {
        "schema_version": _VERSION,
        "tenant_id": "tenant-a",
        "request_id": "req-1",
        "feasibility": "conditional_go" if budget else "no_go",
        "next_action": "handoff" if budget else "stop",
        "priority": "P2",
        "interface_a": _interface_a(),
        "interface_b": interface_b,
        "budget": budget,
        "conditions": [
            {
                "schema_version": _VERSION,
                "id": "cond-1",
                "summary": "補上 MCP 端點",
                "owner": "analyst-1",
            }
        ],
        "handoff": {
            "schema_version": _VERSION,
            "execution_path": "company",
            "company_template": "quick_task",
            "budget_locked": False,
            "query": "說明既有介面",
        },
    }


def _interface_c() -> dict:
    return {
        "schema_version": _VERSION,
        "interface": "C",
        "report": _report(budget=_budget(), interface_b=_interface_b()),
    }


def test_enum_names_are_frozen() -> None:
    assert PRIMARY_ENUM_NAMES == _PRIMARY
    assert COMPANION_ENUM_NAMES == _COMPANION
    assert tuple(ENUMS) == _PRIMARY + _COMPANION


def test_every_value_has_traditional_chinese_label() -> None:
    assert ENUMS["priority"].keys() == {"P0", "P1", "P2", "P3"}
    for name, values in ENUMS.items():
        assert values, name
        for value, label in values.items():
            assert label.strip(), (name, value)
            assert any("\u4e00" <= char <= "\u9fff" for char in label)
            assert display_name(name, value) == label


def test_enum_mapping_is_immutable() -> None:
    with pytest.raises(TypeError):
        ENUMS["priority"]["P4"] = "新"  # type: ignore[index]


def test_unknown_enum_value_has_no_display_name() -> None:
    with pytest.raises(KeyError):
        display_name("priority", "P4")


def test_schema_shape_additional_properties_and_version() -> None:
    assert SCHEMA_VERSION == "v0.1"
    assert CHANGE_POLICY == "additive-only"
    assert set(SCHEMAS) == set(_SHAPE)
    for name, keys in _SHAPE.items():
        schema = SCHEMAS[name]
        optional = _OPTIONAL.get(name, [])
        assert list(schema["properties"]) == keys
        assert schema["required"] == [key for key in keys if key not in optional]
        assert schema["additionalProperties"] is False
        if "schema_version" in keys:
            assert schema["properties"]["schema_version"] == {"const": "v0.1"}
        else:
            assert "schema_version" not in schema["properties"]


def test_schema_enums_match_dictionary() -> None:
    found: set[tuple[str, ...]] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if "enum" in node:
                found.add(tuple(node["enum"]))
            for child in node.values():
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    for schema in SCHEMAS.values():
        walk(schema)
    assert found == {tuple(values) for values in ENUMS.values()}


def test_interface_boundaries() -> None:
    assert "questions" not in SCHEMAS["InterfaceA"]["properties"]
    assert "redlines" not in SCHEMAS["InterfaceA"]["properties"]
    assert "budget" not in SCHEMAS["InterfaceA"]["properties"]
    assert "budget" not in SCHEMAS["InterfaceB"]["properties"]
    report = SCHEMAS["TaskAnalysisReport"]["properties"]
    assert report["interface_a"] == {"$ref": "#/$defs/InterfaceA"}
    assert report["interface_b"]["anyOf"][0] == {"$ref": "#/$defs/InterfaceB"}
    assert report["budget"]["anyOf"][0] == {"$ref": "#/$defs/BudgetEstimate"}
    assert SCHEMAS["InterfaceA"]["properties"]["interface"] == {"const": "A"}
    assert SCHEMAS["InterfaceB"]["properties"]["interface"] == {"const": "B"}
    assert SCHEMAS["InterfaceC"]["properties"]["interface"] == {"const": "C"}


def test_schema_document_embeds_defs() -> None:
    document = schema_document()
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert document["$defs"] is SCHEMAS


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("Criterion", _criterion()),
        ("TaskGoal", _goal()),
        ("EnvironmentSpec", _environment()),
        ("ResourceSpec", _resource()),
        ("HardwareSpec", _hardware()),
        ("Question", _question()),
        ("RedLine", _redline()),
        ("BudgetEstimate", _budget()),
        ("TaskRequest", _request()),
        ("TaskSummary", _summary()),
        ("Gap", _gap()),
        ("InterfaceA", _interface_a()),
        ("InterfaceB", _interface_b()),
        ("TaskAnalysisReport", _report(budget=_budget(), interface_b=_interface_b())),
        ("TaskAnalysisReport", _report(budget=None, interface_b=None)),
        ("InterfaceC", _interface_c()),
    ],
)
def test_valid_documents(name: str, document: dict) -> None:
    assert validate(document, name) is document


def test_unknown_field_rejected() -> None:
    document = _request()
    document["guessed"] = True
    with pytest.raises(SchemaError) as caught:
        validate(document, "TaskRequest")
    assert caught.value.kind == "unknown_field"
    assert caught.value.path == "$.guessed"


def test_nested_unknown_field_rejected() -> None:
    document = _goal()
    document["criteria"][0]["weight"] = 1
    with pytest.raises(SchemaError) as caught:
        validate(document, "TaskGoal")
    assert caught.value.kind == "unknown_field"
    assert caught.value.path == "$.criteria[0].weight"


def test_interface_a_rejects_questions_and_budget() -> None:
    document = _interface_a()
    document["questions"] = [_question()]
    with pytest.raises(SchemaError) as caught:
        validate(document, "InterfaceA")
    assert caught.value.kind == "unknown_field"
    document = _interface_b()
    document["budget"] = _budget()
    with pytest.raises(SchemaError) as caught:
        validate(document, "InterfaceB")
    assert caught.value.kind == "unknown_field"


def test_invalid_enum_rejected() -> None:
    document = _criterion()
    document["metric"] = "bogus"
    with pytest.raises(SchemaError) as caught:
        validate(document, "Criterion")
    assert caught.value.kind == "invalid_enum"
    assert caught.value.path == "$.metric"


def test_schema_version_required_and_exact() -> None:
    document = _criterion()
    del document["schema_version"]
    with pytest.raises(SchemaError) as caught:
        validate(document, "Criterion")
    assert caught.value.kind == "missing_field"
    document = _criterion()
    document["schema_version"] = "v0.2"
    with pytest.raises(SchemaError) as caught:
        validate(document, "Criterion")
    assert caught.value.kind == "invalid_version"


def test_boolean_is_not_integer_quantity() -> None:
    document = _hardware()
    document["quantity"] = True
    with pytest.raises(SchemaError) as caught:
        validate(document, "HardwareSpec")
    assert caught.value.kind == "type"


def test_money_band_low_cannot_exceed_high() -> None:
    document = _budget()
    document["one_time"] = _band(5, 1)
    with pytest.raises(SchemaError) as caught:
        validate(document, "BudgetEstimate")
    assert caught.value.kind == "range"
    assert caught.value.path == "$.one_time"


def _execution_path_record() -> dict:
    return {
        "chosen": "company",
        "source": "user_explicit",
        "suggested": "simple",
        "reason": "這次由你指定路徑",
    }


def _feasibility_input(source: str = "user_explicit") -> dict:
    return {"schema_version": _VERSION, "decision_source": source}


def test_report_execution_path_records_choice_without_dropping_v01() -> None:
    report = SCHEMAS["TaskAnalysisReport"]
    assert SCHEMA_VERSION == "v0.1"
    assert report["properties"]["schema_version"] == {"const": "v0.1"}
    assert "execution_path" in report["properties"]
    assert "execution_path" not in report["required"]
    assert report["additionalProperties"] is False
    record = SCHEMAS["ExecutionPathRecord"]
    assert record["additionalProperties"] is False
    assert record["required"] == ["chosen", "source", "suggested", "reason"]
    assert record["properties"]["chosen"]["enum"] == ["simple", "company"]
    assert record["properties"]["suggested"]["enum"] == ["simple", "company"]
    assert record["properties"]["source"]["enum"] == [
        "user_explicit",
        "user_default",
        "admin_lock",
        "fallback",
    ]
    assert "auto" not in record["properties"]["chosen"]["enum"]
    assert "auto" not in record["properties"]["source"]["enum"]
    feasibility = SCHEMAS["FeasibilityInput"]
    assert feasibility["properties"]["decision_source"]["enum"] == record["properties"]["source"]["enum"]
    assert feasibility["additionalProperties"] is False


@pytest.mark.parametrize(
    "source",
    ["user_explicit", "user_default", "admin_lock", "fallback"],
)
def test_feasibility_input_accepts_decision_sources(source: str) -> None:
    document = _feasibility_input(source)
    assert validate(document, "FeasibilityInput") is document


def test_report_with_execution_path_validates() -> None:
    document = _report(budget=_budget(), interface_b=_interface_b())
    document["execution_path"] = _execution_path_record()
    assert validate(document, "TaskAnalysisReport") is document


def test_execution_path_rejects_unknown_field_and_auto() -> None:
    document = _report(budget=None, interface_b=None)
    document["execution_path"] = {**_execution_path_record(), "auto": True}
    with pytest.raises(SchemaError) as caught:
        validate(document, "TaskAnalysisReport")
    assert caught.value.kind == "unknown_field"
    assert caught.value.path == "$.execution_path.auto"

    document = _report(budget=None, interface_b=None)
    document["execution_path"] = {**_execution_path_record(), "chosen": "auto"}
    with pytest.raises(SchemaError) as caught:
        validate(document, "TaskAnalysisReport")
    assert caught.value.kind == "invalid_enum"
    assert caught.value.path == "$.execution_path.chosen"

    document = _report(budget=None, interface_b=None)
    document["execution_path"] = {**_execution_path_record(), "source": "auto"}
    with pytest.raises(SchemaError) as caught:
        validate(document, "TaskAnalysisReport")
    assert caught.value.kind == "invalid_enum"
    assert caught.value.path == "$.execution_path.source"


def test_feasibility_input_rejects_auto_and_unknown_field() -> None:
    with pytest.raises(SchemaError) as caught:
        validate(_feasibility_input("auto"), "FeasibilityInput")
    assert caught.value.kind == "invalid_enum"
    document = _feasibility_input()
    document["strategy"] = "auto"
    with pytest.raises(SchemaError) as caught:
        validate(document, "FeasibilityInput")
    assert caught.value.kind == "unknown_field"


def test_recommended_default_must_be_an_option() -> None:
    document = _question()
    document["recommended_default"] = "invented"
    with pytest.raises(SchemaError) as caught:
        validate(document, "Question")
    assert caught.value.kind == "invalid_enum"
    assert caught.value.path == "$.recommended_default"
