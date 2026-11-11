"""L1 憲兵審查官：憲法層（唯讀）＋四維度驗收＋雙向 Grill＋簽核閘門。

L1 不隸屬 L3，直接對最終交付品質負責。
禁止同理心、禁止跨級代勞；只有 VERDICT: APPROVED 的數據可寫入共享記憶體。

本檔案已於第七輪重構拆為套件：對外仍以
from backend.company.raho.inspector import InspectorGate, run_inspection 等名稱匯入；
實作分散在 constants／models／similarity／schema／service／gate 等模組，內容與行為逐字不變。
"""

from __future__ import annotations

# 以下 13 個名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import hashlib  # noqa: F401
import json  # noqa: F401
import os  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401
from collections.abc import Callable  # noqa: F401
from dataclasses import dataclass, field  # noqa: F401
from typing import Any  # noqa: F401

from backend.company.raho.atomic_executor import AtomicTaskSpec, spec_from_mapping  # noqa: F401
from backend.company.raho.protocol import ESCALATE_MARK, GRILL_MARK, GrillIssue  # noqa: F401

from .constants import (  # noqa: F401
    CONSTITUTION_LAYER,
    FAIL,
    GRILL_TARGET_L2,
    GRILL_TARGET_L3,
    GRILL_TARGET_L4,
    GRILL_TARGET_L5,
    INSPECTION_LAYER_MARKER,
    INSPECTOR_ID,
    INSPECTOR_MARKER,
    PASS,
    TEST_EDGE,
    TEST_FACTUAL,
    TEST_KEYS,
    TEST_LABELS,
    TEST_SCHEMA,
    TEST_SEMANTIC,
    VERDICT_APPROVED,
    VERDICT_ESCALATE,
    VERDICT_REWORK,
    VERDICTS,
)
from .gate import InspectorGate
from .models import EscalateRequired, InspectorGrill, InspectorVerdict, ReworkRequired
from .service import (  # noqa: F401
    compose_inspector_prompt,
    has_inspector_constitution,
    l1_llm_enabled,
    parse_inspector_grill,
    parse_verdict,
    read_signed_memory,
    render_inspection_layer,
    resolve_input_ref,
    run_inspection,
    sign_payload,
    source_for_artifacts,
    write_signed_memory,
)
from .similarity import compare_facts, exact_match, semantic_similarity

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

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in (
    "constants", "gate", "models", "schema", "service", "similarity"
):
    globals().pop(_submodule, None)
del _submodule
