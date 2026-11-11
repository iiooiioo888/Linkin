"""L4 門票解析與估算（自 backend.services.commander 抽出）。

Token 估算、門票抽取、期限換算等純函式。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any


def estimate_tokens(text: str) -> int:
    """粗估 Token：CJK 一字一 token，拉丁詞一 token。"""
    raw = text or ""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", raw))
    latin = len(re.findall(r"[A-Za-z0-9_]+", raw))
    punct = len(re.findall(r"[^\w\s\u4e00-\u9fff]", raw))
    return max(1, cjk + latin + punct // 3) if raw.strip() else 0


def ticket_hash(ticket: dict[str, Any]) -> str:
    blob = json.dumps(ticket or {}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16].upper()


def extract_ticket(source: Any) -> dict[str, Any] | None:
    """從 dict／鎖定簡報／JSON 字串取出 L4 門票。"""
    if isinstance(source, dict):
        if source.get("status") == "APPROVED_FOR_PLANNING" and isinstance(
            source.get("clarified_goal"), dict
        ):
            return source
        inner = source.get("ticket")
        if isinstance(inner, dict):
            return extract_ticket(inner)
        brief = source.get("locked_brief")
        if isinstance(brief, str):
            return extract_ticket(brief)
        return None
    raw = str(source or "")
    if not raw.strip():
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    blob = fence.group(1) if fence else raw
    try:
        from backend.core.llm import parse_json_response

        data = parse_json_response(blob)
    except Exception:
        match = re.search(r"\{.*\}", blob, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    if data.get("status") != "APPROVED_FOR_PLANNING":
        return None
    return data


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def hours_until_deadline(deadline: str, now: datetime | None = None) -> float | None:
    text = (deadline or "").strip()
    if not text or text.startswith("未明示"):
        return None
    clock = now or datetime.now(timezone.utc).astimezone()
    iso = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if iso:
        try:
            due = datetime.strptime(iso.group(1), "%Y-%m-%d").replace(tzinfo=clock.tzinfo)
            return (due - clock).total_seconds() / 3600.0
        except ValueError:
            return None
    hours = re.search(r"(\d+(?:\.\d+)?)\s*(小時|小时)", text)
    if hours:
        return float(hours.group(1))
    days = re.search(r"(\d+(?:\.\d+)?)\s*(天|日|週|周)", text)
    if days:
        unit = days.group(2)
        n = float(days.group(1))
        return n * 24.0 if unit in {"天", "日"} else n * 24.0 * 7
    return None
