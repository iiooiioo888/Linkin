"""Grill 質詢處理（自 backend.services.commander 抽出）。

質詢分類、工具推斷、SOP 回覆與輪次計數。
"""

from __future__ import annotations

import re
from typing import Any

from backend.company.raho.protocol import ESCALATE_MARK, MAX_SUPERIOR_ROUNDS, GrillIssue

from .prompts import GRILL_CLARIFY, GRILL_DATA, GRILL_LOGIC, GRILL_TOOL
from .rules import KNOWN_TOOLS, TOOL_ALIASES, normalize_tools

_GRILL_DATA = re.compile(
    r"(不存在|缺失|沒有欄位|没有栏位|資料缺|data missing|欄位.?不|INPUT_REF|資料缺失)",
    re.IGNORECASE,
)


_GRILL_TOOL = re.compile(
    r"(無法用|无法用|權限|权限|工具|ffmpeg|\.mov|tool insufficient|白名單|工具不足)",
    re.IGNORECASE,
)


_GRILL_LOGIC = re.compile(
    r"(矛盾|無法同時|无法同时|保守.{0,8}激進|激進.{0,8}保守|logic conflict|容量矛盾)",
    re.IGNORECASE,
)


_GRILL_CONSTRAINT = re.compile(r"(約束衝突|迭代|token.?預算|TOKEN_BUDGET|MAX_ITERATIONS)", re.IGNORECASE)


_BLOCKER_KIND = {
    "資料缺失": GRILL_DATA,
    "工具不足": GRILL_TOOL,
    "標準模糊": GRILL_CLARIFY,
    "容量矛盾": GRILL_LOGIC,
    "約束衝突": "constraint_conflict",
}


def classify_grill(issues: list[GrillIssue] | list[str] | str) -> str:
    if isinstance(issues, str):
        text = issues
        blockers: list[str] = []
    else:
        parts = []
        blockers = []
        for item in issues:
            if isinstance(item, GrillIssue):
                parts.append(item.message)
                if item.blocker_type:
                    blockers.append(item.blocker_type)
            else:
                parts.append(str(item))
        text = "\n".join(parts)
    for blocker in blockers:
        mapped = _BLOCKER_KIND.get(blocker)
        if mapped:
            return mapped
    if _GRILL_DATA.search(text):
        return GRILL_DATA
    if _GRILL_TOOL.search(text):
        return GRILL_TOOL
    if _GRILL_LOGIC.search(text):
        return GRILL_LOGIC
    if _GRILL_CONSTRAINT.search(text):
        return "constraint_conflict"
    return GRILL_CLARIFY


def _conflict_ruling(text: str) -> str:
    """從 L2 質詢抽出衝突節點，給出「以 A 為準，B 需修正」。"""
    found: list[str] = []
    for match in re.finditer(r"(?:節點\s*)([A-Z]\d+|[A-Z])|([A-Z]\d+|[A-Z])\s*節點", text or ""):
        token = match.group(1) or match.group(2)
        if token and token not in found:
            found.append(token)
    if len(found) >= 2:
        return f"以 {found[0]} 為準，{found[1]} 需修正"
    return ""


def _requested_tool(text: str) -> str:
    raw = text or ""
    unknown = ("ffmpeg", "whisper", "opencv")
    for name in unknown:
        if name in raw.lower():
            return name
    for name in list(TOOL_ALIASES) + list(KNOWN_TOOLS):
        if name in raw:
            return TOOL_ALIASES.get(name, name)
    match = re.search(r"`([a-zA-Z0-9_]+)`", raw)
    return match.group(1) if match else ""


