"""可程式化決策路由（C-LLM-002／TODO §5.2／§5.6）。

契約：
- 暫停／審計／扣預算／啟用插件／部署等**可程式化決策**一律走程式碼路徑，
  禁止交由 LLM 決定（``guard_programmatic_action``）。
- 所有短路（不進 LLM 的路由）必附**路由原因碼**，供可觀測性診斷
  （「為什麼沒走 LLM」必須可回答）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DecisionAction(str, Enum):
    """可程式化決策動作（§5.2 白名單）。這些動作永遠不進 LLM。"""

    PAUSE_TASK = "pause_task"
    REQUEST_AUDIT = "request_audit"
    DEDUCT_BUDGET = "deduct_budget"
    ENABLE_PLUGIN = "enable_plugin"
    DISABLE_PLUGIN = "disable_plugin"
    DEPLOY_ARTIFACT = "deploy_artifact"
    COMPILE_ARTIFACT = "compile_artifact"
    L0_REFRESH = "l0_refresh"


class RouteTarget(str, Enum):
    PROGRAMMATIC = "programmatic"  # 程式碼短路，不進 LLM
    LLM = "llm"                    # 需要生成，進 LLM


# ── 路由原因碼（C-LLM-002：短路決策可觀測）──
REASON_PROGRAMMATIC_ACTION = "programmatic_action"   # 白名單動作，直接程式執行
REASON_STATE_MACHINE_DENY = "state_machine_deny"     # §9 矩陣拒絕
REASON_CACHE_HIT = "cache_hit"                       # C-LLM-003 快取命中
REASON_BUDGET_EXHAUSTED = "budget_exhausted"         # 預算耗盡短路
REASON_NEEDS_GENERATION = "needs_generation"         # 需要生成 → 進 LLM

ERR_LLM_FORBIDDEN_FOR_ACTION = "ERR_PROGRAMMATIC_ACTION_VIA_LLM"


@dataclass(frozen=True)
class RouteDecision:
    """一次路由決策的可觀測記錄。"""

    target: RouteTarget
    reason_code: str
    action: str = ""
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "target": self.target.value,
            "reason_code": self.reason_code,
            "action": self.action,
            "detail": self.detail,
        }


@dataclass
class DecisionRouter:
    """決策路由器：可程式化動作短路，生成類需求進 LLM。

    ``route_log`` 保留所有決策的原因碼（可觀測，CI 可稽核）。
    """

    route_log: list[RouteDecision] = field(default_factory=list)

    def route_action(self, action: DecisionAction, *, detail: str = "") -> RouteDecision:
        """白名單動作 → 程式碼路徑，附原因碼。"""
        decision = RouteDecision(
            target=RouteTarget.PROGRAMMATIC,
            reason_code=REASON_PROGRAMMATIC_ACTION,
            action=action.value,
            detail=detail,
        )
        self.route_log.append(decision)
        logger.debug("決策短路（程式化）：%s", action.value)
        return decision

    def route_generation(self, *, reason: str = REASON_NEEDS_GENERATION, detail: str = "") -> RouteDecision:
        """需要生成的段落 → 進 LLM，原因碼同樣記錄。"""
        decision = RouteDecision(target=RouteTarget.LLM, reason_code=reason, detail=detail)
        self.route_log.append(decision)
        return decision

    def guard_programmatic_action(self, action: DecisionAction, *, via_llm: bool) -> None:
        """契約守衛：可程式化決策若試圖經 LLM 決定 → 直接拒絕。

        Raises:
            ValueError: 違反 C-LLM-002。
        """
        if via_llm:
            raise ValueError(f"{ERR_LLM_FORBIDDEN_FOR_ACTION}: {action.value} 不得交由 LLM 決定")

    def reason_codes(self) -> list[str]:
        return [d.reason_code for d in self.route_log]


# 模組級單例（測試可 monkeypatch 重置）
_default_router: DecisionRouter | None = None


def get_decision_router() -> DecisionRouter:
    global _default_router
    if _default_router is None:
        _default_router = DecisionRouter()
    return _default_router
