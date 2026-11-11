"""DAG 與任務簡報建構（自 backend.services.commander 抽出）。

蒐集／串行節點、角色孵化與 L2 任務簡報（<200 token）。
"""

from __future__ import annotations

import re
from typing import Any

from .rules import (
    ACTION_VERBS,
    MAX_SRP_VERBS,
    clip_prompt,
    exclusions_ban_crawl,
    normalize_tools,
    pick_template,
    remap_template,
)
from .templates import CRAWL_TOOLS, TEMPLATE_META
from .ticket import _as_list


def _memory_ref(node_id: str) -> str:
    return f"shared_memory://results/{node_id}_output.json"


def _ticket_ref() -> str:
    return "shared_memory://l4/ticket.json"


def _render_l2_prompt(
    *,
    name: str,
    task: str,
    input_ref: str,
    schema: str,
    fallback: str,
    example: str = "",
    trait: str = "",
) -> str:
    persona = f"你是一名{name}" + (f"（{trait}）" if trait else "")
    example_line = f"嚴格輸出 {schema}，範例：{example}。" if example else f"嚴格輸出：{schema}。"
    body = (
        f"{persona}。你的唯一任務是：{task}。\n"
        f"輸入來源（Input Ref）：{input_ref}\n"
        f"{example_line}\n"
        f"{fallback}"
    )
    return clip_prompt(body)


def l2_task_brief(
    *,
    title: str,
    input_ref: Any = None,
    output_schema: str = "",
    success_criteria: str = "",
    allowed_tools: list[str] | None = None,
) -> str:
    """給 L2 的任務簡報：只傳指標，不傳戰役對話。必須 < 200 Token。"""
    if isinstance(input_ref, list):
        ref_line = "、".join(str(x) for x in input_ref if str(x).strip())
    else:
        ref_line = str(input_ref or _ticket_ref())
    tools = ", ".join(allowed_tools or []) or "無（純推理）"
    body = (
        f"唯一任務：{title}\n"
        f"輸入指標：{ref_line}\n"
        f"輸出：{output_schema or '依 output_schema'}\n"
        f"成功標準：{success_criteria or '符合 output_schema 且不編造'}\n"
        f"工具白名單：{tools}\n"
        "禁止繼承戰役對話。只讀 input_ref，禁止編造。"
    )
    return clip_prompt(body)


def _budget_for(template: str, rush: bool) -> tuple[int, int]:
    if template in {"data_synthesizer", "review"}:
        iters, tokens = 3, 3000
    elif template in {"code"}:
        iters, tokens = 3, 4000
    else:
        iters, tokens = 2, 2000
    if rush:
        iters = min(iters, 2)
        tokens = min(tokens, 2500)
    return iters, tokens


def _split_if_too_many_verbs(description: str) -> list[str]:
    verbs = ACTION_VERBS.findall(description)
    if len(verbs) <= MAX_SRP_VERBS:
        return [description]
    parts = ACTION_VERBS.split(description)
    chunks: list[str] = []
    found = ACTION_VERBS.finditer(description)
    marks = list(found)
    if not marks:
        return [description]
    for i, match in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(description)
        chunk = description[match.start() : end].strip(" ，,。；;與並和")
        if chunk:
            chunks.append(chunk)
    return chunks or [description]


def _gather_specs(ticket: dict[str, Any], *, ban_crawl: bool) -> list[tuple[str, str]]:
    """回傳可並行的蒐集節點 (description, template)。"""
    goal = ticket.get("clarified_goal") or {}
    action = str(goal.get("core_action") or ticket.get("goal") or "執行已鎖定目標").strip()
    quantified = str(goal.get("quantified_success") or "").strip()
    blob = f"{action} {quantified}"
    pricing = bool(re.search(r"價格|訂價|定价|預警|预警|調價|调价", blob))
    pdf = bool(re.search(r"pdf|表格|第三頁", blob, re.IGNORECASE))
    social = bool(re.search(r"社群|提及|社交", blob))

    if pdf:
        return [("提取指定 PDF 頁面的表格", "pdf_extractor")]
    if ban_crawl and pricing:
        return [
            ("從核准來源擷取競品價格表", "file_ingest"),
            ("核對備援價格或內部清單", "file_ingest"),
        ]
    if pricing:
        return [
            ("爬取競品官網最新價格", "web_scraper"),
            ("爬取競品社群媒體提及數", "social_listener"),
        ]
    if social:
        return [("蒐集指定來源的社群提及數", "social_listener")]
    return [(f"擷取「{action}」所需的原始輸入", "generic")]


