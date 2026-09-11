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

# 公開方案順序（免費 → 企業）
PLAN_ORDER: tuple[str, ...] = ("free", "starter", "pro", "business", "enterprise")

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
        "docker_rate_multiplier": 2.0,
        "docker_included_hours_per_month": 0,
        "docker_description_zh": "Docker 牌價 ×2 · 無含時數",
    },
    "starter": {
        "id": "starter",
        "name": "Starter",
        "name_zh": "入門版",
        "price_usd_month": 29,
        "monthly_credits": int(os.getenv("LINKIN_PLAN_STARTER_CREDITS", "30000")),
        "concurrency": 2,
        "features": [PACK_BASE_MODELS, PACK_QUANT],
        "description_zh": "每月 3 萬積分 · 2 併發 · 量化策略",
        "docker_rate_multiplier": 1.5,
        "docker_included_hours_per_month": 5,
        "docker_description_zh": "Docker 牌價 ×1.5 · 含 5 小時/月",
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
        "docker_rate_multiplier": 1.0,
        "docker_included_hours_per_month": 20,
        "docker_description_zh": "Docker 牌價 · 含 20 小時/月",
    },
    "business": {
        "id": "business",
        "name": "Business",
        "name_zh": "商務版",
        "price_usd_month": 299,
        "monthly_credits": int(os.getenv("LINKIN_PLAN_BUSINESS_CREDITS", "500000")),
        "concurrency": 15,
        "features": [
            PACK_BASE_MODELS,
            PACK_QUANT,
            PACK_ADVANCED_MODELS,
            PACK_MINECRAFT,
            PACK_RAHO,
            PACK_OPC,
            PACK_AUDIT,
        ],
        "description_zh": "每月 50 萬積分 · 15 併發 · 審計合規 · 無跨帳共享",
        "docker_rate_multiplier": 0.8,
        "docker_included_hours_per_month": 80,
        "docker_description_zh": "Docker 牌價 ×0.8 · 含 80 小時/月",
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
        "docker_rate_multiplier": 0.5,
        "docker_included_hours_per_month": 500,
        "docker_description_zh": "Docker 牌價 ×0.5 · 含 500 小時/月",
    },
}

# 舊版別名（僅解析，不出現在公開列表）
_LEGACY_PLAN_ALIASES: dict[str, str] = {
    "team": "business",
    "lite": "starter",
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


def normalize_plan_id(plan_id: str | None) -> str:
    """將舊版或別名方案 ID 映射至現行方案。"""
    pid = (plan_id or "free").strip().lower()
    return _LEGACY_PLAN_ALIASES.get(pid, pid)


def get_plan(plan_id: str) -> dict[str, Any]:
    pid = normalize_plan_id(plan_id)
    return PLAN_DEFINITIONS.get(pid, PLAN_DEFINITIONS["free"])


def plan_has_feature(plan_id: str, feature: str) -> bool:
    plan = get_plan(plan_id)
    return feature in (plan.get("features") or [])


def list_plans_public() -> list[dict[str, Any]]:
    from backend.billing.docker_pricing import get_plan_docker_terms

    out = []
    for pid in PLAN_ORDER:
        plan = PLAN_DEFINITIONS[pid]
        docker = get_plan_docker_terms(pid)
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
                "docker": {
                    "rate_multiplier": docker["rate_multiplier"],
                    "included_hours_per_month": docker["included_hours_per_month"],
                    "description_zh": docker["description_zh"],
                },
            }
        )
    return out


def is_public_plan_id(plan_id: str) -> bool:
    return normalize_plan_id(plan_id) in PLAN_DEFINITIONS
