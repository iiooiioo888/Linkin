"""每租戶技能覆寫（啟用／停用、角色白名單），不修改全域 skills.json。"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from backend.tenant.context import current_tenant_user

_lock = threading.RLock()
DEFAULT_DIR = Path(__file__).resolve().parent.parent / "data" / "skills_overrides"


def _override_dir() -> Path:
    return Path(os.getenv("EVOL_SKILLS_OVERRIDE_DIR", str(DEFAULT_DIR)))


def _user_file(user_id: str | None = None) -> Path:
    from backend.tenant.context import current_tenant_user as _cur

    uid = re.sub(r"[^a-zA-Z0-9._@-]+", "_", (user_id or _cur()).strip())[:96]
    return _override_dir() / f"{uid or 'anonymous'}.json"


def _load(user_id: str | None = None) -> dict[str, Any]:
    path = _user_file(user_id)
    if not path.is_file():
        return {"skills": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            skills = raw.get("skills")
            if isinstance(skills, dict):
                return {"skills": skills}
    except (OSError, json.JSONDecodeError):
        pass
    return {"skills": {}}


def _save(data: dict[str, Any], user_id: str | None = None) -> None:
    path = _user_file(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "owner_user_id": (user_id or current_tenant_user()), "skills": data.get("skills") or {}}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def skill_enabled_override(skill_id: str, user_id: str | None = None) -> bool | None:
    """None = 無覆寫，沿用全域 skills.json。"""
    with _lock:
        row = (_load(user_id).get("skills") or {}).get(skill_id)
        if not isinstance(row, dict) or "enabled" not in row:
            return None
        return bool(row["enabled"])


def set_skill_enabled_override(skill_id: str, enabled: bool, user_id: str | None = None) -> None:
    with _lock:
        data = _load(user_id)
        skills = dict(data.get("skills") or {})
        skills[skill_id] = {**(skills.get(skill_id) or {}), "enabled": bool(enabled)}
        data["skills"] = skills
        _save(data, user_id)