def _rule_nodes(ticket: dict[str, Any], *, rush: bool) -> list[dict[str, Any]]:
    goal = ticket.get("clarified_goal") or {}
    action = str(goal.get("core_action") or ticket.get("goal") or "執行已鎖定目標").strip()
    quantified = str(goal.get("quantified_success") or "").strip()
    audience = str(goal.get("target_audience") or "").strip()
    exclusions = _as_list((ticket.get("hard_constraints") or {}).get("absolute_exclusions"))
    ban_crawl = exclusions_ban_crawl(exclusions)
    deliverable = "交付物"
    if re.search(r"Excel|報表|报表", quantified, re.IGNORECASE):
        deliverable = "預警摘要（Excel 列）"
    elif re.search(r"Prototype|原型", quantified, re.IGNORECASE):
        deliverable = "可點擊原型說明"
    elif re.search(r"JSON", quantified, re.IGNORECASE):
        deliverable = "JSON 結果"

    gathers = _gather_specs(ticket, ban_crawl=ban_crawl)
    nodes: list[dict[str, Any]] = []
    idx = 1
    gather_ids: list[str] = []
    for desc, tmpl in gathers:
        for piece in _split_if_too_many_verbs(desc):
            node_id = f"N{idx}"
            nodes.append(
                {
                    "node_id": node_id,
                    "description": piece,
                    "depends_on": [],
                    "assigned_role_template": remap_template(tmpl or pick_template(piece), ban_crawl=ban_crawl),
                    "parallel_ok": True,
                }
            )
            gather_ids.append(node_id)
            idx += 1

    analyze = f"比對前序 JSON 與量化標準：{(quantified or action)[:36]}"
    write = f"撰寫{deliverable}給{audience or '發起人'}"[:72]
    if rush:
        serials = [f"融合前序產出，僅輸出{deliverable}與威脅等級"]
    else:
        serials = [analyze, write]

    parent_ids = list(gather_ids)
    for desc in serials:
        for piece in _split_if_too_many_verbs(desc):
            node_id = f"N{idx}"
            tmpl = remap_template(pick_template(piece), ban_crawl=ban_crawl)
            if tmpl in {"generic", "file_ingest"}:
                tmpl = "copy" if "撰寫" in piece or "撰写" in piece else "data_synthesizer"
            nodes.append(
                {
                    "node_id": node_id,
                    "description": piece,
                    "depends_on": list(parent_ids),
                    "assigned_role_template": tmpl,
                    "parallel_ok": False,
                }
            )
            parent_ids = [node_id]
            idx += 1
    return nodes


def _tools_for(template: str, meta: dict[str, str], ticket: dict[str, Any] | None) -> list[str]:
    tools = normalize_tools([t.strip() for t in str(meta.get("tools") or "").split(",") if t.strip()])
    constraints = (ticket or {}).get("hard_constraints") or {}
    exclusions = _as_list(constraints.get("absolute_exclusions"))
    if exclusions_ban_crawl(exclusions):
        tools = [t for t in tools if t not in CRAWL_TOOLS]
    tech = " ".join(_as_list(constraints.get("must_use_tech"))).lower()
    if "python" in tech and template in {"pdf_extractor", "code", "file_ingest"} and "python_exec" not in tools:
        tools.append("python_exec")
        tools = normalize_tools(tools)
    return tools or ["read_memory"]


def _root_input_ref(template: str, meta: dict[str, str]) -> Any:
    hint = str(meta.get("input_hint") or "").strip()
    if hint:
        return f"shared_memory://user_uploaded/{hint}"
    if template == "file_ingest":
        return "shared_memory://user_uploaded/price_source.csv"
    return _ticket_ref()


def _incubate(
    nodes: list[dict[str, Any]],
    *,
    rush: bool,
    ticket: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    instances: list[dict[str, Any]] = []
    ban_crawl = exclusions_ban_crawl(
        _as_list(((ticket or {}).get("hard_constraints") or {}).get("absolute_exclusions"))
    )
    for node in nodes:
        raw_tmpl = node.get("assigned_role_template") or "generic"
        tmpl = remap_template(str(raw_tmpl), ban_crawl=ban_crawl)
        node["assigned_role_template"] = tmpl
        meta = TEMPLATE_META.get(tmpl, TEMPLATE_META["generic"])
        deps = [str(d) for d in (node.get("depends_on") or [])]
        if deps:
            refs = [_memory_ref(dep) for dep in deps]
            input_ref: Any = refs if len(refs) > 1 else refs[0]
            input_label = "、".join(refs)
        else:
            input_ref = _root_input_ref(tmpl, meta)
            input_label = str(input_ref)
        tools = _tools_for(tmpl, meta, ticket)
        iters, tokens = _budget_for(tmpl, rush)
        prompt = _render_l2_prompt(
            name=meta["name"],
            task=str(node["description"]),
            input_ref=input_label,
            schema=meta["schema"],
            fallback=meta["fallback"],
            example=str(meta.get("example") or ""),
            trait=str(meta.get("trait") or ""),
        )
        success = str(meta.get("success") or "").strip() or (
            f"完成「{str(node['description'])[:40]}」且符合 {meta['schema']}"
        )
        instances.append(
            {
                "instance_id": f"ROLE-{node['node_id']}",
                "node_id": node["node_id"],
                "template_id": tmpl,
                "name": meta["name"],
                "trait": str(meta.get("trait") or ""),
                "system_prompt": prompt,
                "allowed_tools": tools,
                "input_ref": input_ref,
                "output_schema": meta["schema"],
                "success_criteria": success,
                "max_iterations": iters,
                "token_budget": tokens,
                "failure_fallback": str(meta.get("fallback") or ""),
            }
        )
    return instances
