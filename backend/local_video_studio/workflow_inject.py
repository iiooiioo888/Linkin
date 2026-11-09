"""ComfyUI workflow JSON 參數注入。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


class WorkflowMappingError(ValueError):
    """mapping 指向的 node／input 不存在。"""


def inject_params(
    workflow_json: dict[str, Any],
    params: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    """依 mapping 將 params 寫入 workflow 節點 inputs。

    mapping 格式：
    ``{"mappings": [{"param": "prompt", "node_id": "6", "input": "text"}, ...]}``
    """
    out = deepcopy(workflow_json)
    entries = mapping.get("mappings") or []
    if not isinstance(entries, list):
        raise WorkflowMappingError("mapping.mappings 須為陣列")

    for entry in entries:
        if not isinstance(entry, dict):
            raise WorkflowMappingError("mapping 項目須為物件")
        param = entry.get("param")
        node_id = str(entry.get("node_id", ""))
        input_name = entry.get("input")
        if not param or not node_id or not input_name:
            raise WorkflowMappingError(f"mapping 缺欄位：{entry}")
        if param not in params:
            continue
        node = out.get(node_id)
        if not isinstance(node, dict):
            raise WorkflowMappingError(f"node 不存在：{node_id}")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise WorkflowMappingError(f"node {node_id} 無 inputs")
        if input_name not in inputs:
            raise WorkflowMappingError(f"node {node_id} 無 input：{input_name}")
        inputs[input_name] = params[param]
    return out
