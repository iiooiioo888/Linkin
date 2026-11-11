"""比對工具（自 backend.company.raho.inspector 抽出）。

文字正規化、JSON 抽取、數字／詞彙 Jaccard 與事實比對分數。
"""

from __future__ import annotations

import json
import re
from typing import Any

from .constants import _NUMBER


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "、".join(str(x).strip() for x in value if str(x).strip())
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _extract_json(text: str) -> Any | None:
    raw = (text or "").strip()
    if not raw:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else None
    if blob is None:
        if raw.startswith(("{", "[")):
            blob = raw
        else:
            match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
            blob = match.group(1) if match else None
    if not blob:
        return None
    try:
        return json.loads(blob)
    except json.JSONDecodeError:
        return None


def _numbers(text: str) -> set[str]:
    return {m.group(1) for m in _NUMBER.finditer(text or "")}


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[\w\u4e00-\u9fff]+", (text or "").lower()) if t}


def exact_match(left: str, right: str) -> float:
    """精確比對：完全一致為 1.0，否則 0.0。"""
    a = (left or "").strip()
    b = (right or "").strip()
    if not a or not b:
        return 0.0
    return 1.0 if a == b else 0.0


def semantic_similarity(left: str, right: str) -> float:
    """無嵌入的交叉比對：詞彙 Jaccard 0.6 + 數字覆蓋 0.4。"""
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    jaccard = len(a & b) / len(a | b)
    claimed = _numbers(left)
    available = _numbers(right)
    if claimed:
        coverage = len(claimed & available) / len(claimed)
    else:
        coverage = 1.0
    return round(min(1.0, 0.6 * jaccard + 0.4 * coverage), 3)


def compare_facts(output: str, source: str) -> dict[str, float]:
    """測試 3 的比對工具包：exact_match + semantic_similarity。"""
    return {
        "exact_match": exact_match(output, source),
        "semantic_similarity": semantic_similarity(output, source),
    }
