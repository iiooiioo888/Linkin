"""任務層 spec 正規化與文字／工具轉換 helper。"""

from __future__ import annotations

import json
import re
from typing import Any

from .constants import _EMPTY_REFS, DEFAULT_MAX_ITERATIONS, DEFAULT_TOKEN_BUDGET
from .models import AtomicTaskSpec


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
    raw_iters = raw.get("max_iterations")
    try:
        iters = int(raw_iters) if raw_iters is not None else DEFAULT_MAX_ITERATIONS
    except (TypeError, ValueError):
        iters = DEFAULT_MAX_ITERATIONS
    raw_tokens = raw.get("token_budget")
    try:
        tokens = int(raw_tokens) if raw_tokens is not None else DEFAULT_TOKEN_BUDGET
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
