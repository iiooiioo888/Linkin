"""分層記憶傳遞（Hierarchical Context Bus）。

向下：只傳必要最少上下文（Minimum Viable Context）。
向上：質詢／請示攜帶壓縮後的決策前置摘要。
黑板：以 task_id + layer 索引寫入共享記憶。
"""

from __future__ import annotations

from typing import Any

from backend.company.raho.protocol import RahoLayer
from backend.company.state import WorkItem, WorkItemStatus

DOWN_LIMIT = 720
UP_LIMIT = 480


def compress(text: str, limit: int = DOWN_LIMIT) -> str:
    raw = (text or "").strip()
    if len(raw) <= limit:
        return raw
    return raw[: limit - 16].rstrip() + "\n…(已壓縮)"


def downward_context(item: WorkItem, dependencies: list[WorkItem]) -> str:
    """上層 → 下層：MVC，避免把整份戰役上下文灌進原子角色。"""
    if not dependencies:
        return "（無依賴上下文）"
    parts: list[str] = []
    for dep in dependencies:
        if dep.status != WorkItemStatus.DONE:
            continue
        output = ""
        if isinstance(dep.artifacts, dict):
            output = str(dep.artifacts.get("output") or "")
        spec = compress(output, DOWN_LIMIT)
        parts.append(f"【前置交付：{dep.title}】\n{spec or '（無正文）'}")
    return "\n\n".join(parts) if parts else "（無依賴上下文）"


def upward_brief(
    *,
    title: str,
    description: str,
    issues: list[str],
    options: list[str] | None = None,
) -> str:
    """下層 → 上層：決策所需前置摘要。"""
    lines = [
        f"任務：{title}",
        compress(description, 180),
        "質詢：",
        *[f"- {issue}" for issue in issues[:5]],
    ]
    if options:
        lines.append("建議方案：")
        lines.extend(f"- {opt}" for opt in options[:3])
    return compress("\n".join(lines), UP_LIMIT)


def blackboard_record(
    *,
    task_id: str,
    layer: RahoLayer | int,
    title: str,
    content: str,
    role: str = "",
) -> dict[str, Any]:
    """寫入角色記憶庫（失敗靜默）。"""
    payload = {
        "task_id": task_id,
        "layer": int(layer),
        "title": title,
        "role": role,
        "content": compress(content, 1200),
    }
    try:
        from backend.company.role_memory import get_role_memory

        memory = get_role_memory(role or "raho")
        memory.save_from_work_item(
            f"[L{int(layer)}] {title}",
            payload["content"][:1000],
            None,
            True,
        )
    except Exception:  # noqa: BLE001
        pass
    return payload
