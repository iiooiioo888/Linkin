"""IR 識別與標籤 helper（自 backend.company.archify_compile 抽出）。

_ID_RE／_sid／_compact／_short_label。
"""

from __future__ import annotations

import re
from typing import Any

_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]*$")


def _sid(raw: Any, fallback: str = "n") -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw or fallback).strip())
    text = text.strip("_") or fallback
    if not text[0].isalpha():
        text = f"n_{text}"
    if not _ID_RE.match(text):
        text = "n_" + re.sub(r"[^a-zA-Z0-9_]", "", text)
    return text[:72]


def _compact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if v not in (None, "", [], {})}


def _short_label(raw: Any, limit: int = 16) -> str:
    text = str(raw or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"
