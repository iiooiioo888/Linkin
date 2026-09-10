"""席位調用輸入／輸出軌跡（公司運行時監察的單一真相源）。

記錄每一次「真正投遞給模型」的完整上下文：系統提示詞、組裝後的
prompt 全文（含上下文匯流排、角色記憶、工具白名單、戰役簡報、
執行前裁決）、模型回應原文，以及這次投遞的來源分解。

與 run_<run_id>.jsonl 分開存放（seat_<run_id>.jsonl），因為
agent_monitor._ingest_run_logs 會把該檔案的每個事件併入各席位
events[]，混入逐次模型調用會排掉真正的生命週期事件。

特性：
- 有界記憶體環形緩衝供即時餵給（feed），進程重啟後由 JSONL 補齊
- 寫入失敗僅記錄警告，絕不中斷公司主流程
- 全文明文上限 TEXT_LIMIT；超出時保留長度資訊並標記 truncated
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import deque
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from backend.company.run_log import run_log_dir

logger = logging.getLogger(__name__)

# 記憶體環形緩衝容量（跨所有 run 的最近 N 次投遞）
BUFFER_CAPACITY = 1500
# 單欄明文上限；超出截斷並標記 truncated
TEXT_LIMIT = 40000
# context_sources 每條預覽長度
SOURCE_PREVIEW = 600

# 當前 run 綁定：讓 orchestrator 之外的模組（decomposer／inspector）
# 不必逐層穿參也能把投遞寫到正確的 run 上。asyncio 子任務在建立時
# 複製上下文，因此並行的公司任務之間不會互相污染。
_CURRENT_RUN: ContextVar[tuple[str, str]] = ContextVar("evoloop_seat_io_run", default=("", ""))


def bind_run(run_id: str, task_id: str = "") -> Token:
    """綁定當前 run（回傳 token 供 unbind_run 還原）。"""
    return _CURRENT_RUN.set((str(run_id or ""), str(task_id or "")))


def unbind_run(token: Token) -> None:
    """還原 run 綁定。"""
    try:
        _CURRENT_RUN.reset(token)
    except (ValueError, LookupError):
        pass


def current_run() -> tuple[str, str]:
    """讀當前綁定的 (run_id, task_id)。"""
    return _CURRENT_RUN.get()


def seat_log_path(run_id: str) -> Path:
    """指定 run 的席位 I/O JSONL 路徑（與 run_*.jsonl 同目錄、不同前綴）。"""
    return run_log_dir() / f"seat_{run_id or 'unknown'}.jsonl"


def _clip(text: Any, limit: int = TEXT_LIMIT) -> tuple[str, bool]:
    value = "" if text is None else str(text)
    if len(value) <= limit:
        return value, False
    return value[:limit], True


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SeatIOStore:
    """執行緒安全的席位投遞倉：環形緩衝 + JSONL 持久 sink。"""

    def __init__(self, capacity: int = BUFFER_CAPACITY) -> None:
        self._lock = threading.Lock()
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)

    # ── 寫入 ──

    def record(self, data: dict[str, Any]) -> dict[str, Any]:
        """落一筆投遞記錄（環形緩衝 + JSONL），回傳正規化後的記錄。"""
        prompt, prompt_trunc = _clip(data.get("prompt"))
        response, response_trunc = _clip(data.get("response"))
        system, system_trunc = _clip(data.get("system"))
        ctx_run_id, ctx_task_id = current_run()

        record = {
            "io_id": uuid.uuid4().hex[:12],
            "ts": _now_iso(),
            "epoch": time.time(),
            "run_id": str(data.get("run_id") or ctx_run_id or ""),
            "task_id": str(data.get("task_id") or ctx_task_id or ""),
            "item_id": str(data.get("item_id") or ""),
            "title": str(data.get("title") or ""),
            "role": str(data.get("role") or ""),
            "role_label": str(data.get("role_label") or ""),
            "layer": data.get("layer"),
            "layer_label": str(data.get("layer_label") or ""),
            "lane": str(data.get("lane") or ""),
            "kind": str(data.get("kind") or "execute"),
            "attempt": int(data.get("attempt") or 0),
            "step": int(data.get("step") or 0),
            "tool_steps": int(data.get("tool_steps") or 0),
            "final": bool(data.get("final", True)),
            "model": str(data.get("model") or ""),
            "tier": str(data.get("tier") or ""),
            "temperature": data.get("temperature"),
            "system": system,
            "prompt": prompt,
            "response": response,
            "system_length": len(str(data.get("system") or "")),
            "prompt_length": len(str(data.get("prompt") or "")),
            "response_length": len(str(data.get("response") or "")),
            "truncated": bool(prompt_trunc or response_trunc or system_trunc),
            "cost_usd": data.get("cost_usd"),
            "duration_ms": data.get("duration_ms"),
            "error": str(data.get("error") or ""),
            "degraded": bool(data.get("degraded", False)),
            # 本輪投遞的來源分解：讓監察頁能回答「這段 prompt 是哪些部分拼起來的」
            "allowed_tools": [str(t) for t in (data.get("allowed_tools") or [])],
            "input_ref": data.get("input_ref"),
            "output_schema": str(data.get("output_schema") or ""),
            "success_criteria": str(data.get("success_criteria") or ""),
            "context_sources": _normalize_sources(data.get("context_sources")),
        }

        with self._lock:
            self._records.append(record)

        self._persist(record)
        return record

    @staticmethod
    def _persist(record: dict[str, Any]) -> Path | None:
        try:
            directory = run_log_dir()
            directory.mkdir(parents=True, exist_ok=True)
            path = seat_log_path(record["run_id"])
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return path
        except OSError:
            logger.warning("席位 I/O 軌跡寫入失敗（已忽略）：run_id=%s", record.get("run_id"), exc_info=True)
            return None

    # ── 查詢 ──

    def list(
        self,
        *,
        run_id: str = "",
        task_id: str = "",
        role: str = "",
        layer: Any = None,
        item_id: str = "",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """依條件過濾環形緩衝，回傳新→舊順序。"""
        want_layer = None if layer in (None, "") else int(layer)
        with self._lock:
            pool = list(self._records)
        out: list[dict[str, Any]] = []
        for rec in reversed(pool):
            if run_id and rec["run_id"] != run_id:
                continue
            if task_id and rec["task_id"] != task_id:
                continue
            if role and rec["role"] != role:
                continue
            if want_layer is not None and rec.get("layer") != want_layer:
                continue
            if item_id and rec["item_id"] != item_id:
                continue
            out.append(rec)
            if len(out) >= max(1, limit):
                break
        return out

    def get(self, io_id: str) -> dict[str, Any] | None:
        """按 io_id 取單筆（先查環形緩衝，再掃持久 JSONL）。"""
        with self._lock:
            for rec in reversed(self._records):
                if rec["io_id"] == io_id:
                    return rec
        return self._read_from_disk(io_id)

    @staticmethod
    def _read_from_disk(io_id: str) -> dict[str, Any] | None:
        try:
            files = sorted(run_log_dir().glob("seat_*.jsonl"), reverse=True)[:20]
        except OSError:
            return None
        for path in files:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for line in reversed(lines):
                line = line.strip()
                if not line or io_id not in line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and record.get("io_id") == io_id:
                    return record
        return None

    def load_run(self, run_id: str, *, limit: int = 500) -> List[dict[str, Any]]:
        """讀指定 run 的持久投遞軌跡（舊於環形緩衝的歷史）。"""
        path = seat_log_path(run_id)
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                out.append(record)
            if len(out) >= max(1, limit):
                break
        return out

    def recent_runs(self, *, limit: int = 20) -> List[dict[str, Any]]:
        """環形緩衝中出现過的 run 摘要（供監察頁選單）。"""
        with self._lock:
            pool = list(self._records)
        buckets: dict[str, dict[str, Any]] = {}
        for rec in pool:
            key = rec["run_id"] or rec["task_id"] or "unknown"
            bucket = buckets.setdefault(
                key,
                {
                    "run_id": rec["run_id"],
                    "task_id": rec["task_id"],
                    "invocations": 0,
                    "roles": set(),
                    "items": set(),
                    "first_ts": rec["ts"],
                    "last_ts": rec["ts"],
                    "total_cost_usd": 0.0,
                },
            )
            bucket["invocations"] += 1
            if rec["role"]:
                bucket["roles"].add(rec["role"])
            if rec["item_id"]:
                bucket["items"].add(rec["item_id"])
            bucket["last_ts"] = max(bucket["last_ts"], rec["ts"])
            bucket["first_ts"] = min(bucket["first_ts"], rec["ts"])
            bucket["total_cost_usd"] += float(rec.get("cost_usd") or 0)
        rows = sorted(buckets.values(), key=lambda r: r["last_ts"], reverse=True)[:limit]
        for row in rows:
            row["roles"] = sorted(row["roles"])
            row["items"] = sorted(row["items"])
            row["role_count"] = len(row["roles"])
            row["item_count"] = len(row["items"])
            row["total_cost_usd"] = round(row["total_cost_usd"], 6)
        return rows

    def clear(self) -> None:
        with self._lock:
            self._records.clear()


def _normalize_sources(raw: Any) -> list[dict[str, Any]]:
    """來源分解正規化：每條带 kind/label/chars/preview。"""
    items = raw if isinstance(raw, list) else []
    out: list[dict[str, Any]] = []
    for entry in items[:24]:
        if isinstance(entry, dict):
            text = str(entry.get("text") or entry.get("preview") or "")
            out.append(
                {
                    "kind": str(entry.get("kind") or "unknown"),
                    "label": str(entry.get("label") or ""),
                    "chars": int(entry.get("chars") or len(text)),
                    "preview": text[:SOURCE_PREVIEW],
                }
            )
        elif entry is not None:
            text = str(entry)
            out.append({"kind": "unknown", "label": "", "chars": len(text), "preview": text[:SOURCE_PREVIEW]})
    return out


# 模組級單例：公司主流程與 API 層共用
STORE = SeatIOStore()


def record_seat_io(data: dict[str, Any]) -> dict[str, Any] | None:
    """記錄一次席位投遞；失敗回傳 None，絕不中斷公司主流程。"""
    try:
        return STORE.record(data)
    except Exception:
        logger.warning("席位 I/O 記錄失敗（已忽略）", exc_info=True)
        return None


__all__ = [
    "BUFFER_CAPACITY",
    "STORE",
    "TEXT_LIMIT",
    "SeatIOStore",
    "bind_run",
    "current_run",
    "record_seat_io",
    "seat_log_path",
    "unbind_run",
]
