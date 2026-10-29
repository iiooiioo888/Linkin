"""敘事、控制台與現場寫入的同一里程碑。

已存在席位的提示詞與工具權限立刻寫進目錄。
新席位與現場寫入留在確認上，點頭才落盤。
憲法在這一輪只讀。拒絕確認不退回已經寫進目錄的變更。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

from backend.company.state import RoleType

ENTITY_KINDS = {
    "npc": "npcs",
    "quest": "quests",
    "item": "items",
}
_FROZEN_KEYS = {"constitution", "worldview", "l0", "graph"}


def catalog_role_ids() -> set[str]:
    from backend.company.role_catalog import list_role_snapshots

    found: set[str] = set()
    for snap in list_role_snapshots():
        role_id = str(snap.get("id") or "")
        if role_id and snap.get("enabled", True):
            found.add(role_id)
    return found


def resolve_assignee(role_id: str) -> RoleType | str:
    """目錄裡的自訂席保持原 id。不在目錄也不在列舉時才改派 developer。"""
    text = (role_id or "").strip()
    if not text:
        return RoleType.DEVELOPER
    try:
        return RoleType(text)
    except ValueError:
        if text in catalog_role_ids():
            return text
        return RoleType.DEVELOPER


def apply_existing_override(
    role_id: str,
    *,
    system_prompt: str | None = None,
    tools_allowed: list[str] | None = None,
) -> dict[str, Any]:
    """已存在席位立刻改目錄。新席位不能走這條。"""
    from backend.company.role_catalog import update_role_settings

    payload: dict[str, Any] = {}
    if system_prompt is not None:
        payload["system_prompt"] = system_prompt
    if tools_allowed is not None:
        payload["tools_allowed"] = [str(item) for item in tools_allowed if str(item).strip()]
    if not payload:
        raise ValueError("請提供提示詞或工具權限")
    try:
        return update_role_settings(role_id, payload)
    except KeyError as exc:
        raise KeyError("席位不存在。新席位要放在確認上，點頭後才建立") from exc


def _clean_new_seats(raw: Any) -> list[dict[str, Any]]:
    seats: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return seats
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        seats.append({
            "name": name,
            "id": str(item.get("id") or "").strip(),
            "system_prompt": str(item.get("system_prompt") or ""),
            "tools_allowed": [str(tool) for tool in (item.get("tools_allowed") or []) if str(tool).strip()],
        })
    return seats


def _clean_writes(raw: Any) -> list[dict[str, Any]]:
    writes: list[dict[str, Any]] = []
    if not isinstance(raw, list):
        return writes
    for item in raw:
        if not isinstance(item, dict):
            continue
        tag = str(item.get("tag") or item.get("tag_name") or "").strip()
        if not tag:
            continue
        writes.append({"tag": tag, "value": item.get("value")})
    return writes


def absorb_analysis(plan: dict[str, Any], meta: dict[str, Any] | None) -> dict[str, Any]:
    """分析結束時：已存在席位立刻寫目錄；新席位與現場寫入只進確認。憲法丟掉。"""
    source = meta if isinstance(meta, dict) else {}
    applied: list[dict[str, Any]] = []
    for row in source.get("seat_overrides") or []:
        if not isinstance(row, dict):
            continue
        role_id = str(row.get("role_id") or row.get("assignee") or "").strip()
        if not role_id:
            continue
        try:
            apply_existing_override(
                role_id,
                system_prompt=row.get("system_prompt"),
                tools_allowed=row.get("tools_allowed"),
            )
            applied.append({"role_id": role_id, "applied": True})
        except KeyError:
            applied.append({"role_id": role_id, "applied": False, "reason": "席位不存在"})
        except ValueError as exc:
            applied.append({"role_id": role_id, "applied": False, "reason": str(exc)})
    plan["seat_overrides"] = applied
    plan["new_seats"] = _clean_new_seats(source.get("new_seats"))
    plan["field_writes"] = _clean_writes(source.get("field_writes"))
    plan.pop("constitution", None)
    return plan


def replace_confirmation_draft(
    plan: dict[str, Any],
    *,
    new_seats: list[dict[str, Any]] | None = None,
    field_writes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """點頭前改確認卡。不寫目錄，不改憲法。"""
    if new_seats is not None:
        plan["new_seats"] = _clean_new_seats(new_seats)
    if field_writes is not None:
        plan["field_writes"] = _clean_writes(field_writes)
    plan.pop("constitution", None)
    plan["version"] = int(plan.get("version") or 1) + 1
    return plan


def create_confirmed_seats(plan: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.company.role_catalog import create_custom_role

    created: list[dict[str, Any]] = []
    for seat in plan.get("new_seats") or []:
        record = create_custom_role({
            "name": seat.get("name"),
            "id": seat.get("id") or f"seat_{uuid.uuid4().hex[:8]}",
            "system_prompt": seat.get("system_prompt") or "",
            "tools_allowed": seat.get("tools_allowed") or [],
        })
        created.append({"id": record.get("id"), "name": record.get("name")})
    plan["new_seats_created"] = created
    return created


def commit_field_writes(
    writes: list[dict[str, Any]],
    writer: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """整批通過檢查才寫。任一筆不通過就一筆都不寫。"""
    from opc_service.guard import write_guard

    failures: list[dict[str, str]] = []
    accepted: list[dict[str, Any]] = []
    for row in writes:
        tag = str(row.get("tag") or row.get("tag_name") or "").strip()
        raw_val = row.get("value")
        if raw_val is None:
            failures.append({"tag": tag, "message": "數值無法檢查"})
            continue
        try:
            value = float(raw_val)
        except (TypeError, ValueError):
            failures.append({"tag": tag, "message": "數值無法檢查"})
            continue
        ok, message = write_guard.validate_write(tag, value)
        if not ok:
            failures.append({"tag": tag, "message": message})
            continue
        accepted.append({"tag_name": tag, "value": value})
    if failures:
        return {"status": "blocked", "written": [], "failures": failures}
    if not accepted:
        return {"status": "empty", "written": [], "failures": []}
    if writer is None:
        written = [
            {"tag_name": row["tag_name"], "value": row["value"], "status": "guard_passed"}
            for row in accepted
        ]
    else:
        written = list(writer(accepted))
    return {"status": "accepted", "written": written, "failures": []}


def commit_narrative_entity(kind: str, record: dict[str, Any]) -> dict[str, Any]:
    """顯式寫入只進實體。憲法與世界圖譜拒絕。"""
    from backend.linkin.knowledge import upsert_entity

    normalized = (kind or "").strip().lower()
    if normalized in _FROZEN_KEYS or any(key in record for key in _FROZEN_KEYS):
        raise ValueError("這一輪世界觀只讀，不能寫入")
    collection = ENTITY_KINDS.get(normalized)
    if collection is None:
        raise ValueError("顯式寫入只接受 npc、quest、item")
    payload = {key: value for key, value in record.items() if key not in _FROZEN_KEYS}
    if not str(payload.get("name") or payload.get("title") or "").strip():
        raise ValueError("實體需要名稱")
    stored = upsert_entity(collection, payload)
    return {"kind": normalized, "collection": collection, "entity": stored}
