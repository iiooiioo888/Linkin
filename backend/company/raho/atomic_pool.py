"""原子角色池：微型模板（約 50~100 Token），任務結束即回收。

完整 System Prompt 由 `AtomicExecutorFactory` 組裝：憲法層唯讀，任務層由此填入。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.atomic_executor import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_TOKEN_BUDGET,
    AtomicExecutorFactory,
)
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
        return AtomicExecutorFactory.spawn(
            {
                "name": self.name,
                "template_id": self.template_id,
                "task_description": f"你是一次性原子角色「{self.name}」。生命週期內只做一件事：{title}。{description[:280]}",
                "success_criteria": self.kpi,
                "output_schema": self.output_spec,
                "allowed_tools": allow,
                "input_ref": description[:280] or title,
                "max_iterations": DEFAULT_MAX_ITERATIONS,
                "token_budget": DEFAULT_TOKEN_BUDGET,
            }
        )


TEMPLATES: dict[str, AtomicTemplate] = {
    "research": AtomicTemplate("research", "調研員", "資訊完整且可引用", "結構化要點 + 來源"),
    "swot": AtomicTemplate("swot", "SWOT 分析員", "四象限皆有證據", "四象限表格，每格 ≤ 5 條"),
    "copy": AtomicTemplate("copy", "文案員", "可直接上線的文案", "標題 + 正文 + CTA"),
    "code": AtomicTemplate("code", "實作員", "可運行的最小交付", "完整程式碼或 diff"),
    "review": AtomicTemplate("review", "審查員", "可執行的通過／退回裁決", "分數 + 缺陷清單"),
    "plan": AtomicTemplate("plan", "規劃員", "可執行的里程碑 DAG", "節點、依賴、成敗標準"),
    "web_scraper": AtomicTemplate(
        "web_scraper", "價格偵查員", "產出 JSON 中至少包含 5 筆有效產品", "List[Dict[str, str]]",
        tools=["web_fetch", "json_formatter"],
    ),
    "social_listener": AtomicTemplate(
        "social_listener", "社群監聽員", "每列含來源與可核對的提及數", "List[Dict[str, str]]",
        tools=["web_search", "json_formatter"],
    ),
    "pdf_extractor": AtomicTemplate(
        "pdf_extractor", "表格提取員", "表格列完整且不編造", "List[Dict[str, str]]",
        tools=["read_file", "python_exec"],
    ),
    "data_synthesizer": AtomicTemplate(
        "data_synthesizer", "商業威脅分析師", "明確包含『高/中/低』判定", "Plain Text (Max 200 chars)",
        tools=["read_memory", "text_analyzer"],
    ),
    "file_ingest": AtomicTemplate(
        "file_ingest", "核准來源擷取員", "產出 JSON 至少含有效列，且未使用爬蟲", "List[Dict[str, str]]",
        tools=["read_file", "json_formatter"],
    ),
    "generic": AtomicTemplate("generic", "原子執行員", "符合描述的單一交付物", "依工作項描述"),
}

_ROLE_HINTS: dict[str, str] = {
    RoleType.RESEARCHER.value: "research",
    RoleType.ANALYST.value: "research",
    RoleType.CONTENT_WRITER.value: "copy",
    RoleType.COPY_EDITOR.value: "copy",
    RoleType.TECH_WRITER.value: "copy",
    RoleType.REVIEWER.value: "review",
    RoleType.CONSTITUTIONAL_INSPECTOR.value: "review",
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
    if any(k in text for k in ("核准來源", "備援", "上傳清單", "price_source")):
        return TEMPLATES["file_ingest"]
    if any(k in text for k in ("價格", "官網", "url")):
        return TEMPLATES["web_scraper"]
    if any(k in text for k in ("調研", "调研", "競品", "竞品", "研究")):
        return TEMPLATES["research"]
    role = item.assignee.value if item.assignee else ""
    return TEMPLATES.get(_ROLE_HINTS.get(role, ""), TEMPLATES["generic"])


def incubate_instance(item: WorkItem, instance: dict[str, Any]) -> dict[str, Any]:
    """用 L3 作戰手冊的原子角色實例覆寫工作項。憲法層由工廠鎖定。"""
    tools = list(instance.get("allowed_tools") or [])
    tmpl = TEMPLATES.get(str(instance.get("template_id") or ""), TEMPLATES["generic"])
    task_desc = str(instance.get("system_prompt") or "").strip()
    if not task_desc:
        task_desc = f"你是一次性原子角色「{tmpl.name}」。生命週期內只做一件事：{item.title}。{item.description[:280]}"
    card = AtomicExecutorFactory.spawn_card(
        {
            "template_id": instance.get("template_id") or instance.get("instance_id") or tmpl.template_id,
            "name": instance.get("name") or instance.get("instance_id") or tmpl.name,
            "instance_id": instance.get("instance_id") or "",
            "task_description": task_desc,
            "success_criteria": instance.get("success_criteria") or tmpl.kpi,
            "output_schema": instance.get("output_schema") or tmpl.output_spec,
            "allowed_tools": tools or list(tmpl.tools),
            "input_ref": instance["input_ref"] if "input_ref" in instance else (item.description[:280] or item.title),
            "max_iterations": instance.get("max_iterations", DEFAULT_MAX_ITERATIONS),
            "token_budget": instance.get("token_budget", DEFAULT_TOKEN_BUDGET),
        }
    )
    item.artifacts["atomic_role"] = card
    item.artifacts["input_ref"] = card.get("input_ref")
    item.artifacts["allowed_tools"] = card.get("allowed_tools") or tools
    item.artifacts["task_layer"] = card.get("task_layer")
    item.artifacts["output_schema"] = card.get("output_schema")
    item.artifacts["success_criteria"] = card.get("success_criteria")
    item.artifacts["l1_signed"] = False
    if card.get("max_iterations") is not None:
        item.artifacts["max_iterations"] = card["max_iterations"]
    if card.get("token_budget") is not None:
        item.artifacts["token_budget"] = card["token_budget"]
    return card


def assemble(item: WorkItem, tools: list[str] | None = None) -> dict[str, Any]:
    """為單一工作項組裝微型角色；寫入 artifacts 供執行使用。"""
    tmpl = pick_template(item)
    allow = tools if tools is not None else list(tmpl.tools)
    if not allow:
        try:
            from backend.services.commander import fill_allowed_tools

            allow = fill_allowed_tools(f"{item.title}\n{item.description}")
        except Exception:  # noqa: BLE001
            allow = []
    card = AtomicExecutorFactory.spawn_card(
        {
            "template_id": tmpl.template_id,
            "name": tmpl.name,
            "task_description": f"你是一次性原子角色「{tmpl.name}」。生命週期內只做一件事：{item.title}。{item.description[:280]}",
            "success_criteria": tmpl.kpi,
            "output_schema": tmpl.output_spec,
            "allowed_tools": allow,
            "input_ref": item.description[:280] or item.title,
            "max_iterations": DEFAULT_MAX_ITERATIONS,
            "token_budget": DEFAULT_TOKEN_BUDGET,
        }
    )
    item.artifacts["atomic_role"] = card
    item.artifacts["task_layer"] = card.get("task_layer")
    item.artifacts["input_ref"] = card.get("input_ref")
    item.artifacts["allowed_tools"] = card.get("allowed_tools")
    item.artifacts["output_schema"] = card.get("output_schema")
    item.artifacts["success_criteria"] = card.get("success_criteria")
    item.artifacts["l1_signed"] = False
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
