"""Minecraft 動作。危險寫入必須先有 guardrail 決策。"""

from __future__ import annotations

from typing import Any

from pydantic import Field, model_validator

from linkin_core.contracts.common import TENANT_ID, TRACE_ID, ContractModel

MUTATING_MINECRAFT_ACTIONS = frozenset(
    {
        "place_block",
        "pose_block",
        "break_block",
        "fill_block",
        "execute_command",
    }
)


def minecraft_requires_guardrail(action: str) -> bool:
    return action in MUTATING_MINECRAFT_ACTIONS


class MinecraftActionRequest(ContractModel):
    server_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    guardrail_decision_id: str | None = Field(default=None, max_length=64)
    tenant_id: str = Field(pattern=TENANT_ID)
    trace_id: str = Field(pattern=TRACE_ID)

    @model_validator(mode="after")
    def mutating_needs_decision(self) -> MinecraftActionRequest:
        if minecraft_requires_guardrail(self.action) and not self.guardrail_decision_id:
            raise ValueError("危險 Minecraft 動作需要 guardrail 決策")
        return self


class MinecraftActionResult(ContractModel):
    ok: bool
    detail: str = ""
    session_id: str
