"""伺服器運維的待審批隊列：載入／儲存／建立／確認／取消（自 backend.linkin.server_admin 抽出）。"""

from __future__ import annotations

import json
import threading
import time
import uuid
from typing import Any

from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError

from .config import DEFAULT_TTL_MIN, PENDING_KEEP_DAYS, _env_int, logger, pending_path

_lock = threading.RLock()
_pending_cache: dict[str, Any] | None = None
_pending_mtime: float | None = None


def reset_cache() -> None:
    """清空批准隊列的模組級快取（測試隔離用）。"""
    global _pending_cache, _pending_mtime
    with _lock:
        _pending_cache = None
        _pending_mtime = None


def _load_pending() -> dict[str, Any]:
    global _pending_cache, _pending_mtime
    path = pending_path()
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = None
    if _pending_cache is not None and _pending_mtime == mtime:
        return _pending_cache
    store: dict[str, Any] = {"approvals": []}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("approvals"), list):
                store["approvals"] = [a for a in raw["approvals"] if isinstance(a, dict)]
        except (OSError, json.JSONDecodeError):
            logger.warning("讀取批准隊列失敗，改用空隊列：%s", path)
    _pending_cache = store
    _pending_mtime = mtime
    return store


def _save_pending(store: dict[str, Any]) -> None:
    global _pending_cache, _pending_mtime
    cutoff = time.time() - PENDING_KEEP_DAYS * 86400
    store["approvals"] = [
        a for a in store.get("approvals", [])
        if a.get("status") == "pending" or float(a.get("created_ts") or 0) >= cutoff
    ][-500:]
    path = pending_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    _pending_cache = store
    try:
        _pending_mtime = path.stat().st_mtime
    except OSError:
        _pending_mtime = None


def _ttl_min() -> int:
    return _env_int("EVOL_SA_PENDING_TTL_MIN", DEFAULT_TTL_MIN, 1, 1440)


def _is_expired(record: dict[str, Any]) -> bool:
    if record.get("status") != "pending":
        return False
    deadline = float(record.get("created_ts") or 0) + float(record.get("ttl_min") or DEFAULT_TTL_MIN) * 60
    return time.time() > deadline


def create_approval(tool: str, params: dict[str, Any], preview: dict[str, Any], question: str = "") -> dict[str, Any]:
    """為寫操作建立待批准記錄（含無副作用的預覽掃描結果）。"""
    record = {
        "id": f"sa-{uuid.uuid4().hex[:10]}",
        "tool": tool,
        "params": params,
        "question": question[:300],
        "preview": {k: preview.get(k) for k in ("message", "count", "bytes", "days", "max_mb", "service", "subdir") if k in preview},
        "status": "pending",
        "created_ts": time.time(),
        "ttl_min": _ttl_min(),
        "resolved_ts": None,
        "result": None,
    }
    with _lock:
        store = dict(_load_pending())
        store["approvals"] = [*store.get("approvals", []), record]
        _save_pending(store)
    return record


def list_approvals(include_done: bool = False) -> list[dict[str, Any]]:
    with _lock:
        store = _load_pending()
        approvals = store.get("approvals", [])
        out: list[dict[str, Any]] = []
        changed = False
        for index, record in enumerate(approvals):
            if _is_expired(record):
                record = {**record, "status": "expired"}
                approvals[index] = record
                changed = True
            if record["status"] == "pending" or include_done:
                out.append(record)
        if changed:
            _save_pending(store)
        return out


def _get_pending_or_raise(approval_id: str) -> dict[str, Any]:
    with _lock:
        store = _load_pending()
        for record in store.get("approvals", []):
            if record.get("id") == approval_id:
                if _is_expired(record):
                    record["status"] = "expired"
                    record["resolved_ts"] = time.time()
                    _save_pending(store)
                    raise ServerAdminError("批准請求已過期，請重新發起", code="expired", extra={"id": approval_id})
                return record
    raise LookupError(f"批准請求不存在：{approval_id}")


def confirm_approval(approval_id: str) -> dict[str, Any]:
    """管理員批准 → 以 confirmed=True 執行寫工具 → 記錄結果。"""
    with _lock:
        store = _load_pending()
        record = _get_pending_or_raise(approval_id)
        if record["status"] != "pending":
            raise ServerAdminError(
                f"批准請求狀態為 {record['status']}，不可重複確認",
                code="invalid_state",
                extra={"id": approval_id, "status": record["status"]},
            )
        try:
            result = sa.execute_named_tool(record["tool"], record["params"], confirm=True)
            record["status"] = "executed" if result.get("ok", False) else "failed"
            record["result"] = result
        except ServerAdminError as exc:
            record["status"] = "failed"
            record["result"] = {"ok": False, "code": exc.code, "message": str(exc)}
        record["resolved_ts"] = time.time()
        _save_pending(store)
        return dict(record)


def cancel_approval(approval_id: str) -> dict[str, Any]:
    with _lock:
        store = _load_pending()
        record = _get_pending_or_raise(approval_id)
        if record["status"] != "pending":
            raise ServerAdminError(
                f"批准請求狀態為 {record['status']}，不可取消",
                code="invalid_state",
                extra={"id": approval_id, "status": record["status"]},
            )
        record["status"] = "cancelled"
        record["resolved_ts"] = time.time()
        _save_pending(store)
        return dict(record)
