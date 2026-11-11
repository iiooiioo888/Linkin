"""規則引擎（自 backend.services.commander 抽出）。

受詞／排除項／動詞數／序列深度／工具正規化與門票檢查。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from .templates import CRAWL_TEMPLATES, TEMPLATE_HINTS, TEMPLATE_META
from .ticket import _as_list, estimate_tokens, hours_until_deadline

MAX_L2_PROMPT_TOKENS = 200


MAX_SRP_VERBS = 3


RUSH_DEADLINE_HOURS = 48


PLACEHOLDER_EXCLUSIONS = (
    "未明示絕對排除項",
    "planner 不得自行擴",
    "未明示",
)


VAGUE_ACTIONS = re.compile(
    r"^(處理數據|處理資料|做一下|處理|優化|分析|看看|弄一下|搞一下|"
    r"做點事|處理一下|優化數據|分析數據)$"
)


ACTION_VERBS = re.compile(
    r"(爬取|擷取|提取|撰寫|寫入|分析|融合|比對|計算|審查|整合|"
    r"下載|解析|轉換|驗證|部署|測試|設計|實作|整理|彙總|彙整|"
    r"讀取|發送|訂閱|生成|產出|收集|蒐集|抓取|匯出|預警|調價|"
    r"壓縮|盯盤|審核|追蹤|孵化|拆解|核發|"
    r"fetch|extract|write|analyze|compare|compute|review|scrape)",
    re.IGNORECASE,
)


HUGE_SCALE = re.compile(
    r"(100\s*萬|一百萬|[5-9]\d{5,}|\d{7,})\s*(個|筆|頁|網頁|网页|URL|網站|网站)?",
    re.IGNORECASE,
)


KNOWN_TOOLS = frozenset(
    {
        "web_search",
        "web_fetch",
        "read_file",
        "python_exec",
        "json_formatter",
        "read_memory",
        "text_analyzer",
        "docker_ps",
        "docker_logs",
        "docker_stats",
        "docker_health",
    }
)


FORBIDDEN_TOOLS = frozenset({"*", "all", "all_tools", "全部", "所有工具", "any"})


TOOL_ALIASES = {
    "web_scrape": "web_fetch",
    "fetch": "web_fetch",
    "search": "web_search",
    "python": "python_exec",
    "memory": "read_memory",
}


def has_concrete_object(action: str) -> bool:
    text = (action or "").strip()
    if len(text) < 6:
        return False
    if VAGUE_ACTIONS.match(text):
        return False
    if ACTION_VERBS.search(text) and len(re.sub(ACTION_VERBS, "", text).strip()) >= 2:
        return True
    return len(text) >= 8 and not VAGUE_ACTIONS.search(text)


def exclusions_ok(items: list[str]) -> bool:
    cleaned = [x for x in items if x and not any(p in x for p in PLACEHOLDER_EXCLUSIONS)]
    return bool(cleaned)


def count_verbs(text: str) -> int:
    return len(ACTION_VERBS.findall(text or ""))


def pick_template(description: str) -> str:
    low = (description or "").lower()
    for keys, tmpl in TEMPLATE_HINTS:
        if any(k.lower() in low for k in keys):
            return tmpl
    return "generic"


def exclusions_ban_crawl(exclusions: list[str]) -> bool:
    blob = " ".join(exclusions or [])
    return bool(re.search(r"爬蟲|爬虫|scrape|crawler|爬取", blob, re.IGNORECASE))


def remap_template(template: str, *, ban_crawl: bool) -> str:
    if ban_crawl and template in CRAWL_TEMPLATES:
        return "file_ingest"
    return template if template in TEMPLATE_META else "generic"


def serial_depth(nodes: list[dict[str, Any]]) -> int:
    """最長依賴鏈長度（含自身）。並行蒐集層深度為 1。"""
    by_id = {str(n.get("node_id")): n for n in nodes}
    memo: dict[str, int] = {}

    def depth(nid: str) -> int:
        if nid in memo:
            return memo[nid]
        node = by_id.get(nid) or {}
        deps = [str(d) for d in (node.get("depends_on") or []) if str(d) in by_id]
        memo[nid] = 1 + max((depth(d) for d in deps), default=0)
        return memo[nid]

    return max((depth(str(n.get("node_id"))) for n in nodes), default=0)


def normalize_tools(tools: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in tools or []:
        name = TOOL_ALIASES.get(str(raw).strip(), str(raw).strip())
        if not name or name in FORBIDDEN_TOOLS:
            continue
        if name not in KNOWN_TOOLS:
            continue
        if name not in out:
            out.append(name)
    if not out:
        out = ["read_memory"]
    return out


def clip_prompt(text: str, limit: int = MAX_L2_PROMPT_TOKENS) -> str:
    raw = (text or "").strip()
    if estimate_tokens(raw) <= limit:
        return raw
    lines = [ln.rstrip() for ln in raw.splitlines() if ln.strip()]
    kept: list[str] = []
    for line in lines:
        trial = "\n".join(kept + [line])
        if estimate_tokens(trial) > limit:
            break
        kept.append(line)
    if kept:
        return "\n".join(kept)
    chars = max(40, limit * 2)
    return raw[:chars].rstrip() + "…"


def validate_ticket(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    """L4 門票最後防線。缺失則拒絕拆解。"""
    goal = ticket.get("clarified_goal") or {}
    constraints = ticket.get("hard_constraints") or {}
    action = str(goal.get("core_action") or "").strip()
    deadline = str(constraints.get("deadline") or "").strip()
    exclusions = _as_list(constraints.get("absolute_exclusions"))
    hours = hours_until_deadline(deadline, now)
    defects: list[str] = []
    object_ok = has_concrete_object(action)
    excl_ok = exclusions_ok(exclusions)

    if not object_ok:
        defects.append(
            "clarified_goal.core_action 缺少具體受詞（例如「分析競品定價」而非「處理數據」）"
        )
    if not excl_ok:
        defects.append("hard_constraints.absolute_exclusions 為空，必須補充「絕對不做的事」")

    rush = hours is not None and hours < RUSH_DEADLINE_HOURS
    items = [
        {
            "id": "core_action_object",
            "label": "clarified_goal.core_action 是否包含具體受詞",
            "pass": object_ok,
        },
        {
            "id": "deadline_48h",
            "label": "hard_constraints.deadline 距離現在是否大於 48 小時",
            "pass": True,
            "rush_mode": rush,
            "hours_until_deadline": None if hours is None else round(hours, 2),
        },
        {
            "id": "exclusions_nonempty",
            "label": "hard_constraints.absolute_exclusions 是否為非空陣列",
            "pass": excl_ok,
        },
    ]
    return {
        "ok": not defects,
        "defects": defects,
        "items": items,
        "rush_mode": rush,
        "hours_until_deadline": None if hours is None else round(hours, 2),
        "core_action": action,
        "deadline": deadline,
        "exclusions": exclusions,
        "must_use_tech": _as_list(constraints.get("must_use_tech")),
        "ban_crawl": exclusions_ban_crawl(exclusions),
    }


def detect_infeasible(ticket: dict[str, Any], now: datetime | None = None) -> dict[str, Any] | None:
    """硬限制內不可能完成 → 上交 L5，禁止硬拆。"""
    if ticket.get("user_override"):
        return None
    text = json.dumps(ticket, ensure_ascii=False)
    hours = hours_until_deadline(str((ticket.get("hard_constraints") or {}).get("deadline") or ""), now)
    huge = HUGE_SCALE.search(text)
    if not huge:
        return None
    if hours is None or hours >= 72:
        return None
    sample = huge.group(0)
    return {
        "reason": "資源不足",
        "details": (
            f"N1 任務要求處理「{sample}」，但約束中僅允許使用單台 PC 且無代理池，"
            f"預估耗時遠超截止日（剩餘約 {round(hours, 1)} 小時），禁止硬拆。"
        ),
        "alternatives": [
            "方案 A：將樣本縮減至 1,000 個網頁（推薦）",
            "方案 B：開放預算購買 10 個代理服務器（成本增加 3 萬）",
        ],
    }