def infer_tools_from_text(text: str) -> list[str]:
    """從質詢文推斷可重發的已知工具（空白名單時用）。"""
    raw = (text or "").lower()
    found: list[str] = []

    def add(name: str) -> None:
        if name not in found:
            found.append(name)

    if re.search(r"pdf|csv|檔案|文件|讀檔|read_file|\.txt|\.md|xlsx|寫入", raw):
        add("read_file")
    if re.search(r"url|http|爬取|擷取|下載|web_fetch|官網|頁面", raw):
        add("web_fetch")
    if re.search(r"搜尋|search|web_search", raw):
        add("web_search")
    if re.search(r"解析|python|統計|計算|python_exec", raw):
        add("python_exec")
    if re.search(r"摘要|分析|text_analyzer|語意", raw):
        add("text_analyzer")
    if re.search(r"json|json_formatter|schema", raw):
        add("json_formatter")
    if re.search(r"記憶|memory|read_memory", raw):
        add("read_memory")
    # ALLOWED_TOOLS 為空但任務需要工具：給最小可用組合
    if not found and re.search(r"allowed_tools|工具白名單|工具不足|需要讀檔|擷取|解析", raw):
        found.extend(["read_file", "web_fetch", "json_formatter"])
    return normalize_tools(found)


def fill_allowed_tools(text: str, current: list[str] | None = None) -> list[str]:
    """空白名單時依任務描述推斷；已有名單則原樣正規化。"""
    raw = [str(t).strip() for t in (current or []) if str(t).strip()]
    if raw:
        return normalize_tools(raw)
    inferred = infer_tools_from_text(text)
    return inferred if inferred else normalize_tools([])


