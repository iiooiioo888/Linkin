"""訂閱方案與功能包權益。"""

from __future__ import annotations

import os
from typing import Any

# 功能包鍵
PACK_QUANT = "quant"
PACK_OPC = "opc"
PACK_MINECRAFT = "minecraft"
PACK_ADVANCED_MODELS = "advanced_models"
PACK_AUDIT = "audit"
PACK_RAHO = "raho"
PACK_BASE_MODELS = "base_models"
PACK_BYOK = "byok"

PLAN_DEFINITIONS: dict[str, dict[str, Any]] = {
    "free": {
        "id": "free",
        "name": "Free",
        "name_zh": "免費版",
        "price_usd_month": 0,
        "monthly_credits": int(os.getenv("LINKIN_PLAN_FREE_CREDITS", "10000")),
        "concurrency": 1,
        "features": [PACK_BASE_MODELS],
        "description_zh": "每月 1 萬積分 · 1 併發 · 基礎模型",
    },
    "pro": {
        "id": "pro",
        "name": "Pro",
        "name_zh": "專業版",
        "price_usd_month": 99,
        "monthly_credits": int(os.getenv("LINKIN_PLAN_PRO_CREDITS", "100000")),
        "concurrency": 5,
        "features": [PACK_BASE_MODELS, PACK_QUANT, PACK_ADVANCED_MODELS, PACK_MINECRAFT, PACK_RAHO, PACK_OPC],
        "description_zh": "每月 10 萬積分 · 5 併發 · 量化 · RAHO · OPC",
    },
    "enterprise": {
        "id": "enterprise",
        "name": "Enterprise",
        "name_zh": "企業版",
        "price_usd_month": None,
        "monthly_credits": int(os.getenv("LINKIN_PLAN_ENTERPRISE_CREDITS", "5000000")),
        "concurrency": 100,
        "features": [
            PACK_BASE_MODELS,
            PACK_QUANT,
            PACK_ADVANCED_MODELS,
            PACK_MINECRAFT,
            PACK_RAHO,
            PACK_OPC,
            PACK_AUDIT,
            PACK_BYOK,
            "private_deploy",
            "sla",
            "sso",
        ],
        "description_zh": "客製配額 · 私有部署 · BYOK · SLA · SSO",
    },
}

FEATURE_LABELS_ZH: dict[str, str] = {
    PACK_QUANT: "量化策略包",
    PACK_OPC: "工業 OPC 包",
    PACK_MINECRAFT: "Minecraft 包",
    PACK_ADVANCED_MODELS: "進階模型",
    PACK_AUDIT: "審計與合規",
    PACK_RAHO: "RAHO 公司運行時",
    PACK_BASE_MODELS: "基礎模型",
    PACK_BYOK: "自備 API 金鑰（BYOK）",
    "private_deploy": "私有部署",
    "sla": "SLA",
    "sso": "SSO",
}


def get_plan(plan_id: str) -> dict[str, Any]:
    pid = (plan_id or "free").strip()
    if pid == "team":
        pid = "pro"
    return PLAN_DEFINITIONS.get(pid, PLAN_DEFINITIONS["free"])


def plan_has_feature(plan_id: str, feature: str) -> bool:
    plan = get_plan(plan_id)
    return feature in (plan.get("features") or [])


def list_plans_public() -> list[dict[str, Any]]:
    out = []
    for pid, plan in PLAN_DEFINITIONS.items():
        out.append(
            {
                "id": pid,
                "name": plan["name"],
                "name_zh": plan["name_zh"],
                "price_usd_month": plan["price_usd_month"],
                "monthly_credits": plan["monthly_credits"],
                "concurrency": plan["concurrency"],
                "features": [
                    {"key": f, "label_zh": FEATURE_LABELS_ZH.get(f, f)}
                    for f in plan.get("features") or []
                ],
                "description_zh": plan.get("description_zh", ""),
            }
        )
    return out
