"""將 Linkin 計費庫 usage 映射為 token-dashboard 看板 DATA schema。"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.billing.context import default_anonymous_user
from backend.billing.quota import get_billing_service

_WORKSPACE_LABELS: dict[str, str] = {
    "call_llm": "LLM 調用",
    "chat": "對話",
    "company": "公司運行時",
    "raho": "RAHO",
    "reflection": "反思閉環",
    "opc": "OPC",
    "minecraft": "Minecraft",
    "docker": "Docker",
    "llm_tokens": "LLM Token",
    "llm": "LLM",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_created_at(value: str | None) -> int | None:
    if not value:
        return None
    s = str(value).strip()
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() // 60)
    except ValueError:
        pass
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return int(dt.timestamp() // 60)
    except ValueError:
        return None


def _load_meta(raw: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _workspace_key(source: str, event_type: str) -> str:
    src = (source or "").strip().lower()
    et = (event_type or "").strip().lower()
    if src in _WORKSPACE_LABELS:
        return src
    if et in _WORKSPACE_LABELS:
        return et
    if "raho" in src or "raho" in et:
        return "raho"
    if "company" in src or "company" in et:
        return "company"
    if "chat" in src or "chat" in et:
        return "chat"
    return src or et or "other"


def _workspace_label(key: str) -> str:
    return _WORKSPACE_LABELS.get(key, key.replace("_", " ").title() or "其他")


def _session_title(meta: dict[str, Any], task_id: str, reference: str) -> str:
    for key in ("title", "session_title", "reference", "role", "tool"):
        val = str(meta.get(key) or "").strip()
        if val:
            return val[:42]
    ref = (reference or "").strip()
    if ref:
        return ref[:42]
    tid = (task_id or "").strip()
    return tid[:42] if tid else "(無標題任務)"


def _model_name(meta: dict[str, Any], fallback: str = "unknown") -> str:
    for key in ("model", "request_model", "requestModelId"):
        val = str(meta.get(key) or "").strip()
        if val:
            return val
    return fallback


def _request_tuple(
    minute: int,
    model_idx: int,
    *,
    total_tokens: int,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int,
    cache_write_tokens: int,
) -> tuple[int, int, int, int, int, int, int] | None:
    tt = max(0, int(total_tokens))
    if tt <= 0:
        return None
    ch = max(0, min(int(cached_tokens), tt))
    cw = max(0, min(int(cache_write_tokens), tt))
    if input_tokens is not None and output_tokens is not None:
        it = max(0, int(input_tokens))
        ot = max(0, int(output_tokens))
    elif input_tokens is not None:
        it = max(0, int(input_tokens))
        ot = max(0, tt - it)
    elif output_tokens is not None:
        ot = max(0, int(output_tokens))
        it = max(0, tt - ot)
    else:
        # 僅有合計 token、無輸入/輸出拆分時仍展示總量（不臆造 IO 比）
        it = max(0, tt - ch - cw)
        ot = 0
    return (minute, model_idx, tt, it, ot, ch, cw)


def _fetch_pool_events(conn: Any, user_id: str, since_iso: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, task_id, event_type, source, tokens, cached_tokens,
               cache_write_tokens, cost_credits, meta_json, created_at
        FROM pool_usage_events
        WHERE account_id = ? AND created_at >= ? AND tokens > 0
        ORDER BY created_at ASC
        """,
        (user_id, since_iso),
    ).fetchall()
    return [dict(r) for r in rows]


