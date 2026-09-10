"""工作項狀態機。

管理任務分解、狀態轉換、依賴解析與看板視圖。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

from backend.company.state import (
    BudgetTier,
    Priority,
    RoleType,
    WorkItem,
    WorkItemStatus,
)

logger = logging.getLogger(__name__)

_STATUS_PROGRESS = {
    WorkItemStatus.PLANNING: 0,
    WorkItemStatus.READY: 8,
    WorkItemStatus.BLOCKED: 12,
    WorkItemStatus.EXECUTING: 55,
    WorkItemStatus.REWORK: 40,
    WorkItemStatus.IN_REVIEW: 100,
    WorkItemStatus.DONE: 100,
}

_TAG_RULES: tuple[tuple[str, str], ...] = (
    ("API", r"api|sse|endpoint|協議"),
    ("Schema", r"schema|資料結構|npc|quest"),
    ("Design", r"設計|design|架構|選型"),
    ("Database", r"資料庫|postgres|sql|schema"),
    ("Code", r"程式|code|實作|typescript|python"),
    ("Docs", r"文件|文檔|文件空間"),
    ("Research", r"調研|研究|競品"),
)


def _slug_file(title: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in "-_ " else "" for ch in (title or "").strip())
    slug = "_".join(raw.split())[:48] or "output"
    return slug


def _item_tags(item: WorkItem) -> list[str]:
    tags: list[str] = []
    artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
    raw = artifacts.get("tags")
    if isinstance(raw, list):
        tags.extend(str(t).strip()[:18] for t in raw if str(t).strip())
    blob = f"{item.title} {item.description}"
    for label, pat in _TAG_RULES:
        if label in tags:
            continue
        if re.search(pat, blob, re.IGNORECASE):
            tags.append(label)
    return tags[:4]


def _item_progress(item: WorkItem) -> int:
    artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
    raw = artifacts.get("progress")
    try:
        n = int(raw) if raw is not None else -1
        if 0 <= n <= 100:
            return n
    except (TypeError, ValueError):
        pass
    return _STATUS_PROGRESS.get(item.status, 0)


def _item_action(item: WorkItem) -> str:
    artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
    action = str(artifacts.get("current_action") or "").strip()
    if action:
        return action[:120]
    if item.status != WorkItemStatus.EXECUTING:
        return ""
    think = str(artifacts.get("thinking") or "").strip()
    if think:
        last = think.splitlines()[-1].strip()
        if last:
            return last[:120]
    return "執行中…"


def _item_files(item: WorkItem, output: str) -> list[dict[str, str]]:
    artifacts = item.artifacts if isinstance(item.artifacts, dict) else {}
    files: list[dict[str, str]] = []
    raw = artifacts.get("files")
    if isinstance(raw, list):
        for row in raw[:12]:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or row.get("name") or "").strip()
            if not path:
                continue
            files.append(
                {
                    "name": path.rsplit("/", 1)[-1],
                    "path": path,
                    "status": str(row.get("status") or "modified"),
                    "size": str(row.get("size") or f"{len(str(row.get('content') or ''))}B"),
                }
            )
    if output and not files:
        name = f"{_slug_file(item.title)}.md"
        files.append(
            {
                "name": name,
                "path": f"output/{name}",
                "status": "added" if item.status == WorkItemStatus.DONE else "modified",
                "size": f"{len(output)}B",
            }
        )
    return files


class WorkItemManager:
    """工作項生命週期管理器。

    負責：
    - 建立/分解工作項
    - 狀態轉換（含合法性檢查）
    - 依賴關係解析
    - 看板視圖
    """

    def __init__(self):
        self._items: dict[str, WorkItem] = {}

    # ── CRUD ──

    def create(
        self,
        title: str,
        description: str = "",
        assignee: RoleType | None = None,
        created_by: RoleType | None = None,
        depends_on: list[str] | None = None,
        tier: BudgetTier = BudgetTier.ROUTINE,
        priority: Priority = Priority.MEDIUM,
    ) -> WorkItem:
        """建立新工作項。"""
        item = WorkItem(
            title=title,
            description=description,
            assignee=assignee,
            created_by=created_by,
            depends_on=depends_on or [],
            tier=tier,
            priority=priority,
        )
        self._items[item.id] = item
        logger.info("工作項建立：%s [%s] → %s", item.id, item.title, item.assignee.value if item.assignee else "未指派")
        return item

    def decompose(
        self,
        parent_goal: str,
        subtasks: list[dict[str, Any]],
        assignee: RoleType | None = None,
        created_by: RoleType | None = None,
    ) -> list[WorkItem]:
        """將目標分解為多個子工作項。

        subtasks: [{"title": ..., "description": ..., "tier": ...}, ...]
        """
        items = []
        for task in subtasks:
            item = self.create(
                title=task["title"],
                description=task.get("description", ""),
                assignee=assignee or task.get("assignee"),
                created_by=created_by,
                depends_on=task.get("depends_on", []),
                tier=task.get("tier", BudgetTier.ROUTINE),
            )
            # 建立後自動設為就緒
            item.transition_to(WorkItemStatus.READY)
            items.append(item)
        logger.info("目標分解完成：%d 個子工作項", len(items))
        return items

    def get(self, item_id: str) -> WorkItem | None:
        """取得工作項。"""
        return self._items.get(item_id)

    def list_all(self) -> list[WorkItem]:
        """列出所有工作項。"""
        return list(self._items.values())

    def list_by_status(self, status: WorkItemStatus) -> list[WorkItem]:
        """依狀態篩選工作項。"""
        return [item for item in self._items.values() if item.status == status]

    def list_by_assignee(self, role: RoleType) -> list[WorkItem]:
        """依指派角色篩選工作項。"""
        return [item for item in self._items.values() if item.assignee == role]

    # ── 狀態轉換 ──

    def transition(
        self,
        item_id: str,
        new_status: WorkItemStatus,
        metadata: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        """嘗試轉換工作項狀態。

        Returns:
            (success, message): 是否成功與原因
        """
        item = self._items.get(item_id)
        if item is None:
            return False, f"工作項 {item_id} 不存在"

        if not item.transition_to(new_status):
            return False, (
                f"不允許從 {item.status.value} 轉換到 {new_status.value}"
            )

        if metadata:
            item.artifacts.update(metadata)

        logger.info(
            "工作項 %s: %s → %s", item_id, item.status.value, new_status.value
        )
        return True, f"已轉換到 {new_status.value}"

    def complete(self, item_id: str, artifacts: dict[str, Any] | None = None) -> tuple[bool, str]:
        """標記工作項為完成。"""
        if artifacts:
            item = self._items.get(item_id)
            if item:
                item.artifacts.update(artifacts)
        return self.transition(item_id, WorkItemStatus.DONE)

    def request_review(self, item_id: str) -> tuple[bool, str]:
        """提交審查。"""
        return self.transition(item_id, WorkItemStatus.IN_REVIEW)

    def request_rework(self, item_id: str, feedback: str) -> tuple[bool, str]:
        """退回修改（審查不通過）。"""
        item = self._items.get(item_id)
        if item:
            item.feedback.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "feedback": feedback,
            })
        return self.transition(item_id, WorkItemStatus.REWORK)

    def block(self, item_id: str, reason: str) -> tuple[bool, str]:
        """阻塞工作項。"""
        item = self._items.get(item_id)
        if item:
            item.artifacts["block_reason"] = reason
        return self.transition(item_id, WorkItemStatus.BLOCKED)

    def unblock(self, item_id: str) -> tuple[bool, str]:
        """解除阻塞。"""
        item = self._items.get(item_id)
        if item is None:
            return False, f"工作項 {item_id} 不存在"
        if item.status != WorkItemStatus.BLOCKED:
            return False, "工作項未處於阻塞狀態"
        # 回到就緒
        return self.transition(item_id, WorkItemStatus.READY)

    # ── 依賴解析 ──

    def get_ready_items(self) -> list[WorkItem]:
        """取得所有就緒且依賴已滿足的工作項（按優先級排序）。"""
        done_ids = {
            item.id for item in self._items.values()
            if item.status == WorkItemStatus.DONE
        }
        ready = []
        for item in self._items.values():
            if item.status != WorkItemStatus.READY:
                continue
            if all(dep in done_ids for dep in item.depends_on):
                ready.append(item)
        # 按優先級排序（數值越小越優先）
        ready.sort(key=lambda item: item.priority.value)
        return ready

    def get_blocked_by_deps(self) -> list[WorkItem]:
        """取得因依賴未滿足而無法執行的工作項。"""
        done_ids = {
            item.id for item in self._items.values()
            if item.status == WorkItemStatus.DONE
        }
        blocked = []
        for item in self._items.values():
            if item.status != WorkItemStatus.READY:
                continue
            if not all(dep in done_ids for dep in item.depends_on):
                blocked.append(item)
        return blocked

    def has_work_remaining(self) -> bool:
        """檢查是否還有未完成的工作（CANCELLED 視為終態，不再計入）。"""
        return any(
            item.status not in (WorkItemStatus.DONE, WorkItemStatus.CANCELLED)
            for item in self._items.values()
        )

    def cancel_all_pending(self, reason: str = "任務已取消") -> int:
        """把所有未完成的工作項標記為 CANCELLED（終態）。

        使用者取消任務時調用：在飛的工作項其協程結果會被丟棄，
        尚未開始／阻塞／審查中的項目直接轉終態，看板語義正確。

        Returns:
            被標記的項目數。
        """
        count = 0
        for item in list(self._items.values()):
            if item.status in (WorkItemStatus.DONE, WorkItemStatus.CANCELLED):
                continue
            if item.transition_to(WorkItemStatus.CANCELLED):
                item.artifacts["cancel_reason"] = reason
                count += 1
        if count:
            logger.info("已將 %d 個未完成工作項標記為取消：%s", count, reason)
        return count

    def is_all_done(self) -> bool:
        """檢查是否所有工作項已完成。"""
        return (
            len(self._items) > 0
            and all(
                item.status == WorkItemStatus.DONE
                for item in self._items.values()
            )
        )

    # ── 看板視圖 ──

    def get_kanban(self) -> dict[WorkItemStatus, list[dict[str, Any]]]:
        """回傳看板視圖（字典格式，適合 API 回應）。"""
        board: dict[WorkItemStatus, list[dict[str, Any]]] = {
            s: [] for s in WorkItemStatus
        }
        for item in self._items.values():
            # 產出物預覽：截斷避免回應過大
            output = str(item.artifacts.get("output", "")) if item.artifacts else ""
            thinking = str(item.artifacts.get("thinking", "")) if item.artifacts else ""
            board[item.status].append({
                "id": item.id,
                "title": item.title,
                "description": item.description[:300],
                "assignee": item.assignee.value if item.assignee else None,
                "depends_on": item.depends_on,
                "tier": item.tier.value,
                "actual_cost": round(item.actual_cost, 4),
                "feedback": [fb for fb in item.feedback[-3:]],
                "output": output[:20000],
                "thinking": thinking[:12000],
                "created_at": item.created_at,
                "updated_at": item.updated_at,
                "completed_at": item.completed_at,
                "tags": _item_tags(item),
                "progress": _item_progress(item),
                "current_action": _item_action(item),
                "files": _item_files(item, output),
                "tokens": int(item.artifacts.get("tokens") or 0) if isinstance(item.artifacts, dict) else 0,
            })
        return board

    # ── 統計 ──

    def get_stats(self) -> dict[str, Any]:
        """回傳工作項統計。"""
        total = len(self._items)
        done = sum(1 for item in self._items.values() if item.status == WorkItemStatus.DONE)
        in_review = sum(1 for item in self._items.values() if item.status == WorkItemStatus.IN_REVIEW)
        blocked = sum(1 for item in self._items.values() if item.status == WorkItemStatus.BLOCKED)
        return {
            "total": total,
            "done": done,
            "in_progress": total - done - blocked,
            "in_review": in_review,
            "blocked": blocked,
            "completion_pct": round(done / total * 100, 1) if total > 0 else 0,
        }