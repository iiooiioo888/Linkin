"""L0 知識實體抽取：規則切詞，不呼叫 LLM。

不另開 Chroma；向量化仍走 `backend.memory.vector_store.VectorMemoryStore`。
"""

from __future__ import annotations

import re

_ENTITY = re.compile(
    r"(轉化率|復購|電商|競品|Robots|代理池|反爬|合規|PDF|API|GMV|KPI|"
    r"爬蟲|價格監控|簡潔|表格)",
    re.IGNORECASE,
)
_FILE = re.compile(r"[\w./-]+\.(?:pdf|csv|json|md|txt|xlsx)", re.IGNORECASE)
_QUOTED = re.compile(r"[「『\"']([^」』\"']{2,40})[」』\"']")


def extract_entities(text: str, *, limit: int = 12) -> list[str]:
    """從用戶／門票文字抽出實體（術語、檔名、引號短語）。"""
    found: list[str] = []
    seen: set[str] = set()
    blob = text or ""
    for match in (*_ENTITY.finditer(blob), *_FILE.finditer(blob), *_QUOTED.finditer(blob)):
        token = match.group(1) if match.lastindex else match.group(0)
        key = token.strip()
        if len(key) < 2 or key.lower() in seen:
            continue
        seen.add(key.lower())
        found.append(key)
        if len(found) >= limit:
            break
    return found
