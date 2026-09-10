"""L4 需求審計官的戰役譯製：將語意鎖定後的目標譯成戰役 DAG（里程碑，非原子任務）。

預設走規則規劃（零 LLM），避免公司運行時測試被額外模型呼叫拖垮。
`EVOL_RAHO_PLANNER_LLM=true` 時才用 LiteLLM 豐富節點標題與成敗標準。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from backend.company.raho.protocol import RahoLayer
from backend.company.raho.scorecard import planning_paradigm_hint
from backend.company.state import WorkItem


@dataclass
class CampaignNode:
    node_id: str
    title: str
    outcome: str
    success_criteria: str
    depends_on: list[str] = field(default_factory=list)
    parallel_ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "title": self.title,
            "outcome": self.outcome,
            "success_criteria": self.success_criteria,
            "depends_on": list(self.depends_on),
            "parallel_ok": self.parallel_ok,
            "layer": int(RahoLayer.L4_AUDITOR),
        }


@dataclass
class CampaignMap:
    goal: str
    nodes: list[CampaignNode] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    source: str = "rule"

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "nodes": [n.to_dict() for n in self.nodes],
            "success_criteria": list(self.success_criteria),
            "source": self.source,
            "layer": int(RahoLayer.L4_AUDITOR),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None, goal: str = "") -> CampaignMap:
        raw = data or {}
        nodes = []
        for row in raw.get("nodes") or []:
            if not isinstance(row, dict):
                continue
            nodes.append(
                CampaignNode(
                    node_id=str(row.get("node_id") or ""),
                    title=str(row.get("title") or ""),
                    outcome=str(row.get("outcome") or ""),
                    success_criteria=str(row.get("success_criteria") or ""),
                    depends_on=[str(d) for d in (row.get("depends_on") or [])],
                    parallel_ok=bool(row.get("parallel_ok")),
                )
            )
        return cls(
            goal=str(raw.get("goal") or goal),
            nodes=nodes,
            success_criteria=list(raw.get("success_criteria") or []),
            source=str(raw.get("source") or "rule"),
        )

    def brief(self, limit: int = 720) -> str:
        """給 L3 的最小可行戰役上下文。"""
        lines = ["【L4 戰役地圖】"]
        for node in self.nodes:
            deps = "、".join(node.depends_on) if node.depends_on else "無"
            lines.append(
                f"- {node.node_id} {node.title}（依賴 {deps}；成果：{node.outcome}；"
                f"成敗：{node.success_criteria}）"
            )
        if self.success_criteria:
            lines.append("【戰役成敗標準】" + "；".join(self.success_criteria[:4]))
        text = "\n".join(lines)
        return text if len(text) <= limit else text[: limit - 16].rstrip() + "\n…(已壓縮)"


_SPLIT = re.compile(r"(?:然後|接著|并且|並且|以及|再|→|->|；|;|，再|，然後)")
_QUANT = re.compile(
    r"(\d+(\.\d+)?\s*(%|％|萬|万|元|天|週|周|小時|小时)|gmv|kpi|roi|復購|复购|轉化|转化)",
    re.IGNORECASE,
)


def _planner_llm_enabled() -> bool:
    return os.getenv("EVOL_RAHO_PLANNER_LLM", "false").lower() in {"1", "true", "yes", "on"}


def _extract_criteria(goal: str) -> list[str]:
    found = [m.group(0).strip() for m in _QUANT.finditer(goal or "")]
    uniq: list[str] = []
    for item in found:
        if item not in uniq:
            uniq.append(item)
    if uniq:
        return [f"以可量化指標驗收：{', '.join(uniq[:4])}"]
    return ["交付物可被 L5 對照原始目標驗收，且不得偏離子任務範圍"]


def _keyword_milestones(goal: str) -> list[tuple[str, str, str]]:
    text = goal or ""
    if any(k in text for k in ("轉化", "转化", "復購", "复购", "促銷", "促销", "成長", "增长")):
        return [
            ("A", "市場與現況調研", "鎖定客群、基線指標與資料缺口"),
            ("B", "競品與替代方案分析", "可對照的優劣與威脅"),
            ("C", "定價與資源配置", "可執行的取捨與預算上限"),
            ("D", "促銷／成長交付物", "可上線或可評測的最小成品"),
        ]
    if any(k in text for k in ("開發", "开发", "系統", "系统", "頁面", "页面", "API", "登入")):
        return [
            ("A", "需求與驗收錨定", "範圍、不做清單、驗收數字"),
            ("B", "架構與介面契約", "模組邊界與資料規格"),
            ("C", "核心實作", "可運行的最小交付"),
            ("D", "審查與回歸", "缺陷清單清空或標註風險"),
        ]
    if any(k in text for k in ("報告", "报告", "研究", "分析", "策略")):
        return [
            ("A", "問題與資料邊界", "要回答的決策問題"),
            ("B", "證據蒐集", "可引用的來源與數據"),
            ("C", "分析與推論", "對決策有用的結論"),
            ("D", "建議與風險", "可執行建議 + 備案"),
        ]
    return [
        ("A", "釐清範圍與成敗標準", "鎖定做／不做與量化成功"),
        ("B", "蒐集前置資訊", "後續節點夠用的最小資料集"),
        ("C", "產出核心交付", "單一主交付物達規格"),
        ("D", "審查與驗收", "對照成敗標準簽核"),
    ]


def _from_clauses(goal: str) -> list[tuple[str, str, str]] | None:
    parts = [p.strip(" 。．,，") for p in _SPLIT.split(goal or "") if p and len(p.strip()) >= 4]
    if len(parts) < 2 or len(parts) > 6:
        return None
    nodes: list[tuple[str, str, str]] = []
    for i, part in enumerate(parts):
        node_id = chr(ord("A") + i)
        title = part[:24]
        nodes.append((node_id, title, f"完成「{title}」且可作為下一節點輸入"))
    return nodes


def _build_nodes(
    specs: list[tuple[str, str, str]],
    criteria: list[str],
) -> list[CampaignNode]:
    nodes: list[CampaignNode] = []
    crit = criteria[0] if criteria else "可對照目標驗收"
    for i, (node_id, title, outcome) in enumerate(specs):
        depends = [specs[i - 1][0]] if i > 0 else []
        # 第二、第四節點允許與鄰近節點並行（B∥D 這類戰役），其餘串行
        parallel_ok = i in {1, 3} and len(specs) >= 4
        if parallel_ok and i == 3:
            depends = [specs[0][0]]
        nodes.append(
            CampaignNode(
                node_id=node_id,
                title=title,
                outcome=outcome,
                success_criteria=crit,
                depends_on=depends,
                parallel_ok=parallel_ok,
            )
        )
    return nodes


def plan_campaign_rule(goal: str) -> CampaignMap:
    criteria = _extract_criteria(goal)
    specs = _from_clauses(goal) or _keyword_milestones(goal)
    return CampaignMap(
        goal=goal,
        nodes=_build_nodes(specs, criteria),
        success_criteria=criteria,
        source="rule",
    )


def _enrich_with_llm(campaign: CampaignMap) -> CampaignMap:
    from backend.core.llm import call_llm, parse_json_response

    hint = planning_paradigm_hint()
    prompt = (
        "你是 L4 需求審計官。把戰役目標譯成里程碑 DAG（不是原子任務）。"
        "只輸出 JSON：{\"nodes\":[{\"node_id\",\"title\",\"outcome\",\"success_criteria\",\"depends_on\":[]}]}\n"
        f"目標：{campaign.goal}\n"
        f"現有骨架：{[n.to_dict() for n in campaign.nodes]}\n"
        f"{hint}"
    )
    raw = call_llm(
        prompt,
        system="你只規劃里程碑與依賴，禁止拆成執行步驟。使用繁體中文。",
    )
    parsed = parse_json_response(raw)
    incoming = parsed.get("nodes") if isinstance(parsed, dict) else None
    if not isinstance(incoming, list) or not incoming:
        return campaign
    nodes: list[CampaignNode] = []
    for i, row in enumerate(incoming[:8]):
        if not isinstance(row, dict):
            continue
        node_id = str(row.get("node_id") or chr(ord("A") + i))
        deps = row.get("depends_on") or []
        if not isinstance(deps, list):
            deps = []
        nodes.append(
            CampaignNode(
                node_id=node_id,
                title=str(row.get("title") or f"里程碑 {node_id}")[:80],
                outcome=str(row.get("outcome") or "")[:200],
                success_criteria=str(row.get("success_criteria") or campaign.success_criteria[0])[:200],
                depends_on=[str(d) for d in deps][:4],
            )
        )
    if not nodes:
        return campaign
    campaign.nodes = nodes
    campaign.source = "llm"
    return campaign


def plan_campaign(goal: str) -> CampaignMap:
    """產生 L4 戰役地圖。LLM 失敗時靜默回退規則骨架。"""
    campaign = plan_campaign_rule(goal)
    if not _planner_llm_enabled():
        return campaign
    try:
        return _enrich_with_llm(campaign)
    except Exception:
        campaign.source = "rule"
        return campaign


def tag_work_items(items: list[WorkItem], campaign: CampaignMap) -> None:
    """把 L3 原子工作項掛到最近的 L4 里程碑（標題關鍵字重疊）。"""
    if not items or not campaign.nodes:
        return
    for item in items:
        text = f"{item.title} {item.description}"
        best = campaign.nodes[0]
        best_score = -1
        for node in campaign.nodes:
            score = sum(1 for token in node.title if token and token in text)
            if node.node_id in text:
                score += 3
            if score > best_score:
                best = node
                best_score = score
        item.artifacts["campaign_node"] = best.to_dict()
