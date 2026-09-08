"""L0 動態記憶壓縮：把冗長對話／任務軌跡收成決策摘要。

不呼叫 LLM（規則截斷 + 關鍵句抽取），避免測試與離線環境依賴模型。
既有 `context_bus.compress` 仍負責向下傳遞；本模組負責跨輪次記憶銀行。
"""

from __future__ import annotations

import re

_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")
_DECISION = re.compile(
    r"(決定|裁定|採用|改用|禁止|必須|失敗|質詢|Grill|ESCALATE|APPROVED|REWORK|"
    r"代理池|Header|簡潔|字數|合規|Robots)",
    re.IGNORECASE,
)


def compress(text: str, limit: int = 720) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 16].rstrip() + "\n…(已壓縮)"


def extract_decisions(text: str, *, limit: int = 5) -> list[str]:
    """抽出帶決策語意的句子，供中期記憶（Lessons Learned）。"""
    found: list[str] = []
    seen: set[str] = set()
    for match in _SENTENCE.finditer(text or ""):
        sentence = match.group(0).strip()
        if len(sentence) < 6 or sentence in seen:
            continue
        if _DECISION.search(sentence):
            seen.add(sentence)
            found.append(compress(sentence, 160))
        if len(found) >= limit:
            break
    return found


def summarize_trace(
    *,
    title: str,
    body: str,
    failure_reason: str = "",
    limit: int = 280,
) -> str:
    """一筆記憶軌跡的壓縮摘要。"""
    parts = [title.strip()] if title.strip() else []
    decisions = extract_decisions(body)
    if decisions:
        parts.extend(decisions[:3])
    elif body.strip():
        parts.append(compress(body.strip(), 160))
    if failure_reason.strip():
        parts.append(f"失敗：{compress(failure_reason, 120)}")
    return compress("／".join(p for p in parts if p), limit)
