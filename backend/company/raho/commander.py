"""RAHO 適配：L3 戰術指揮官對外入口。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from backend.services.commander import SYSTEM_PROMPT, TacticalCommander


def command_from_ticket(ticket: dict[str, Any] | str, *, use_llm: bool | None = None) -> dict[str, Any]:
    from backend.company.raho.store import STORE
    from backend.services.commander import plan_from_ticket

    pack = plan_from_ticket(ticket, use_llm=use_llm)
    plan = pack.get("battle_plan")
    if isinstance(plan, dict) and plan.get("plan_id"):
        STORE.put_battle_plan(str(plan["plan_id"]), pack)
    return pack


def command_grill(issues, **kwargs) -> dict[str, Any]:
    from backend.services.commander import respond_to_grill

    return respond_to_grill(issues, **kwargs)


def __getattr__(name: str):
    if name in {"SYSTEM_PROMPT", "TacticalCommander"}:
        from backend.services.commander import SYSTEM_PROMPT, TacticalCommander

        return SYSTEM_PROMPT if name == "SYSTEM_PROMPT" else TacticalCommander
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SYSTEM_PROMPT",
    "TacticalCommander",
    "command_from_ticket",
    "command_grill",
]