def _fetch_usage_events(conn: Any, user_id: str, since_iso: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT id, task_id, event_type, reference, quantity, meta_json, created_at
        FROM usage_events
        WHERE user_id = ? AND created_at >= ? AND event_type = 'llm_tokens'
        ORDER BY created_at ASC
        """,
        (user_id, since_iso),
    ).fetchall()
    return [dict(r) for r in rows]


def collect_linkin_usage(user_id: str | None = None, *, days: int = 90) -> dict[str, Any]:
    """從 billing.sqlite3 彙整請求級 token usage，輸出看板 DATA dict。"""
    uid = (user_id or default_anonymous_user()).strip()
    days = max(1, min(int(days), 365))
    since = _utc_now() - timedelta(days=days)
    since_iso = since.isoformat()

    store = get_billing_service().store
    pool_rows: list[dict[str, Any]] = []
    usage_rows: list[dict[str, Any]] = []
    with store._connect() as conn:
        pool_rows = _fetch_pool_events(conn, uid, since_iso)
        usage_rows = _fetch_usage_events(conn, uid, since_iso)

    now = _utc_now()
    gen_ms = int(now.timestamp() * 1000)
    ws_keys: list[str] = []
    ws_idx: dict[str, int] = {}
    models: list[str] = []
    model_idx: dict[str, int] = {}
    sessions: dict[str, dict[str, Any]] = {}
    pool_task_minutes: set[tuple[str, int]] = set()

    def add_record(
        *,
        session_id: str,
        workspace_key: str,
        title: str,
        minute: int | None,
        model: str,
        total_tokens: int,
        input_tokens: int | None,
        output_tokens: int | None,
        cached_tokens: int,
        cache_write_tokens: int,
    ) -> None:
        if minute is None:
            return
        if workspace_key not in ws_idx:
            ws_idx[workspace_key] = len(ws_keys)
            ws_keys.append(workspace_key)
        m = model or "unknown"
        if m not in model_idx:
            model_idx[m] = len(models)
            models.append(m)
        rec = _request_tuple(
            minute,
            model_idx[m],
            total_tokens=total_tokens,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cache_write_tokens=cache_write_tokens,
        )
        if rec is None:
            return
        sess = sessions.setdefault(
            session_id,
            {
                "w": ws_idx[workspace_key],
                "id": session_id[:8],
                "t": title,
                "r": [],
            },
        )
        if not sess.get("t"):
            sess["t"] = title
        sess["r"].append(rec)

    for row in pool_rows:
        meta = _load_meta(row.get("meta_json"))
        minute = _parse_created_at(row.get("created_at"))
        task_id = str(row.get("task_id") or meta.get("task_id") or row.get("event_id") or "")
        session_id = task_id or str(row.get("event_id") or "")
        ws_key = _workspace_key(str(row.get("source") or ""), str(row.get("event_type") or ""))
        title = _session_title(meta, task_id, "")
        total = int(row.get("tokens") or 0)
        cached = int(row.get("cached_tokens") or meta.get("cache_read_tokens") or 0)
        cache_write = int(row.get("cache_write_tokens") or meta.get("cache_write_tokens") or 0)
        inp = meta.get("input_tokens")
        out = meta.get("output_tokens")
        add_record(
            session_id=session_id,
            workspace_key=ws_key,
            title=title,
            minute=minute,
            model=_model_name(meta),
            total_tokens=total,
            input_tokens=int(inp) if inp is not None else None,
            output_tokens=int(out) if out is not None else None,
            cached_tokens=cached,
            cache_write_tokens=cache_write,
        )
        if minute is not None:
            pool_task_minutes.add((session_id, minute))

    for row in usage_rows:
        meta = _load_meta(row.get("meta_json"))
        minute = _parse_created_at(row.get("created_at"))
        ref = str(row.get("id") or "")
        task_id = str(row.get("task_id") or meta.get("task_id") or ref)
        session_id = task_id or ref
        if minute is not None and (session_id, minute) in pool_task_minutes:
            continue
        ws_key = _workspace_key(str(meta.get("source") or ""), str(row.get("event_type") or ""))
        title = _session_title(meta, task_id, str(row.get("reference") or ""))
        quantity = int(row.get("quantity") or 0)
        inp = meta.get("input_tokens")
        out = meta.get("output_tokens")
        total = quantity or (int(inp or 0) + int(out or 0))
        add_record(
            session_id=session_id,
            workspace_key=ws_key,
            title=title,
            minute=minute,
            model=_model_name(meta),
            total_tokens=total,
            input_tokens=int(inp) if inp is not None else None,
            output_tokens=int(out) if out is not None else None,
            cached_tokens=int(meta.get("cache_read_tokens") or meta.get("cached_tokens") or 0),
            cache_write_tokens=int(meta.get("cache_write_tokens") or 0),
        )

    sess_list: list[dict[str, Any]] = []
    for sid, data in sessions.items():
        recs = data.get("r") or []
        if not recs:
            continue
        recs.sort(key=lambda x: x[0])
        sess_list.append(
            {
                "w": data["w"],
                "id": str(data.get("id") or sid[:8]),
                "t": data.get("t") or "(無標題任務)",
                "st": recs[0][0],
                "r": recs,
            }
        )
    sess_list.sort(key=lambda s: s["st"])

    source_note = "Linkin 計費庫"
    if os.path.isdir(os.path.join(os.path.expanduser("~"), ".workbuddy", "projects")):
        source_note += "（本機亦有 WorkBuddy 日誌可選）"

    return {
        "genMs": gen_ms,
        "gen": now.strftime("%Y-%m-%d %H:%M"),
        "ws": [_workspace_label(k) for k in ws_keys],
        "models": models,
        "sess": sess_list,
        "source": source_note,
        "user_id": uid,
        "days": days,
    }


def dashboard_stats(data: dict[str, Any]) -> dict[str, Any]:
    total_tokens = 0
    turns = 0
    for sess in data.get("sess") or []:
        for rec in sess.get("r") or []:
            total_tokens += int(rec[2])
            turns += 1
    return {
        "user_id": data.get("user_id"),
        "days": data.get("days"),
        "sessions": len(data.get("sess") or []),
        "models": len(data.get("models") or []),
        "workspaces": len(data.get("ws") or []),
        "requests": turns,
        "total_tokens": total_tokens,
        "empty": turns == 0,
        "source": data.get("source"),
    }
