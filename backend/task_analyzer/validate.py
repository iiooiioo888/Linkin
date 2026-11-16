"""v0.1 JSON Schema 的最小驗證器。

只檢查結構：未知欄位、枚舉、版號、型別與兩條形狀不變量。
不建立錯誤碼目錄，也不跑規則或狀態機。
"""

from __future__ import annotations

from typing import Any

from backend.task_analyzer.schema import SCHEMA_VERSION, SCHEMAS


class SchemaError(ValueError):
    """結構不符合 v0.1 契約。kind 只區分失敗原因。"""

    def __init__(self, kind: str, message: str, *, path: str) -> None:
        self.kind = kind
        self.path = path
        super().__init__(f"{path}: {message}" if path else message)


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise SchemaError("schema", f"不支援的型別關鍵字 {expected}", path="")


def _fail(kind: str, message: str, path: str) -> None:
    raise SchemaError(kind, message, path=path)


def _invariants(title: str, value: dict[str, Any], path: str) -> None:
    if title == "MoneyBand" and value["low"] > value["high"]:
        _fail("range", "金額下緣不可高於上緣", path)
    if title != "Question":
        return
    ids = [item["id"] for item in value["options"]]
    if len(ids) != len(set(ids)):
        _fail("duplicate", "選項 id 不可重複", f"{path}.options")
    if value["recommended_default"] not in ids:
        _fail("invalid_enum", "推薦預設不在選項內", f"{path}.recommended_default")


def _check_object(
    value: dict[str, Any],
    schema: dict[str, Any],
    path: str,
    defs: dict[str, Any],
) -> None:
    properties: dict[str, Any] = schema.get("properties", {})
    if schema.get("additionalProperties") is False:
        extra = [key for key in value if key not in properties]
        if extra:
            joined = f"{path}.{extra[0]}"
            _fail("unknown_field", f"未知欄位 {extra[0]}", joined)
    for key in schema.get("required", []):
        if key not in value:
            _fail("missing_field", f"缺少欄位 {key}", f"{path}.{key}")
    for key, item in value.items():
        if key in properties:
            _check(item, properties[key], f"{path}.{key}", defs)
    _invariants(str(schema.get("title", "")), value, path)


def _check(value: Any, schema: dict[str, Any], path: str, defs: dict[str, Any]) -> None:
    if "$ref" in schema:
        name = str(schema["$ref"]).rsplit("/", 1)[-1]
        _check(value, defs[name], path, defs)
        return
    if "anyOf" in schema:
        _check_any(value, schema["anyOf"], path, defs)
        return
    if "const" in schema and value != schema["const"]:
        kind = "invalid_version" if schema["const"] == SCHEMA_VERSION else "invalid_const"
        _fail(kind, f"必須為 {schema['const']}", path)
    if "enum" in schema and value not in schema["enum"]:
        _fail("invalid_enum", f"非法枚舉值 {value!r}", path)
    expected = schema.get("type")
    if isinstance(expected, str) and not _type_ok(value, expected):
        _fail("type", f"型別應為 {expected}", path)
    if isinstance(expected, list) and not any(_type_ok(value, item) for item in expected):
        _fail("type", f"型別應為 {' 或 '.join(expected)}", path)
    if expected == "string" and len(value) < int(schema.get("minLength", 0)):
        _fail("min_length", "文字短於下限", path)
    if expected in {"number", "integer"} and "minimum" in schema:
        if value < schema["minimum"]:
            _fail("minimum", "數值低於下限", path)
    if expected == "array":
        if len(value) < int(schema.get("minItems", 0)):
            _fail("min_items", "項目數少於下限", path)
        for index, item in enumerate(value):
            _check(item, schema["items"], f"{path}[{index}]", defs)
    if expected == "object":
        _check_object(value, schema, path, defs)


def _check_any(
    value: Any,
    options: list[dict[str, Any]],
    path: str,
    defs: dict[str, Any],
) -> None:
    null_ok = any(item.get("type") == "null" for item in options)
    rest = [item for item in options if item.get("type") != "null"]
    if value is None:
        if null_ok:
            return
        _fail("type", "不可為 null", path)
    if len(rest) == 1:
        _check(value, rest[0], path, defs)
        return
    errors: list[SchemaError] = []
    for item in rest:
        try:
            _check(value, item, path, defs)
        except SchemaError as exc:
            errors.append(exc)
        else:
            return
    if errors:
        raise errors[0]
    _fail("type", "不符合任一允許形狀", path)


def validate(document: Any, schema_name: str) -> Any:
    """依名稱驗證。通過時回傳原物件。"""
    if schema_name not in SCHEMAS:
        _fail("schema", f"未知的結構名稱 {schema_name}", "$")
    _check(document, SCHEMAS[schema_name], "$", SCHEMAS)
    return document
