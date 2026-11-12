"""LLM 呼叫層（自 backend.core.llm 抽出）。

LLM 回應 JSON 解析（去 fence／抓最外層區塊）。
"""

from __future__ import annotations

import json
import re

from ._compat import split_thinking


def parse_json_response(text: str) -> dict:
    """穩健地解析 LLM 回傳的 JSON。

    依序嘗試：直接解析 → 去除 markdown 程式碼圍欄 →
    擷取最外層 {...} 區塊。
    """
    text = split_thinking(text)[1] or (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise
