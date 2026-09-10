"""OPC 执行节点 — 根据决策结果执行控制动作。

6 级闭环中的第 6 级：接收决策节点产出的优先级排序动作列表，
经安全护栏检查后写入 OPC 标签，并记录执行结果。
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# OPC 微服务基础 URL（可通过环境变量覆盖）
OPC_SERVICE_URL = os.getenv(
    "OPC_SERVICE_URL", "http://localhost:8001"
)


async def _write_opc_tags(
    entries: list[dict], reason: str = ""
) -> list[dict]:
    """通过 HTTP 调用 OPC 服务写入标签值。

    Args:
        entries: [{"tag_name": ..., "value": ...}, ...]
        reason: 操作原因（审计用）

    Returns:
        [{"tag_name": ..., "success": bool, "message": ...}, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{OPC_SERVICE_URL}/opc/write",
                json={"entries": entries, "reason": reason},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [])
    except Exception as exc:
        logger.warning("OPC 写入失败：%s", exc)
        return [
            {
                "tag_name": e["tag_name"],
                "success": False,
                "message": str(exc),
            }
            for e in entries
        ]


async def act_opc(state: dict) -> dict[str, Any]:
    """节点 A2：根据决策结果执行控制动作。

    优先使用 state.opc_decisions（决策节点产出），
    若无决策则回退到 state.opc_actions（兼容旧流程）。
    每个动作按优先级顺序执行，经 OPC 服务端安全护栏检查。
    """
    # 优先使用决策节点的产出
    decisions = state.get("opc_decisions") or []
    if decisions:
        # 按优先级排序：critical > high > medium > low
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        decisions = sorted(
            decisions,
            key=lambda d: priority_order.get(d.get("priority", "medium"), 2),
        )
        entries = [
            {"tag_name": d["tag_name"], "value": d["value"]}
            for d in decisions
        ]
    else:
        # 兼容旧流程：直接使用 opc_actions
        actions = state.get("opc_actions") or []
        if not actions:
            return {"opc_actions": []}
        entries = [
            {"tag_name": a["tag_name"], "value": a["value"]}
            for a in actions
        ]

    if not entries:
        return {"opc_actions": []}

    reason = (
        f"EvoLoop 6 级闭环自动决策"
        f"（session: {state.get('session_id', 'unknown')}）"
    )
    results = await _write_opc_tags(entries, reason=reason)

    success_count = sum(1 for r in results if r.get("success"))
    logger.info(
        "OPC 控制动作执行完成：%d/%d 成功",
        success_count,
        len(results),
    )

    return {"opc_actions": results}