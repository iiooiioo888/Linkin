"""RAHO 角色映射：角色 id 正規化與層級推導。"""

from __future__ import annotations

from typing import Any

from backend.company.state import RoleType

from .layers import LAYER_META, ROLE_ID_TO_LAYER, RahoLayer


def _full_for_role_id(role_id: str) -> str:
    layer = ROLE_ID_TO_LAYER.get(role_id)
    if layer is None:
        return role_id
    return str(LAYER_META[layer]["full"])


def _labels_for_ids(role_ids: list[str] | tuple[str, ...] | None) -> list[str]:
    return [_full_for_role_id(rid) for rid in (role_ids or [])]


_ROLE_OVERLAYS: dict[str, dict[str, Any]] = {
    "environment_kernel": {"layer": 0, "title": "環境與記憶核心", "spine": True},
    "constitutional_inspector": {"layer": 1, "title": "憲兵審查官", "spine": True},
    "atomic_executor": {"layer": 2, "title": "原子執行者", "spine": True},
    "requirement_auditor": {"layer": 4, "title": "需求審計官", "spine": True},
    "tactical_commander": {"layer": 3, "title": "戰術指揮官", "spine": True},
    "user": {"layer": 5, "title": "用戶", "spine": True},
    "manager": {"layer": 4, "title": "任務經理", "spine": False},
    "reviewer": {"layer": 1, "title": "審查者", "spine": False},
}


def _role_value(role: RoleType | str | None) -> str:
    if role is None:
        return ""
    if isinstance(role, RoleType):
        return role.value
    return str(role).strip()


def role_to_raho_layer(role: RoleType | str | None) -> RahoLayer:
    """將現有 RoleType 映射到 RAHO 質詢層。"""
    value = _role_value(role)
    if not value:
        return RahoLayer.L2_EXECUTOR
    if value in ROLE_ID_TO_LAYER:
        return RahoLayer(ROLE_ID_TO_LAYER[value])
    overlay = _ROLE_OVERLAYS.get(value)
    if overlay:
        return RahoLayer(int(overlay["layer"]))
    if value.endswith("_lead") or value in {"architect", "coordinator"}:
        return RahoLayer.L3_COMMANDER
    return RahoLayer.L2_EXECUTOR


def canonical_role_id(layer: int | RahoLayer | None) -> str:
    """層級在質詢樹／名冊上的正規角色 id。"""
    try:
        key = int(layer) if layer is not None else 2
    except (TypeError, ValueError):
        key = 2
    return str(LAYER_META.get(key, LAYER_META[2]).get("role_id") or "")
