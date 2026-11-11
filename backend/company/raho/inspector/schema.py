"""Schema 驗證（自 backend.company.raho.inspector 抽出）。

從 OUTPUT_SCHEMA 抽必填欄位並驗證 JSON 結構合規性。
"""

from __future__ import annotations

from backend.company.raho.atomic_executor import AtomicTaskSpec

from .constants import _JSON_SCHEMA, _KEY_IN_SCHEMA, _REQUIRED_FIELD, FAIL, PASS
from .similarity import _extract_json


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
