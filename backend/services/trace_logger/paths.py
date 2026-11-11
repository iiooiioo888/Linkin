"""軌跡與檢查點路徑 helper（自 backend.services.trace_logger 抽出）。

預設目錄常數、trace／checkpoint 路徑解析、UTC 時間與評估欄位轉換。
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# 預設軌跡目錄：backend/data/traces
DEFAULT_TRACE_DIR = Path(__file__).resolve().parents[2] / "data" / "traces"


# 檢查點目錄：backend/data/checkpoints
DEFAULT_CHECKPOINT_DIR = Path(__file__).resolve().parents[2] / "data" / "checkpoints"


def trace_dir() -> Path:
    """解析軌跡目錄（每次呼叫時解析，方便測試以環境變數覆蓋）。"""
    return Path(os.getenv("EVOL_TRACE_DIR", str(DEFAULT_TRACE_DIR)))


def checkpoint_dir() -> Path:
    """解析檢查點目錄。"""
    return Path(os.getenv("EVOL_CHECKPOINT_DIR", str(DEFAULT_CHECKPOINT_DIR)))


def trace_path(task_id: str) -> Path:
    """指定任務的 JSONL 軌跡檔案路徑。"""
    return trace_dir() / f"trace_{task_id}.jsonl"


def checkpoint_path(task_id: str) -> Path:
    """指定任務的檢查點檔案路徑。"""
    return checkpoint_dir() / f"checkpoint_{task_id}.json"


def utc_now_iso() -> str:
    """當前 UTC 時間的 ISO 字串。"""
    return datetime.now(timezone.utc).isoformat()


def eval_trace_kwargs(multi_dim: Any) -> dict[str, str]:
    """多維評估 → log_evaluation 欄位（feedback/strengths/weaknesses/raw_response）。

    chat 流與後台任務管線共用，確保兩條路徑的軌跡評估明細一致。
    """
    if not isinstance(multi_dim, dict) or not multi_dim:
        return {}
    dims = ("accuracy", "completeness", "clarity", "relevance")
    labels = {"accuracy": "準確", "completeness": "完整", "clarity": "清晰", "relevance": "相關"}

    def _fmt(dim: str) -> str:
        d = multi_dim.get(dim) or {}
        if not isinstance(d, dict):
            return ""
        score = d.get("score")
        reason = str(d.get("reason") or "").strip()
        return f"{labels[dim]}{score}：{reason[:120]}" if reason else f"{labels[dim]}{score}"

    parts = [p for p in (_fmt(x) for x in dims) if p]
    return {
        "feedback": f"來源 {multi_dim.get('source', '?')} · " + " / ".join(parts),
        "strengths": " / ".join(parts[:2]),
        "weaknesses": " / ".join(parts[2:]),
        "raw_response": json.dumps(multi_dim, ensure_ascii=False)[:3000],
    }
