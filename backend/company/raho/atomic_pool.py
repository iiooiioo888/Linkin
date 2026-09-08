"""原子角色池：微型模板（約 50~100 Token），任務結束即回收。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import MGP_EXECUTOR_PREAMBLE
from backend.company.state import RoleType, WorkItem


@dataclass
class AtomicTemplate:
    template_id: str
    name: str
    kpi: str
    output_spec: str
    tools: list[str] = field(default_factory=list)

    def render(self, title: str, description: str, tools: list[str] | None = None) -> str:
        allow = tools if tools is not None else self.tools
        tool_line = "、".join(allow) if allow else "無（純推理）"
        return (
            f"{MGP_EXECUTOR_PREAMBLE}\n"
            f"你是一次性原子角色「{self.name}」。生命週期內只做一件事：{title}。\n"
            f"單一 KPI：{self.kpi}\n"
            f"輸入：{description[:280]}\n"
            f"輸出規格：{self.output_spec}\n"
            f"工具白名單：{tool_line}\n"
            "完成後停止，不要擴寫範圍。"
        )


TEMPLATES: dict[str, AtomicTemplate] = {
    "research": AtomicTemplate("research", "調研員", "資訊完整且可引用", "結構化要點 + 來源"),
    "swot": AtomicTemplate("swot", "SWOT 分析員", "四象限皆有證據", "四象限表格，每格 ≤ 5 條"),
    "copy": AtomicTemplate("copy", "文案員", "可直接上線的文案", "標題 + 正文 + CTA"),
    "code": AtomicTemplate("code", "實作員", "可運行的最小交付", "完整程式碼或 diff"),
    "review": AtomicTemplate("review", "審查員", "可執行的通過／退回裁決", "分數 + 缺陷清單"),
    "plan": AtomicTemplate("plan", "規劃員", "可執行的里程碑 DAG", "節點、依賴、成敗標準"),
    "generic": AtomicTemplate("generic", "原子執行員", "符合描述的單一交付物", "依工作項描述"),
}

_ROLE_HINTS: dict[str, str] = {
    RoleType.RESEARCHER.value: "research",
    RoleType.ANALYST.value: "research",
    RoleType.CONTENT_WRITER.value: "copy",
    RoleType.COPY_EDITOR.value: "copy",
    RoleType.TECH_WRITER.value: "copy",
    RoleType.REVIEWER.value: "review",
    RoleType.MANAGER.value: "plan",
    RoleType.ARCHITECT.value: "plan",
    RoleType.DEVELOPER.value: "code",
    RoleType.BACKEND_DEV.value: "code",
    RoleType.JS_DEV.value: "code",
    RoleType.CSS_DEV.value: "code",
    RoleType.TESTER.value: "code",
}


def pick_template(item: WorkItem) -> AtomicTemplate:
    text = f"{item.title} {item.description}".lower()
    if "swot" in text:
        return TEMPLATES["swot"]
    if any(k in text for k in ("文案", "文案", "landing", "促銷", "文稿")):
        return TEMPLATES["copy"]
    if any(k in text for k in ("調研", "调研", "競品", "竞品", "研究")):
        return TEMPLATES["research"]
    role = item.assignee.value if item.assignee else ""
    return TEMPLATES.get(_ROLE_HINTS.get(role, ""), TEMPLATES["generic"])


def assemble(item: WorkItem, tools: list[str] | None = None) -> dict[str, Any]:
    """為單一工作項組裝微型角色；寫入 artifacts 供執行使用。"""
    tmpl = pick_template(item)
    prompt = tmpl.render(item.title, item.description, tools)
    card = {
        "template_id": tmpl.template_id,
        "name": tmpl.name,
        "kpi": tmpl.kpi,
        "system_prompt": prompt,
        "disposable": True,
    }
    item.artifacts["atomic_role"] = card
    return card


def recycle(item: WorkItem) -> dict[str, Any] | None:
    """任務完成後回收角色卡，保留蒸餾摘要。"""
    card = item.artifacts.pop("atomic_role", None)
    if not card:
        return None
    output = str(item.artifacts.get("output") or "")[:400]
    distilled = {
        "template_id": card.get("template_id"),
        "title": item.title,
        "kpi": card.get("kpi"),
        "output_digest": output,
    }
    item.artifacts["atomic_distill"] = distilled
    return distilled
