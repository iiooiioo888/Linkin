"""熱馬桶圈上交：L2 → L3 → L4 → L5，逾時跳級。"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from backend.company.raho.mgp import parse_superior_reply
from backend.company.raho.protocol import (
    ESCALATE_MARK,
    MAX_SUPERIOR_ROUNDS,
    MGP_SUPERIOR_PREAMBLE,
    EscalationChoice,
    GrillIssue,
    RahoLayer,
    decision_ttl_seconds,
    mgp_enabled,
    superior_layer,
)
from backend.company.raho.scorecard import record_escalation, record_grill, record_resolution
from backend.company.raho.store import STORE, PendingDecision

logger = logging.getLogger(__name__)

L3_SYSTEM = (
    MGP_SUPERIOR_PREAMBLE
    + "你是 L3 戰術指揮官。下層原子執行者對你的指令提出質詢。嚴禁敷衍。"
    "決策樹："
    "資料缺失→先找替代欄；無替代則暫停並交 L4 補數據源；"
    "工具不足→檢查白名單，系統有工具則重發權限，無則標記基礎設施缺失並交 L5；"
    "邏輯矛盾→必須給優先級裁定，自己無法裁定則交 L4；"
    "單純確認→一輪內給量化定義（例如語法錯誤 < 1 處，觀點至少 2 個來源）。"
    f"3 輪無解必須第一行輸出 {ESCALATE_MARK}，並列 2~3 個方案。"
)

L4_SYSTEM = (
    MGP_SUPERIOR_PREAMBLE
    + "你是 L4 元規劃官。L3 無法回答下層質詢，請從戰役目標裁決。"
    f"仍無法裁決則輸出 {ESCALATE_MARK} 交由 L5 用戶。"
)


def _default_choices(issues: list[GrillIssue]) -> list[EscalationChoice]:
    return [
        EscalationChoice("assume", "標註合理假設後繼續執行", "避免停擺，事後由 Reviewer 檢查假設"),
        EscalationChoice("narrow", "縮小輸出規格，先交付最小可用版本", "保時程，犧牲完整度"),
        EscalationChoice("wait", "暫停此子任務，等待更多資料", "避免錯誤方向浪費 Token"),
    ]


def _issue_text(issues: list[GrillIssue]) -> str:
    return "\n".join(f"- {i.message}" for i in issues) or "（無細節）"


def _call_superior(system: str, prompt: str) -> str:
    from backend.core.llm import call_llm

    return call_llm(prompt, system=system)


async def _ask_layer(
    layer: RahoLayer,
    goal: str,
    title: str,
    description: str,
    issues: list[GrillIssue],
    prior: str = "",
) -> dict[str, Any]:
    system = L3_SYSTEM if layer == RahoLayer.L3_DECOMPOSER else L4_SYSTEM
    prompt = (
        f"【戰役目標】{goal}\n"
        f"【原子任務】{title}\n{description}\n\n"
        f"【下層質詢】\n{_issue_text(issues)}\n"
    )
    if prior:
        prompt += f"\n【下級無法裁決的原因】{prior}\n"
    prompt += "請裁決。"
    try:
        raw = await asyncio.to_thread(_call_superior, system, prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning("RAHO %s 裁決失敗：%s", layer.name, exc)
        return {"action": "escalate", "reply": str(exc)}
    return parse_superior_reply(raw)


async def wait_user_decision(
    *,
    run_id: str,
    item_id: str,
    question: str,
    choices: list[EscalationChoice],
    ttl: float | None = None,
) -> dict[str, Any]:
    """等待 L5 用戶裁決；逾時自動採用第一案。"""
    timeout = decision_ttl_seconds() if ttl is None else ttl
    pending = PendingDecision(
        decision_id=uuid.uuid4().hex[:12],
        run_id=run_id,
        item_id=item_id,
        layer=int(RahoLayer.L5_USER),
        question=question,
        choices=[c.to_dict() for c in choices],
        created_at=time.time(),
        ttl=timeout,
    )
    STORE.add_pending(pending)
    STORE.add_node(
        run_id,
        from_layer=int(RahoLayer.L4_PLANNER),
        to_layer=int(RahoLayer.L5_USER),
        kind="escalate",
        summary=question[:240],
        status="blocked",
        payload={"decision_id": pending.decision_id, "item_id": item_id},
    )
    if timeout <= 0:
        resolution = {
            "action": "auto",
            "choice": choices[0].key if choices else "assume",
            "reply": choices[0].label if choices else "標註假設後繼續",
            "timeout": True,
        }
        pending.resolution = resolution
        pending.event.set()
        return resolution
    try:
        await asyncio.wait_for(pending.event.wait(), timeout=timeout)
        return pending.resolution or {
            "action": "auto",
            "choice": choices[0].key,
            "reply": choices[0].label,
            "timeout": True,
        }
    except asyncio.TimeoutError:
        resolution = {
            "action": "auto",
            "choice": choices[0].key if choices else "assume",
            "reply": (choices[0].label if choices else "標註假設後繼續") + "（決策逾時自動裁決）",
            "timeout": True,
        }
        pending.resolution = resolution
        STORE.add_node(
            run_id,
            from_layer=int(RahoLayer.L5_USER),
            to_layer=int(RahoLayer.L2_EXECUTOR),
            kind="timeout",
            summary="決策逾時，熱馬桶圈跳級自動裁決",
            status="timeout",
            payload={"decision_id": pending.decision_id},
        )
        return resolution


async def resolve_grill(
    *,
    run_id: str,
    item_id: str,
    goal: str,
    title: str,
    description: str,
    issues: list[GrillIssue],
    assignee: str = "",
    choices: list[EscalationChoice] | None = None,
    superior: str = "manager",
) -> dict[str, Any]:
    """L2 質詢的熱馬桶圈：L3 → L4 → L5。

    被質詢率記在下指令的上層（預設 manager），不是執行者。
    """
    if not mgp_enabled():
        return {"action": "resolve", "reply": "MGP 已關閉，按原指令執行。", "layer": 0}

    record_grill(superior or "manager")
    from backend.services.commander import increment_grill_round, respond_to_grill

    rounds_used = increment_grill_round(item_id)
    sop = respond_to_grill(issues, rounds_used=max(0, rounds_used - 1))
    node = STORE.add_node(
        run_id,
        from_layer=int(RahoLayer.L2_EXECUTOR),
        to_layer=int(RahoLayer.L3_DECOMPOSER),
        kind="mgp",
        summary=_issue_text(issues)[:240],
        status="open",
        payload={"item_id": item_id, "issues": [i.to_dict() for i in issues], "sop": sop},
        goal=goal,
    )

    if sop.get("action") == "resolve" and sop.get("reply") and not sop.get("escalate"):
        STORE.resolve_node(run_id, node.node_id, "resolved")
        STORE.add_node(
            run_id,
            from_layer=int(RahoLayer.L3_DECOMPOSER),
            to_layer=int(RahoLayer.L2_EXECUTOR),
            kind="resolve",
            summary=str(sop["reply"])[:240],
            status="resolved",
            parent_id=node.node_id,
        )
        record_resolution(assignee or "executor", clear=True)
        return {**sop, "layer": int(RahoLayer.L3_DECOMPOSER), "node_id": node.node_id}

    current = RahoLayer.L3_DECOMPOSER
    prior = ""
    if sop.get("escalate"):
        prior = str(sop.get("reply") or "L3 SOP 無法裁決")
        current = (
            RahoLayer.L5_USER
            if sop.get("escalate_to") == "L5"
            else RahoLayer.L4_PLANNER
        )
        STORE.add_node(
            run_id,
            from_layer=int(RahoLayer.L3_DECOMPOSER),
            to_layer=int(current),
            kind="escalate",
            summary=prior[:240],
            status="escalated",
            parent_id=node.node_id,
        )
        record_escalation(assignee or "executor", to_user=current == RahoLayer.L5_USER)
    for _round in range(MAX_SUPERIOR_ROUNDS + 1):
        if current == RahoLayer.L5_USER:
            user_choices = choices if choices else _default_choices(issues)
            result = await wait_user_decision(
                run_id=run_id,
                item_id=item_id,
                question=_issue_text(issues),
                choices=user_choices,
            )
            STORE.resolve_node(run_id, node.node_id, "escalated")
            record_escalation(assignee or "executor", to_user=True)
            record_resolution("user", clear=not result.get("timeout"))
            return {**result, "layer": int(RahoLayer.L5_USER), "node_id": node.node_id}

        result = await _ask_layer(current, goal, title, description, issues, prior)
        if result.get("action") == "resolve" and result.get("reply"):
            STORE.resolve_node(run_id, node.node_id, "resolved")
            STORE.add_node(
                run_id,
                from_layer=int(current),
                to_layer=int(RahoLayer.L2_EXECUTOR),
                kind="resolve",
                summary=str(result["reply"])[:240],
                status="resolved",
                parent_id=node.node_id,
            )
            record_resolution(assignee or "executor", clear=True)
            return {**result, "layer": int(current), "node_id": node.node_id}

        prior = str(result.get("reply") or "無法裁決")
        nxt = superior_layer(current)
        STORE.add_node(
            run_id,
            from_layer=int(current),
            to_layer=int(nxt),
            kind="escalate",
            summary=prior[:240],
            status="escalated",
            parent_id=node.node_id,
        )
        record_escalation(assignee or "executor", to_user=nxt == RahoLayer.L5_USER)
        current = nxt

    return {
        "action": "resolve",
        "reply": "上層未能裁決，標註假設後繼續。",
        "layer": int(current),
        "node_id": node.node_id,
    }


def decide(decision_id: str, choice: str, note: str = "") -> dict[str, Any]:
    pending = STORE.get_pending(decision_id)
    if pending is None:
        raise KeyError(f"待決決策不存在：{decision_id}")
    labels = {c.get("key"): c.get("label") for c in pending.choices}
    resolution = {
        "action": "user",
        "choice": choice,
        "reply": note.strip() or labels.get(choice, choice),
        "timeout": False,
    }
    STORE.decide(decision_id, resolution)
    STORE.add_node(
        pending.run_id,
        from_layer=int(RahoLayer.L5_USER),
        to_layer=int(RahoLayer.L2_EXECUTOR),
        kind="user_decide",
        summary=resolution["reply"][:240],
        status="resolved",
        payload={"decision_id": decision_id, "choice": choice},
    )
    record_resolution("user", clear=True)
    return pending.to_dict()
