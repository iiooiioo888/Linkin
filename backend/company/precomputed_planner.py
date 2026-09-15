"""審計／前端預算 L4/L3 規劃快照：供公司 orchestrator 單次化重用。"""

from __future__ import annotations

from typing import Any


def normalize_precomputed(raw: Any) -> dict[str, Any] | None:
    """從 task options 解析可用的預算規劃包。"""
    if not isinstance(raw, dict) or not raw:
        return None
    if raw.get("status") == "PLANNER_TRIGGERED":
        return raw
    if raw.get("status") == "PLAN_READY" and raw.get("battle_plan"):
        return {
            "status": "PLANNER_TRIGGERED",
            "commander": raw,
            "campaign": raw.get("campaign"),
        }
    commander = raw.get("commander")
    campaign = raw.get("campaign")
    if isinstance(commander, dict) and commander.get("battle_plan"):
        return raw
    if isinstance(campaign, dict) and campaign.get("nodes"):
        return raw
    return None


def campaign_snapshot(precomputed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not precomputed:
        return None
    campaign = precomputed.get("campaign")
    if not isinstance(campaign, dict):
        return None
    if campaign.get("status") == "PLANNER_DEFERRED":
        return None
    nodes = campaign.get("nodes")
    if isinstance(nodes, list) and nodes:
        return campaign
    return None


def commander_snapshot(precomputed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not precomputed:
        return None
    commander = precomputed.get("commander")
    if not isinstance(commander, dict):
        return None
    status = str(commander.get("status") or "")
    if status in ("REJECT_TO_L4", "ESCALATE_TO_USER", "PLAN_READY"):
        return commander
    return None


def precomputed_usable(precomputed: dict[str, Any] | None) -> bool:
    return campaign_snapshot(precomputed) is not None or commander_snapshot(precomputed) is not None
