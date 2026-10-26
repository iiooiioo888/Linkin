"""路由預覽。對外仍相容 resolve_execution_path 的路徑名。"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel
from linkin_core.contracts.version import RULE_PACK_VERSION

# 現行 Literal 含 opc，但工業查詢實際回 company。契約把 opc 收成 company。
LEGACY_PATH_OPC = "opc"


class RoutePolicy(str, Enum):
    auto = "auto"
    manual = "manual"
    cost_speed = "cost_speed"


class CompatibleStrategy(str, Enum):
    """含現行程式的 simple / company 覆寫。"""

    auto = "auto"
    manual = "manual"
    cost_speed = "cost_speed"
    simple = "simple"
    company = "company"


class ExecutionPathName(str, Enum):
    simple = "simple"
    company = "company"
    minecraft_ops = "minecraft_ops"


class RuleHit(str, Enum):
    manual_override = "manual_override"
    industrial = "industrial"
    linkin_complex = "linkin_complex"
    mine_multi_step = "mine_multi_step"
    mine_single_step = "mine_single_step"
    cost_speed = "cost_speed"
    company_keyword = "company_keyword"
    length = "length"
    fallback_simple = "fallback_simple"


# auto 進入後的順序。manual / simple / company 在鏈之前結束。
RULE_CHAIN: tuple[RuleHit, ...] = (
    RuleHit.industrial,
    RuleHit.linkin_complex,
    RuleHit.mine_multi_step,
    RuleHit.mine_single_step,
    RuleHit.cost_speed,
    RuleHit.company_keyword,
    RuleHit.length,
    RuleHit.fallback_simple,
)


class RoutePreviewRequest(ContractModel):
    query: str = Field(min_length=1, max_length=8000)
    strategy: CompatibleStrategy = CompatibleStrategy.auto
    manual_path: ExecutionPathName | None = None
    task_complexity: str | None = Field(default=None, max_length=32)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID)

    @model_validator(mode="after")
    def manual_needs_path(self) -> RoutePreviewRequest:
        if self.strategy == CompatibleStrategy.manual and self.manual_path is None:
            raise ValueError("manual 策略需要 manual_path")
        return self


class RouteDecision(ContractModel):
    path: ExecutionPathName
    reason: str = Field(min_length=1, max_length=300)
    rule_hit: RuleHit
    version: str = RULE_PACK_VERSION
    confidence: float | None = Field(default=None, ge=0, le=1)
    labels: list[str] = Field(default_factory=list)


def normalize_execution_path(path: str) -> ExecutionPathName:
    """opc 舊名收成 company，其餘名稱必須已是三條路徑之一。"""
    if path == LEGACY_PATH_OPC:
        return ExecutionPathName.company
    return ExecutionPathName(path)
