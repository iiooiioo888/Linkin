"""任務分析器結構契約（v0.1）。

本套件目前只匯出 JSON Schema 與枚舉字典。
"""

from backend.task_analyzer.enums import (
    COMPANION_ENUM_NAMES,
    ENUMS,
    PRIMARY_ENUM_NAMES,
    display_name,
    enum_values,
)
from backend.task_analyzer.schema import (
    CHANGE_POLICY,
    SCHEMA_VERSION,
    SCHEMAS,
    schema_document,
)
from backend.task_analyzer.validate import SchemaError, validate

__all__ = [
    "CHANGE_POLICY",
    "COMPANION_ENUM_NAMES",
    "ENUMS",
    "PRIMARY_ENUM_NAMES",
    "SCHEMAS",
    "SCHEMA_VERSION",
    "SchemaError",
    "display_name",
    "enum_values",
    "schema_document",
    "validate",
]
