"""路由預覽。對外仍相容 resolve_execution_path 的路徑名。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import Field, model_validator

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel
from linkin_core.contracts.version import RULE_PACK_VERSION, auto_input_is_mapped

# 現行 Literal 含 opc，但工業查詢實際回 company。契約把 opc 收成 company。
LEGACY_PATH_OPC = "opc"
AUTO_MAPPED_AUDIT_ACTION = "execution_strategy.auto_mapped"


class RoutePolicy(str, Enum):
    """舊的路由政策名。請求默認不在這裡，見 CompatibleStrategy。"""

    auto = "auto"
    manual = "manual"
    cost_speed = "cost_speed"


class DecisionSource(str, Enum):
    """策略是怎麼定下來的。auto 映射只會寫 fallback。"""

    user_explicit = "user_explicit"
    user_default = "user_default"
    admin_lock = "admin_lock"
    fallback = "fallback"


class CompatibleStrategy(str, Enum):
    """執行策略。契約默認 user_default，不寫死 auto。"""

    auto = "auto"
    user_default = "user_default"
    suggest_only = "suggest_only"
    manual = "manual"
    cost_speed = "cost_speed"
    simple = "simple"
    company = "company"

    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema: Any, handler: Any) -> dict[str, Any]:
        schema = handler(core_schema)
        values = list(schema.get("enum") or [item.value for item in cls])
        schema["description"] = (
            "執行策略。默認 user_default，由租戶配置注入，契約層不寫死 auto。"
            "auto 已棄用：SCHEMA_VERSION 1.x 仍接受，映射為 user_default。"
        )
        schema["anyOf"] = [
            {
                "const": value,
                "deprecated": True,
                "description": (
                    "棄用。現行 SCHEMA_VERSION 主版本內映射為 user_default，"
                    "decision_source=fallback，並記審計。不回 4xx。"
                    "最早可改成拒絕的是 SCHEMA_VERSION 2.0.0。"
                ),
            }
            if value == cls.auto.value
            else {"const": value}
            for value in values
        ]
        return schema


class ExecutionPathName(str, Enum):
    simple = "simple"
    company = "company"


class RuleHit(str, Enum):
    manual_override = "manual_override"
    industrial = "industrial"
    linkin_complex = "linkin_complex"
    cost_speed = "cost_speed"
    company_keyword = "company_keyword"
    length = "length"
    fallback_simple = "fallback_simple"


# auto 進入後的順序。manual / simple / company 在鏈之前結束。
RULE_CHAIN: tuple[RuleHit, ...] = (
    RuleHit.industrial,
    RuleHit.linkin_complex,
    RuleHit.cost_speed,
    RuleHit.company_keyword,
    RuleHit.length,
    RuleHit.fallback_simple,
)


class StrategyCompatAudit(ContractModel):
    """auto 輸入映射的審計列。契約層紀錄，不是 NATS audit.event 本體。"""

    action: str = AUTO_MAPPED_AUDIT_ACTION
    occurred_at: str = Field(min_length=20, max_length=40)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str | None = Field(default=None, pattern=TRACE_ID)
    requested_strategy: str = Field(min_length=1, max_length=32)
    strategy: CompatibleStrategy
    decision_source: DecisionSource


_STRATEGY_COMPAT_AUDITS: list[StrategyCompatAudit] = []


def reset_strategy_compat_audits() -> None:
    _STRATEGY_COMPAT_AUDITS.clear()


def strategy_compat_audits() -> tuple[StrategyCompatAudit, ...]:
    return tuple(_STRATEGY_COMPAT_AUDITS)


def _strategy_token(raw: object) -> str:
    if isinstance(raw, CompatibleStrategy):
        return raw.value
    return str(raw).strip()


def apply_strategy_compat(data: Any) -> Any:
    """缺省改 user_default。auto 在兼容窗口內映射，不在這裡回 4xx。"""
    if not isinstance(data, dict):
        return data
    payload = dict(data)
    payload.pop("decision_source", None)
    payload.pop("requested_strategy", None)
    payload.pop("strategy_audit", None)
    if "strategy" not in payload:
        payload["strategy"] = CompatibleStrategy.user_default.value
        payload["decision_source"] = DecisionSource.user_default.value
        payload["requested_strategy"] = None
        return payload
    raw = payload["strategy"]
    if raw is None:
        return payload
    token = _strategy_token(raw)
    if token == CompatibleStrategy.auto.value:
        if not auto_input_is_mapped():
            raise ValueError(
                "execution_strategy auto 已超出 SCHEMA_VERSION 兼容窗口，不再映射"
            )
        payload["strategy"] = CompatibleStrategy.user_default.value
        payload["decision_source"] = DecisionSource.fallback.value
        payload["requested_strategy"] = CompatibleStrategy.auto.value
        return payload
    if token == CompatibleStrategy.user_default.value:
        payload["decision_source"] = DecisionSource.user_default.value
    else:
        payload["decision_source"] = DecisionSource.user_explicit.value
    payload["requested_strategy"] = token
    return payload


def record_auto_mapping_audit(
    *,
    tenant_id: str,
    trace_id: str | None,
) -> StrategyCompatAudit:
    audit = StrategyCompatAudit(
        occurred_at=datetime.now(timezone.utc).isoformat(),
        tenant_id=tenant_id,
        trace_id=trace_id,
        requested_strategy=CompatibleStrategy.auto.value,
        strategy=CompatibleStrategy.user_default,
        decision_source=DecisionSource.fallback,
    )
    _STRATEGY_COMPAT_AUDITS.append(audit)
    return audit


class ExecutionStrategyRequest(ContractModel):
    """帶執行策略的請求。默認 user_default，auto 只作為棄用輸入。"""

    strategy: CompatibleStrategy = Field(
        default=CompatibleStrategy.user_default,
        description="執行策略。默認 user_default，由租戶配置注入，契約層不寫死 auto。",
    )
    decision_source: DecisionSource = Field(
        default=DecisionSource.user_default,
        description="伺服器寫入。客戶端傳入會被覆蓋。auto 映射時為 fallback。",
    )
    requested_strategy: str | None = Field(
        default=None,
        max_length=32,
        description="伺服器寫入。舊客戶端傳 auto 時保留原值。",
    )
    strategy_audit: StrategyCompatAudit | None = Field(
        default=None,
        description="伺服器寫入。只有 auto 映射會帶審計列。",
    )

    @model_validator(mode="before")
    @classmethod
    def _compat_strategy(cls, data: Any) -> Any:
        return apply_strategy_compat(data)

    @model_validator(mode="after")
    def _audit_deprecated_auto(self) -> ExecutionStrategyRequest:
        if self.requested_strategy != CompatibleStrategy.auto.value:
            return self
        if self.decision_source is not DecisionSource.fallback:
            return self
        if self.strategy is not CompatibleStrategy.user_default:
            return self
        tenant_id = getattr(self, "tenant_id", None)
        if not isinstance(tenant_id, str):
            return self
        trace_id = getattr(self, "trace_id", None)
        self.strategy_audit = record_auto_mapping_audit(
            tenant_id=tenant_id,
            trace_id=trace_id if isinstance(trace_id, str) else None,
        )
        return self


class RoutePreviewRequest(ExecutionStrategyRequest):
    query: str = Field(min_length=1, max_length=8000)
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
    """opc 舊名收成 company，其餘名稱必須已是既有路徑之一。"""
    if path == LEGACY_PATH_OPC:
        return ExecutionPathName.company
    return ExecutionPathName(path)