def respond_to_grill(
    issues: list[GrillIssue] | list[str] | str,
    *,
    allowed_tools: list[str] | None = None,
    alternative_fields: list[str] | None = None,
    priority_ruling: str = "",
    rounds_used: int = 0,
) -> dict[str, Any]:
    """L2 → L3 Grill SOP。3 輪無解即 [ESCALATE]。"""
    if isinstance(issues, str):
        messages = [issues]
        issue_list: list[Any] = [issues]
    else:
        issue_list = list(issues)
        messages = [
            item.message if isinstance(item, GrillIssue) else str(item) for item in issue_list
        ]
    text = "\n".join(messages)
    kind = classify_grill(issues)
    escalate_forced = rounds_used >= MAX_SUPERIOR_ROUNDS

    def _try_reissue_tools() -> dict[str, Any] | None:
        """空白名單／已知工具缺口：優先重發，避免無謂上交 L5。"""
        if escalate_forced:
            return None
        has_tool_blocker = False
        for item in issue_list:
            if isinstance(item, GrillIssue) and (
                item.blocker_type == "工具不足" or item.kind == "tool"
            ):
                has_tool_blocker = True
                break
        if not has_tool_blocker and kind != GRILL_TOOL:
            if not re.search(r"allowed_tools|工具白名單|工具不足|ALLOWED_TOOLS", text, re.IGNORECASE):
                return None
        requested = _requested_tool(text)
        if requested and requested not in KNOWN_TOOLS:
            return None
        allow = normalize_tools(
            list(allowed_tools or []) + ([requested] if requested in KNOWN_TOOLS else [])
        )
        if requested in KNOWN_TOOLS:
            return {
                "action": "resolve",
                "kind": GRILL_TOOL,
                "escalate": False,
                "escalate_to": "",
                "reply": f"白名單已重發，僅允許：{', '.join(allow)}。用 {requested} 重試一次。",
                "reissued_tools": allow,
                "rounds_used": rounds_used + 1,
            }
        inferred = infer_tools_from_text(text)
        if not inferred:
            return None
        allow = normalize_tools(list(allow) + inferred)
        return {
            "action": "resolve",
            "kind": GRILL_TOOL,
            "escalate": False,
            "escalate_to": "",
            "reply": f"白名單已重發，僅允許：{', '.join(allow)}。依任務需求重試一次。",
            "reissued_tools": allow,
            "rounds_used": rounds_used + 1,
        }

    # 工具缺口可本地修復時，即使同時有資料缺失也先重發工具（下一輪再處理資料）
    tool_fix = _try_reissue_tools()
    if tool_fix is not None and (
        kind == GRILL_TOOL
        or not any(
            isinstance(i, GrillIssue) and i.blocker_type == "資料缺失" for i in issue_list
        )
    ):
        return tool_fix

    if kind == GRILL_CLARIFY and not escalate_forced:
        if re.search(r"高品質|品質|质量|深刻|語法", text):
            reply = (
                "『高品質』量化定義：語法錯誤 < 1 處，且每個觀點需引用至少 2 個"
                "已在 input_ref 中的來源。超出範圍的形容詞一律忽略。"
            )
        else:
            reply = (
                "量化定義：交付必須符合 output_schema；缺欄留空；"
                "禁止引入 input_ref 以外的數據；觀點需引用至少 2 個來源，語法錯誤 < 1 處。"
            )
        return {
            "action": "resolve",
            "kind": kind,
            "escalate": False,
            "escalate_to": "",
            "reply": reply,
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_DATA:
        alts = [f for f in (alternative_fields or []) if f]
        if alts and not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": f"來源缺欄時改用替代欄位：{', '.join(alts)}。取得到的值原樣輸出，缺則留空。",
                "rounds_used": rounds_used + 1,
            }
        # 混有工具缺口時一併重發，減少 L5 決策阻塞
        if tool_fix is not None:
            patched = dict(tool_fix)
            patched["reply"] = (
                f"{ESCALATE_MARK} 資料源缺失，L2 已暫停。請 L4 補充替代數據源。"
                f"同時已重發工具：{', '.join(tool_fix.get('reissued_tools') or [])}。"
                f"原文：{text[:140]}"
            )
            patched["action"] = "escalate"
            patched["escalate"] = True
            patched["escalate_to"] = "L4"
            patched["kind"] = kind
            return patched
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 資料源缺失，L2 已暫停。請 L4 補充替代數據源。原文：{text[:180]}",
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_TOOL:
        if tool_fix is not None:
            return tool_fix
        requested = _requested_tool(text)
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L5",
            "reply": (
                f"{ESCALATE_MARK} 基礎設施缺失：系統無「{requested or '所需工具'}」。"
                "該節點標記為不可執行，交 L5 決定是否安裝新工具。"
            ),
            "infrastructure_missing": requested or "unknown",
            "rounds_used": rounds_used + 1,
        }

    if kind == GRILL_LOGIC:
        ruling = (priority_ruling or "").strip() or _conflict_ruling(text)
        if ruling and not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": f"優先級裁定：{ruling}。衝突節點一律服從此裁定。",
                "priority_ruling": ruling,
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 節點目標互斥，L3 無法裁定。請 L4 規劃官給優先序。{text[:160]}",
            "rounds_used": rounds_used + 1,
        }

    if kind == "constraint_conflict":
        if not escalate_forced:
            return {
                "action": "resolve",
                "kind": kind,
                "escalate": False,
                "escalate_to": "",
                "reply": "約束已放寬：max_iterations 至少 2，token_budget 至少 400。請重新執行戰前檢查後再動手。",
                "reissued_budget": {"max_iterations": 2, "token_budget": 400},
                "rounds_used": rounds_used + 1,
            }
        return {
            "action": "escalate",
            "kind": kind,
            "escalate": True,
            "escalate_to": "L4",
            "reply": f"{ESCALATE_MARK} 資源約束衝突，L3 無法再放寬。請 L4 重核預算。{text[:160]}",
            "rounds_used": rounds_used + 1,
        }

    return {
        "action": "escalate",
        "kind": kind,
        "escalate": True,
        "escalate_to": "L4",
        "reply": f"{ESCALATE_MARK} 已滿 {MAX_SUPERIOR_ROUNDS} 輪仍未解，上交。{text[:160]}",
        "rounds_used": rounds_used + 1,
    }


def increment_grill_round(item_id: str) -> int:
    from backend.company.raho.store import STORE

    return STORE.bump_grill_round(item_id)


def grill_rounds(item_id: str) -> int:
    from backend.company.raho.store import STORE

    return STORE.grill_round(item_id)
