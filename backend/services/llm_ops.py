"""LLM 模型池運維：定時爬取目錄、主動探活、監控快照。"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from backend.core.provider_pool import (
    pool_probe_ping_enabled,
    probe_pool_health,
    public_pool,
    refresh_interval_sec,
    refresh_model_catalog,
)

logger = logging.getLogger(__name__)


def ops_enabled() -> bool:
    return os.getenv("EVOL_LLM_OPS_ENABLED", "true").lower() not in {"0", "false", "no"}


def collect_llm_ops() -> dict[str, Any]:
    return public_pool()


def _optional_ping_fn():
    if not pool_probe_ping_enabled():
        return None
    # 延遲匯入，避免循環依賴；僅在明確開啟 ping 探活時使用
    from backend.core.llm import call_llm

    return call_llm


def run_ops_once(reason: str = "schedule") -> dict[str, Any]:
    """刷新目錄後做一次主動探活，預判不可用模型並提前熔斷。"""
    from backend.core.provider_pool import pool_health_snapshot

    pool = refresh_model_catalog(reason=reason)
    try:
        probe = probe_pool_health(reason=reason, ping_fn=_optional_ping_fn())
        failover = pool.setdefault("ops", {}).setdefault("pool_failover", {})
        failover["active_probe"] = probe
        failover["models"] = pool_health_snapshot()
    except Exception:
        logger.warning("模型池主動探活失敗", exc_info=True)
    return pool


async def llm_ops_loop() -> None:
    """背景迴圈：依設定間隔刷新模型目錄並主動探活。測試時 EVOL_LLM_OPS_ENABLED=false 立即結束。"""
    if not ops_enabled():
        logger.info("LLM 運維迴圈已停用（EVOL_LLM_OPS_ENABLED）")
        return
    while ops_enabled():
        try:
            run_ops_once("schedule")
        except Exception:
            logger.warning("LLM 定時目錄檢查失敗", exc_info=True)
        await asyncio.sleep(refresh_interval_sec())
