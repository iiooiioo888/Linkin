"""共用小工具：JSON 輸出、數值轉換與錯誤 payload。"""

from __future__ import annotations

import json
from typing import Any


def dumps_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)

def _fail(error: str | BaseException, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": str(error)[:400], **extra}
    payload.setdefault("disclaimer", "公開數據僅供研究，非投資建議。")
    return payload

def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
