"""敘事核心臨時工作區（TODO §4.7；契約 C-L0-004）。

契約（寫死）：
- **世界觀單一真相來源**＝L0 知識圖譜＋憲法／實體 store；敘事核心**不得**
  維護第二套可寫世界觀圖譜——因此本模組刻意**不提供**任何圖譜寫入方法
  （無 ``write_graph``／``put_entity``／``upsert_relation``）。
- 臨時工作區僅存**記憶體草稿**（劇情分支中間態、關係草稿、待審批任務），
  必帶 ``workspace_id`` 並關聯 L0 圖譜 ``snapshot_id``。
- 生命週期不得超過當前任務：:func:`WorkspaceRegistry.end_task` 一律丟棄。
- 落庫一律經**顯式寫入 API**：:func:`WorkspaceRegistry.commit` 只接受
  呼叫方注入的 ``writer`` callable（對接 ``/linkin/*`` 或模組閘道）。
- L0 刷新導致快照變更時，工作區**預設進入 awaiting_confirmation**
  （保留用戶工作成果）；「丟棄」為顯式選項；禁止靜默沿用舊快照。
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

_persist_lock = threading.Lock()

# 錯誤碼（寫死，前後端共用）
ERR_WORKSPACE_UNKNOWN = "ERR_WORKSPACE_UNKNOWN"
ERR_WORKSPACE_NOT_ACTIVE = "ERR_WORKSPACE_NOT_ACTIVE"
ERR_CONFIRM_CHOICE_INVALID = "ERR_CONFIRM_CHOICE_INVALID"
ERR_SNAPSHOT_UNRESOLVED = "ERR_SNAPSHOT_UNRESOLVED"

CHOICE_REBIND = "rebind"    # 以新上下文重綁（保留草稿）
CHOICE_DISCARD = "discard"  # 顯式丟棄草稿
_CONFIRM_CHOICES = frozenset({CHOICE_REBIND, CHOICE_DISCARD})


class WorkspaceState(str, Enum):
    ACTIVE = "active"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 快照衝突（對齊 §9 狀態）
    COMMITTED = "committed"
    DISCARDED = "discarded"


@dataclass
class EphemeralWorkspace:
    """單一任務的敘事草稿區。草稿只在記憶體；落庫必經顯式 writer。"""

    workspace_id: str
    task_id: str
    snapshot_id: str            # 關聯的 L0 圖譜快照
    state: WorkspaceState = WorkspaceState.ACTIVE
    drafts: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "task_id": self.task_id,
            "snapshot_id": self.snapshot_id,
            "state": self.state.value,
            "draft_keys": sorted(self.drafts.keys()),
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class WorkspaceVerdict:
    ok: bool
    error_code: str = ""
    workspace: EphemeralWorkspace | None = None


def _default_persist_path() -> Path:
    return Path(os.getenv("EVOL_LINKIN_DATA_DIR", "data/linkin")) / "narrative_workspaces.json"


class WorkspaceRegistry:
    """工作區註冊表（草稿持久化至磁碟；commit 仍須顯式呼叫）。"""

    def __init__(self, persist_path: Path | None = None) -> None:
        self._persist_path = persist_path or _default_persist_path()
        self._by_id: dict[str, EphemeralWorkspace] = {}
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        path = self._persist_path
        if not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows = raw.get("workspaces") if isinstance(raw, dict) else None
            if not isinstance(rows, list):
                return
            for item in rows:
                if not isinstance(item, dict):
                    continue
                ws_id = str(item.get("workspace_id") or "").strip()
                if not ws_id:
                    continue
                state_raw = str(item.get("state") or WorkspaceState.ACTIVE.value)
                try:
                    state = WorkspaceState(state_raw)
                except ValueError:
                    state = WorkspaceState.ACTIVE
                drafts = item.get("drafts")
                self._by_id[ws_id] = EphemeralWorkspace(
                    workspace_id=ws_id,
                    task_id=str(item.get("task_id") or ""),
                    snapshot_id=str(item.get("snapshot_id") or ""),
                    state=state,
                    drafts=dict(drafts) if isinstance(drafts, dict) else {},
                    created_at=float(item.get("created_at") or time.time()),
                )
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return

    def _persist(self) -> None:
        path = self._persist_path
        rows = [
            {
                "workspace_id": ws.workspace_id,
                "task_id": ws.task_id,
                "snapshot_id": ws.snapshot_id,
                "state": ws.state.value,
                "drafts": ws.drafts,
                "created_at": ws.created_at,
            }
            for ws in self._by_id.values()
            if ws.state in (WorkspaceState.ACTIVE, WorkspaceState.AWAITING_CONFIRMATION)
        ]
        payload = {"workspaces": rows, "saved_at": time.time()}
        with _persist_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def clear_persistence(self) -> None:
        """測試用：刪除磁碟草稿。"""
        with _persist_lock:
            if self._persist_path.exists():
                self._persist_path.unlink()
        self._by_id.clear()

    # ── 生命週期 ─────────────────────────────────────────────
    def begin(self, task_id: str, snapshot_id: str) -> EphemeralWorkspace:
        ws = EphemeralWorkspace(
            workspace_id=f"ws-{uuid.uuid4().hex[:10]}",
            task_id=task_id,
            snapshot_id=snapshot_id,
        )
        self._by_id[ws.workspace_id] = ws
        self._persist()
        return ws

    def get(self, workspace_id: str) -> EphemeralWorkspace | None:
        return self._by_id.get(workspace_id)

    def list_for_task(
        self,
        task_id: str = "",
        *,
        include_terminal: bool = False,
    ) -> list[EphemeralWorkspace]:
        """列舉工作區；預設略過已提交／已丟棄。"""
        rows: list[EphemeralWorkspace] = []
        for ws in self._by_id.values():
            if task_id and ws.task_id != task_id:
                continue
            if not include_terminal and ws.state in (
                WorkspaceState.COMMITTED,
                WorkspaceState.DISCARDED,
            ):
                continue
            rows.append(ws)
        rows.sort(key=lambda item: item.created_at, reverse=True)
        return rows

    def end_task(self, task_id: str) -> int:
        """任務結束＝生命週期上限：所有未提交草稿自動丟棄（§4.7）。"""
        count = 0
        for ws in self._by_id.values():
            if ws.task_id == task_id and ws.state in (
                WorkspaceState.ACTIVE,
                WorkspaceState.AWAITING_CONFIRMATION,
            ):
                ws.state = WorkspaceState.DISCARDED
                count += 1
        if count:
            self._persist()
        return count

    # ── 草稿（記憶體，不落地） ────────────────────────────────
    def write_draft(self, workspace_id: str, key: str, value: Any) -> WorkspaceVerdict:
        ws = self._by_id.get(workspace_id)
        if ws is None:
            return WorkspaceVerdict(False, ERR_WORKSPACE_UNKNOWN)
        if ws.state is not WorkspaceState.ACTIVE:
            return WorkspaceVerdict(False, ERR_WORKSPACE_NOT_ACTIVE, ws)
        ws.drafts[key] = value
        self._persist()
        return WorkspaceVerdict(True, workspace=ws)

    # ── 落庫（顯式寫入 API；writer 由呼叫方注入） ─────────────
    def commit(
        self,
        workspace_id: str,
        writer: Callable[[dict[str, Any]], Any],
    ) -> WorkspaceVerdict:
        """把草稿交給顯式寫入 API（``/linkin/*`` 或模組閘道）。

        契約：本方法**不接受**圖譜／store 物件，只接受 writer callable——
        杜絕「敘事核心私自改圖譜」的路徑。
        """
        ws = self._by_id.get(workspace_id)
        if ws is None:
            return WorkspaceVerdict(False, ERR_WORKSPACE_UNKNOWN)
        if ws.state is WorkspaceState.AWAITING_CONFIRMATION:
            return WorkspaceVerdict(False, ERR_SNAPSHOT_UNRESOLVED, ws)
        if ws.state is not WorkspaceState.ACTIVE:
            return WorkspaceVerdict(False, ERR_WORKSPACE_NOT_ACTIVE, ws)
        if not callable(writer):
            return WorkspaceVerdict(False, ERR_CONFIRM_CHOICE_INVALID, ws)
        writer(dict(ws.drafts))
        ws.state = WorkspaceState.COMMITTED
        self._persist()
        return WorkspaceVerdict(True, workspace=ws)

    # ── L0 刷新衝突（§4.7 預設保留成果） ──────────────────────
    def on_l0_refresh(self, new_snapshot_id: str) -> list[str]:
        """快照變更：受影響工作區**預設**進入 awaiting_confirmation（不丟棄）。"""
        affected: list[str] = []
        for ws in self._by_id.values():
            if ws.state is WorkspaceState.ACTIVE and ws.snapshot_id != new_snapshot_id:
                ws.state = WorkspaceState.AWAITING_CONFIRMATION
                affected.append(ws.workspace_id)
        if affected:
            self._persist()
        return affected

    def confirm(
        self,
        workspace_id: str,
        choice: str,
        *,
        new_snapshot_id: str = "",
    ) -> WorkspaceVerdict:
        """用戶顯式確認：``rebind``（換綁新快照，保留草稿）或 ``discard``。"""
        ws = self._by_id.get(workspace_id)
        if ws is None:
            return WorkspaceVerdict(False, ERR_WORKSPACE_UNKNOWN)
        if choice not in _CONFIRM_CHOICES:
            return WorkspaceVerdict(False, ERR_CONFIRM_CHOICE_INVALID, ws)
        if ws.state is not WorkspaceState.AWAITING_CONFIRMATION:
            return WorkspaceVerdict(False, ERR_WORKSPACE_NOT_ACTIVE, ws)
        if choice == CHOICE_DISCARD:
            ws.state = WorkspaceState.DISCARDED
            ws.drafts.clear()
        else:
            ws.snapshot_id = new_snapshot_id or ws.snapshot_id
            ws.state = WorkspaceState.ACTIVE
        self._persist()
        return WorkspaceVerdict(True, workspace=ws)


__all__ = [
    "CHOICE_DISCARD",
    "CHOICE_REBIND",
    "ERR_CONFIRM_CHOICE_INVALID",
    "ERR_SNAPSHOT_UNRESOLVED",
    "ERR_WORKSPACE_NOT_ACTIVE",
    "ERR_WORKSPACE_UNKNOWN",
    "EphemeralWorkspace",
    "WorkspaceRegistry",
    "WorkspaceState",
    "WorkspaceVerdict",
]
