"""作戰地圖組裝（自 backend.services.commander 抽出）。

計畫組裝／淨化／YAML 輸出、LLM 拆解與不可行上交。
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from backend.company.raho.protocol import LAYER_LABELS, RahoLayer

from .planner import _incubate, _rule_nodes, _split_if_too_many_verbs
from .prompts import STATUS_ESCALATE_USER, STATUS_PLAN_READY, STATUS_REJECT_L4, SYSTEM_PROMPT
from .rules import (
    detect_infeasible,
    exclusions_ban_crawl,
    pick_template,
    remap_template,
    serial_depth,
    validate_ticket,
)
from .templates import TEMPLATE_META
from .ticket import _as_list, extract_ticket, ticket_hash

logger = logging.getLogger(__name__)


DEFAULT_MAX_PARALLEL = 5


DEFAULT_TIMEOUT_MINUTES = 120


DEFAULT_MODEL = "gpt-5.6-luna"


def _dump_yaml(data: Any, indent: int = 0) -> list[str]:
    space = "  " * indent
    if isinstance(data, dict):
        if not data:
            return [f"{space}{{}}"]
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{space}{key}:")
                lines.extend(_dump_yaml(value, indent + 1))
            elif isinstance(value, str) and ("\n" in value or len(value) > 88):
                lines.append(f"{space}{key}: |")
                for row in value.splitlines() or [""]:
                    lines.append(f"{space}  {row}")
            elif isinstance(value, bool):
                lines.append(f"{space}{key}: {'true' if value else 'false'}")
            elif value is None:
                lines.append(f"{space}{key}: null")
            elif isinstance(value, (int, float)):
                lines.append(f"{space}{key}: {value}")
            else:
                text = str(value).replace('"', '\\"')
                if re.search(r"[:#\[\]{}&*!|>%@`]", text) or text == "":
                    lines.append(f'{space}{key}: "{text}"')
                else:
                    lines.append(f"{space}{key}: {text}")
        return lines
    if isinstance(data, list):
        if not data:
            return [f"{space}[]"]
        lines = []
        for item in data:
            if isinstance(item, (dict, list)):
                lines.append(f"{space}-")
                lines.extend(_dump_yaml(item, indent + 1))
            else:
                text = str(item).replace('"', '\\"')
                lines.append(f'{space}- "{text}"' if re.search(r"[:#]", text) else f"{space}- {text}")
        return lines
    return [f"{space}{data}"]


def battle_plan_to_yaml(plan: dict[str, Any]) -> str:
    """人類可讀的作戰手冊：區塊註解 + 機器可解析 YAML。"""
    slim = {
        k: v
        for k, v in (plan or {}).items()
        if k not in {"reasoning", "serial_depth", "parallel_roots", "rush_mode"}
    }
    raw = "\n".join(_dump_yaml({"battle_plan": slim})) + "\n"
    raw = raw.replace("  global_settings:", "  # 全局執行策略\n  global_settings:", 1)
    raw = raw.replace("  dag_nodes:", "  # 節點拓撲 (DAG)\n  dag_nodes:", 1)
    raw = raw.replace(
        "  atomic_role_instances:",
        "  # L2 原子角色的具體「孵化清單」 (每個節點對應一個角色)\n  atomic_role_instances:",
        1,
    )
    return "# L3 戰術指揮官產出之物\n" + raw


def _new_plan_id(now: datetime | None = None) -> str:
    clock = now or datetime.now(timezone.utc).astimezone()
    return f"PLAN-{clock.strftime('%Y%m%d-%H%M%S')}"


def _assemble_plan(
    ticket: dict[str, Any],
    nodes: list[dict[str, Any]],
    *,
    rush: bool,
    now: datetime | None = None,
) -> dict[str, Any]:
    instances = _incubate(nodes, rush=rush, ticket=ticket)
    return {
        "plan_id": _new_plan_id(now),
        "based_on_l4_json": f"L4-JSON-HASH-{ticket_hash(ticket)}",
        "rush_mode": rush,
        "global_settings": {
            "default_model": DEFAULT_MODEL,
            "max_parallel_workers": 3 if rush else DEFAULT_MAX_PARALLEL,
            "global_timeout_minutes": 45 if rush else DEFAULT_TIMEOUT_MINUTES,
        },
        "dag_nodes": nodes,
        "atomic_role_instances": instances,
        "serial_depth": serial_depth(nodes),
        "parallel_roots": [n["node_id"] for n in nodes if not n.get("depends_on")],
        "reasoning": _build_reasoning(ticket, nodes, instances, rush=rush),
    }


def _build_reasoning(
    ticket: dict[str, Any],
    nodes: list[dict[str, Any]],
    instances: list[dict[str, Any]],
    *,
    rush: bool,
) -> dict[str, Any]:
    """拆解四步法的可檢查痕跡（內部 CoT，不灌給 L2）。"""
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    risks = ticket.get("risk_register") or {}
    risk_list = risks.get("identified_risks") if isinstance(risks, dict) else []
    by_node = {str(row.get("node_id")): row for row in instances}
    return {
        "parsing": {
            "core_action": str(goal.get("core_action") or ""),
            "quantified_success": str(goal.get("quantified_success") or ""),
            "deadline": str(constraints.get("deadline") or ""),
            "absolute_exclusions": _as_list(constraints.get("absolute_exclusions")),
            "identified_risks": _as_list(risk_list),
        },
        "topology": {
            "parallel": [n["node_id"] for n in nodes if not n.get("depends_on")],
            "sequential": [n["node_id"] for n in nodes if n.get("depends_on")],
            "serial_depth": serial_depth(nodes),
            "rush_mode": rush,
        },
        "templating": [
            {
                "node_id": n["node_id"],
                "template": n.get("assigned_role_template"),
                "name": (by_node.get(n["node_id"]) or {}).get("name") or "",
                "trait": (by_node.get(n["node_id"]) or {}).get("trait") or "",
                "fallback": (by_node.get(n["node_id"]) or {}).get("failure_fallback") or "",
            }
            for n in nodes
        ],
        "budgeting": [
            {
                "instance_id": row["instance_id"],
                "max_iterations": row["max_iterations"],
                "token_budget": row["token_budget"],
            }
            for row in instances
        ],
    }


def _sanitize_plan(plan: dict[str, Any], ticket: dict[str, Any], *, rush: bool) -> dict[str, Any]:
    nodes = list(plan.get("dag_nodes") or [])
    cleaned_nodes: list[dict[str, Any]] = []
    ban_crawl = exclusions_ban_crawl(
        _as_list((ticket.get("hard_constraints") or {}).get("absolute_exclusions"))
    )
    for i, node in enumerate(nodes, start=1):
        desc = str(node.get("description") or f"原子任務 {i}")
        pieces = _split_if_too_many_verbs(desc)
        deps = [str(x) for x in (node.get("depends_on") or [])]
        tmpl = str(node.get("assigned_role_template") or pick_template(desc))
        if tmpl not in TEMPLATE_META:
            tmpl = pick_template(desc)
        tmpl = remap_template(tmpl, ban_crawl=ban_crawl)
        if len(pieces) == 1:
            cleaned_nodes.append(
                {
                    "node_id": str(node.get("node_id") or f"N{i}"),
                    "description": pieces[0],
                    "depends_on": deps,
                    "assigned_role_template": tmpl,
                    "parallel_ok": not deps,
                }
            )
        else:
            base = str(node.get("node_id") or f"N{i}")
            for j, piece in enumerate(pieces):
                nid = f"{base}{chr(ord('a') + j)}" if j else base
                piece_deps = deps if j == 0 else [cleaned_nodes[-1]["node_id"]]
                cleaned_nodes.append(
                    {
                        "node_id": nid,
                        "description": piece,
                        "depends_on": piece_deps,
                        "assigned_role_template": remap_template(pick_template(piece), ban_crawl=ban_crawl),
                        "parallel_ok": not piece_deps,
                    }
                )
    if not cleaned_nodes:
        cleaned_nodes = _rule_nodes(ticket, rush=rush)
    if rush and serial_depth(cleaned_nodes) > 2:
        roots = [n for n in cleaned_nodes if not n.get("depends_on")] or [cleaned_nodes[0]]
        last = cleaned_nodes[-1]
        last["depends_on"] = [str(n["node_id"]) for n in roots]
        last["parallel_ok"] = False
        cleaned_nodes = [*roots, last]
    assembled = _assemble_plan(ticket, cleaned_nodes, rush=rush)
    assembled["plan_id"] = str(plan.get("plan_id") or assembled["plan_id"])
    if plan.get("global_settings"):
        assembled["global_settings"].update(
            {k: v for k, v in plan["global_settings"].items() if v is not None}
        )
        assembled["global_settings"]["max_parallel_workers"] = min(
            8, max(1, int(assembled["global_settings"].get("max_parallel_workers") or DEFAULT_MAX_PARALLEL))
        )
    return assembled


def _llm_plan(ticket: dict[str, Any], *, rush: bool) -> dict[str, Any] | None:
    try:
        from backend.core.llm import call_llm, parse_json_response

        prompt = (
            "將下列 L4 戰術指令拆成原子 DAG。"
            "每個節點描述不得超過 3 個動詞；L2 system_prompt 必須 < 200 token，"
            "且含 input_ref 與 output_schema；allowed_tools 必須是白名單子集，"
            "禁止 all。獨立蒐集節點必須並行（depends_on=[]），融合／撰寫節點才串行。"
            f"極速模式={rush}（若為 true，串行深度最多 2，但可保留並行蒐集）。"
            "必須遵守 absolute_exclusions（例如禁止爬蟲則不得使用 web_fetch）。\n"
            "只輸出 JSON："
            '{"dag_nodes":[{"node_id":"N1","description":"...","depends_on":[],'
            '"assigned_role_template":"web_scraper","parallel_ok":true}]}\n\n'
            f"{json.dumps(ticket, ensure_ascii=False)}"
        )
        from backend.company.raho.l0 import inject_l0

        goal = ""
        clarified = ticket.get("clarified_goal") if isinstance(ticket.get("clarified_goal"), dict) else {}
        if clarified:
            goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "")
        raw = call_llm(
            prompt,
            system=inject_l0(SYSTEM_PROMPT, int(RahoLayer.L3_COMMANDER), goal or str(ticket)[:240]),
        )
        data = parse_json_response(raw)
        if isinstance(data, dict) and data.get("dag_nodes"):
            return data
        if isinstance(data, dict) and isinstance(data.get("battle_plan"), dict):
            return data["battle_plan"]
    except Exception as exc:
        logger.debug("L3 LLM 拆解降級為規則引擎：%s", exc)
    return None


def build_escalation(
    *,
    reason: str,
    details: str,
    alternatives: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": STATUS_ESCALATE_USER,
        "reason": reason,
        "details": details,
        "suggested_alternatives": alternatives
        or [
            "方案 A：縮小範圍後重拆（推薦）",
            "方案 B：放寬時程或預算後重拆",
        ],
        "waiting_for_user_decision": True,
        "role": "tactical_commander",
        "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
    }


def commander_llm_enabled() -> bool:
    return os.getenv("EVOL_RAHO_COMMANDER_LLM", "false").lower() in {"1", "true", "yes", "on"}


def plan_from_ticket(
    ticket: dict[str, Any] | str,
    *,
    now: datetime | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """主入口：門票 → 檢查 → 拆解 → 作戰手冊。"""
    parsed = extract_ticket(ticket) if not isinstance(ticket, dict) else extract_ticket(ticket) or ticket
    if not isinstance(parsed, dict) or parsed.get("status") != "APPROVED_FOR_PLANNING":
        return {
            "status": STATUS_REJECT_L4,
            "reason": "門票無效",
            "defects": ["缺少 status=APPROVED_FOR_PLANNING 的 L4 JSON"],
            "waiting_for_l4": True,
            "role": "tactical_commander",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        }

    check = validate_ticket(parsed, now=now)
    if not check["ok"]:
        return {
            "status": STATUS_REJECT_L4,
            "reason": "門票檢查未過",
            "defects": check["defects"],
            "checklist": check,
            "waiting_for_l4": True,
            "role": "tactical_commander",
            "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        }

    blocked = detect_infeasible(parsed, now=now)
    if blocked:
        pack = build_escalation(**blocked)
        pack["checklist"] = check
        return pack

    rush = bool(check["rush_mode"])
    if use_llm is None:
        from backend.company.raho.scorecard import should_demote

        use_llm = commander_llm_enabled()
        if should_demote("tactical_commander") or should_demote("manager"):
            use_llm = False
    llm_plan = _llm_plan(parsed, rush=rush) if use_llm else None
    if llm_plan:
        battle = _sanitize_plan(llm_plan, parsed, rush=rush)
        source = "llm"
    else:
        battle = _assemble_plan(parsed, _rule_nodes(parsed, rush=rush), rush=rush, now=now)
        source = "rule"

    yaml_text = battle_plan_to_yaml(battle)
    pack = {
        "status": STATUS_PLAN_READY,
        "role": "tactical_commander",
        "role_label": LAYER_LABELS.get(int(RahoLayer.L3_COMMANDER), "L3 戰術指揮官"),
        "rush_mode": rush,
        "checklist": check,
        "source": source,
        "battle_plan": battle,
        "battle_plan_yaml": yaml_text,
        "reasoning": battle.get("reasoning") or {},
        "node_count": len(battle.get("dag_nodes") or []),
        "serial_depth": battle.get("serial_depth"),
        "based_on_l4_json": battle.get("based_on_l4_json"),
    }
    try:
        from backend.company.raho.l0 import attach_to_plan

        goal = ""
        clarified = parsed.get("clarified_goal") if isinstance(parsed.get("clarified_goal"), dict) else {}
        if clarified:
            goal = str(clarified.get("core_action") or clarified.get("quantified_success") or "")
        attach_to_plan(pack, query=goal or str(parsed.get("clarified_goal") or "")[:240])
    except Exception:
        pass
    return pack
