"""每個登入帳號的設定檔。

平台預設（``llm_config.json``、環境變數）只服務「沒有綁定租戶」的程序路徑
（腳本、背景作業、既有單機呼叫）。已登入請求只讀寫

``EVOL_USER_SETTINGS_DIR/<user_id>/``

之下的檔案，不把金鑰寫回共用檔，也不寫進程序環境變數。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}\.json$")
LEGACY_OWNER_DEFAULT = "deploy_admin"


def sanitize_user_id(raw: str | None) -> str:
    text = re.sub(r"[^a-zA-Z0-9._@-]+", "_", (raw or "").strip())[:96]
    return text.strip("._") or ""


def active_settings_user() -> str | None:
    """目前請求綁定的租戶；未綁定時回傳 None（走平台範圍）。

    角色表在匯入當下就會讀顯式模型。那時 ``backend.tenant`` 套件還沒載完，
    若再 import 會跟 task_manager 循環。租戶模組尚未載入就視為沒有登入帳號。
    """
    import sys

    mod = sys.modules.get("backend.tenant.context")
    if mod is None:
        return None
    explicit = (mod.tenant_user_id.get() or "").strip()
    if not explicit:
        return None
    uid = sanitize_user_id(explicit)
    if not uid or uid == "anonymous":
        return None
    return uid


def settings_root() -> Path:
    default = Path(__file__).resolve().parent.parent / "data" / "user_settings"
    return Path(os.getenv("EVOL_USER_SETTINGS_DIR", str(default)))


def user_settings_dir(user_id: str) -> Path:
    uid = sanitize_user_id(user_id)
    if not uid or uid in {".", ".."}:
        raise ValueError("無效的使用者 ID")
    root = settings_root().resolve()
    path = (root / uid).resolve()
    if path != root and root not in path.parents:
        raise ValueError("使用者設定路徑越界")
    return path


def _file_path(user_id: str, name: str) -> Path:
    if not _NAME_RE.fullmatch(name):
        raise ValueError("無效的設定檔名")
    directory = user_settings_dir(user_id)
    path = (directory / name).resolve()
    if directory.resolve() not in path.parents:
        raise ValueError("設定檔路徑越界")
    return path


def read_json(user_id: str, name: str) -> dict[str, Any]:
    path = _file_path(user_id, name)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("讀取使用者設定失敗（%s）：%s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def write_json(user_id: str, name: str, payload: dict[str, Any]) -> Path:
    path = _file_path(user_id, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def guard_settings_write() -> str | None:
    """閘門開啟卻沒有租戶時拒絕寫入。回傳使用者 ID，或 None（平台範圍）。"""
    from backend.auth.gate import gate_enabled

    uid = active_settings_user()
    if gate_enabled() and not uid:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="未登入，拒絕寫入設定")
    return uid


def legacy_owner_id() -> str:
    """既有全域設定要複製給誰。優先序：顯式擁有者 → 閘門帳號 → deploy_admin。"""
    explicit = sanitize_user_id(os.getenv("EVOL_SETTINGS_LEGACY_OWNER", ""))
    if explicit:
        return explicit
    gate = sanitize_user_id(os.getenv("LINKIN_GATE_ID", ""))
    if gate:
        return gate
    return LEGACY_OWNER_DEFAULT


def _read_platform_llm() -> dict[str, Any]:
    from backend.core.llm_config import platform_config_path

    path = platform_config_path()
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def migrate_legacy_user_settings(*, force: bool = False) -> dict[str, Any]:
    """把既有全域 LLM 設定與採集 cookie 複製到遺留擁有者。

    不刪除、不覆寫已存在的使用者檔。pytest 預設跳過，避免測試夾具被當成生產遷移。
    """
    if os.getenv("PYTEST_CURRENT_TEST") and not force:
        return {"skipped": True, "reason": "pytest"}
    owner = legacy_owner_id()
    report: dict[str, Any] = {"owner": owner, "llm_copied": False, "cookie_copied": False}
    with _lock:
        existing = read_json(owner, "llm_config.json")
        legacy = _read_platform_llm()
        if legacy and not existing:
            write_json(owner, "llm_config.json", legacy)
            report["llm_copied"] = True
            logger.info("已將共用 llm_config.json 複製到使用者 %s（來源保留）", owner)
        elif legacy and existing:
            report["llm_copied"] = False
            report["llm_note"] = "owner-exists"
        cookie = _legacy_mediacrawler_cookie()
        if cookie and not read_json(owner, "mediacrawler.json").get("cookie"):
            current = read_json(owner, "mediacrawler.json")
            current["cookie"] = cookie
            write_json(owner, "mediacrawler.json", current)
            report["cookie_copied"] = True
    return report


def _legacy_mediacrawler_cookie() -> str:
    from backend.mediacrawler.config import DEFAULT_RUNTIME_CONFIG, load_env_config

    cfg = load_env_config()
    path = cfg.runtime_config_path or DEFAULT_RUNTIME_CONFIG
    if not path.is_file():
        return ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("cookie") or "").strip()


def integration_overlay(user_id: str, name: str) -> dict[str, Any] | None:
    items = read_json(user_id, "integrations.json").get("items")
    if not isinstance(items, dict):
        return None
    row = items.get(name)
    return dict(row) if isinstance(row, dict) else None


def set_integration_fields(user_id: str, name: str, **fields: Any) -> dict[str, Any]:
    safe = re.sub(r"[^a-z0-9_-]", "", (name or "").strip().lower())
    if not safe:
        raise ValueError("未知的整合")
    with _lock:
        data = read_json(user_id, "integrations.json")
        items = data.get("items")
        if not isinstance(items, dict):
            items = {}
        row = dict(items.get(safe) or {})
        for key, value in fields.items():
            if value is None:
                continue
            row[key] = value
        items[safe] = row
        data["items"] = items
        data["owner_user_id"] = user_id
        write_json(user_id, "integrations.json", data)
        return row


LAB_TOOL_IDS = (
    "opc.read",
    "opc.write",
    "memory.search",
    "firecrawl.scrape",
    "docker.inspect",
)
LAB_TOOL_DEFAULTS: dict[str, bool] = {
    "opc.read": True,
    "opc.write": True,
    "memory.search": True,
    "firecrawl.scrape": True,
    "docker.inspect": False,
}


def lab_tool_prefs(user_id: str | None = None) -> dict[str, bool]:
    uid = user_id or active_settings_user()
    merged = dict(LAB_TOOL_DEFAULTS)
    if not uid:
        raw = _platform_blob("lab.json")
    else:
        raw = read_json(uid, "lab.json")
    tools = raw.get("mcp_tools") if isinstance(raw, dict) else None
    if isinstance(tools, dict):
        for key in LAB_TOOL_IDS:
            if key in tools:
                merged[key] = bool(tools[key])
    return merged


def save_lab_tool_prefs(tools: dict[str, Any], user_id: str | None = None) -> dict[str, bool]:
    uid = user_id or active_settings_user()
    cleaned = dict(LAB_TOOL_DEFAULTS)
    for key in LAB_TOOL_IDS:
        if key in tools:
            cleaned[key] = bool(tools[key])
    payload: dict[str, Any] = {"mcp_tools": cleaned}
    if uid:
        payload["owner_user_id"] = uid
        write_json(uid, "lab.json", payload)
    else:
        _write_platform_blob("lab.json", payload)
    return cleaned


def reflect_override(user_id: str | None = None) -> str:
    uid = user_id or active_settings_user()
    if not uid:
        return ""
    raw = str(read_json(uid, "reflect.json").get("post_company_reflect") or "").strip().lower()
    if raw in {"off", "evaluate", "full"}:
        return raw
    return ""


def save_reflect_override(mode: str, user_id: str | None = None) -> str:
    value = (mode or "").strip().lower()
    if value not in {"off", "evaluate", "full"}:
        raise ValueError("post_company_reflect 必須為 off、evaluate 或 full")
    uid = user_id or active_settings_user()
    if not uid:
        return ""
    write_json(uid, "reflect.json", {"owner_user_id": uid, "post_company_reflect": value})
    return value


def _platform_dir() -> Path:
    path = settings_root() / "_platform"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _platform_blob(name: str) -> dict[str, Any]:
    if not _NAME_RE.fullmatch(name):
        raise ValueError("無效的設定檔名")
    path = _platform_dir() / name
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _write_platform_blob(name: str, payload: dict[str, Any]) -> None:
    if not _NAME_RE.fullmatch(name):
        raise ValueError("無效的設定檔名")
    path = _platform_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
