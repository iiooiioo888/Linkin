"""運行時 LLM 配置儲存。

允許透過 API／前端動態配置 LLM 供應商參數（API Key、端點、模型），
無需修改 .env 或重啟服務。

範圍：
- 未綁定租戶（腳本、測試直接呼叫）：``EVOL_CONFIG_DIR/llm_config.json``
  與環境變數，並同步程序環境（既有單機行為）。
- 已登入租戶：只讀寫該 ``user_id`` 的 ``llm_config.json``。
  不繼承其他帳號或平台金鑰，也不寫入 ``OPENAI_API_KEY``。

既有全域檔的遷移見 ``migrate_legacy_user_settings``：複製給遺留擁有者，不刪除來源。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_platform: dict | None = None
_users: dict[str, dict] = {}


def platform_config_path() -> Path:
    directory = Path(
        os.getenv("EVOL_CONFIG_DIR", "/app/data" if os.path.exists("/app") else "backend/data")
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "llm_config.json"


def _config_path() -> Path:
    return platform_config_path()


def _load_platform_file() -> dict:
    path = platform_config_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("LLM 配置文件读取失败（忽略）：%s", exc)
    return {}


def _read_platform() -> dict:
    global _platform
    with _lock:
        if _platform is None:
            _platform = _load_platform_file()
        return dict(_platform)


def _read_user(user_id: str) -> dict:
    from backend.core.user_settings import read_json

    with _lock:
        cached = _users.get(user_id)
        if cached is None:
            cached = read_json(user_id, "llm_config.json")
            _users[user_id] = cached
        return dict(cached)


def _apply_defaults(cfg: dict, *, inherit_secrets: bool) -> dict:
    """補上模型預設。已登入帳號不繼承環境金鑰、端點或其他帳號的選擇。

    平台範圍與舊行為一致：環境端點只參與「尚未指定模型」時的推斷，
    不回寫進回傳的 api_base（LiteLLM 仍會自己讀 OPENAI_API_BASE）。
    """
    if inherit_secrets and not cfg.get("api_key"):
        cfg["api_key"] = os.getenv("OPENAI_API_KEY", "")
    if not cfg.get("model"):
        env_model = os.getenv("EVOL_MODEL", "").strip() if inherit_secrets else ""
        api_base = str(cfg.get("api_base") or "")
        if inherit_secrets and not api_base:
            api_base = os.getenv("OPENAI_API_BASE", "").strip()
        if env_model:
            cfg["model"] = env_model
        elif api_base:
            from backend.core.provider_pool import classify_provider, static_catalog

            rows = static_catalog(classify_provider(api_base, ""))
            cfg["model"] = rows[0]["id"] if rows else "gpt-5.6-luna"
        else:
            cfg["model"] = "gpt-5.6-luna"
    return cfg


def get_runtime_config() -> dict:
    """取得當前範圍生效的 LLM 配置。

    回傳欄位含 api_key、api_base、model。已登入時只含該帳號自己的值。
    """
    from backend.core.user_settings import active_settings_user

    user = active_settings_user()
    if user:
        return _apply_defaults(_read_user(user), inherit_secrets=False)
    return _apply_defaults(_read_platform(), inherit_secrets=True)


def _write_platform(snapshot: dict) -> None:
    try:
        with open(platform_config_path(), "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.warning("LLM 配置持久化失败（内存中仍生效）：%s", exc)


def _write_user(user_id: str, snapshot: dict) -> None:
    from backend.core.user_settings import write_json

    try:
        write_json(user_id, "llm_config.json", snapshot)
    except OSError as exc:
        logger.warning("使用者 LLM 配置持久化失敗（記憶體中仍生效）：%s", exc)


def _sync_env(snapshot: dict) -> None:
    if snapshot.get("api_key"):
        os.environ["OPENAI_API_KEY"] = snapshot["api_key"]
    if snapshot.get("api_base"):
        os.environ["OPENAI_API_BASE"] = snapshot["api_base"]


def _mutate(fields: dict) -> dict:
    """依目前範圍更新配置。使用者寫入不碰平台檔、不同步程序環境。"""
    from backend.core.user_settings import active_settings_user

    global _platform
    user = active_settings_user()
    with _lock:
        if user:
            current = dict(_users.get(user) or {})
            if not current:
                from backend.core.user_settings import read_json

                current = read_json(user, "llm_config.json")
            current.update(fields)
            snapshot = dict(current)
            _users[user] = snapshot
        else:
            if _platform is None:
                _platform = _load_platform_file()
            _platform.update(fields)
            snapshot = dict(_platform)
    if user:
        _write_user(user, snapshot)
    else:
        _write_platform(snapshot)
        _sync_env(snapshot)
    return snapshot


def save_runtime_config(
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
) -> dict:
    """更新運行時配置並持久化。

    傳入 None 的欄位保持原值；傳入空字串可清除。
    僅平台範圍會寫入環境變數。使用者範圍只寫自己的檔。
    """
    fields: dict = {}
    if api_key is not None:
        fields["api_key"] = api_key.strip()
    if api_base is not None:
        fields["api_base"] = api_base.strip()
    if model is not None:
        fields["model"] = model.strip()
    if fields:
        _mutate(fields)
    try:
        from backend.core.api_router import sync_primary_into_routes

        sync_primary_into_routes()
    except Exception:
        logger.debug("同步 primary 路由失敗", exc_info=True)
    return get_runtime_config()


def merge_runtime_config(fields: dict) -> dict:
    """合併任意欄位並持久化（模型目錄、運維狀態、路由）。"""
    _mutate(dict(fields))
    return get_runtime_config()


def reset_runtime_config() -> None:
    """測試用：清掉記憶體快取，下次讀檔。"""
    global _platform
    with _lock:
        _platform = None
        _users.clear()


def masked_key(api_key: str) -> str:
    """回傳脫敏後的金鑰（供 API 展示）。"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return api_key[:2] + "*" * (len(api_key) - 2)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_explicit_model() -> str:
    """回傳使用者明確配置過的模型（配置檔或平台 EVOL_MODEL）。

    已登入時只看該帳號的配置檔，不含其他帳號與環境預設。
    未配置時回傳空字串，供預算層級路由區分「使用者配置 vs 系統預設」。
    """
    from backend.core.user_settings import active_settings_user

    user = active_settings_user()
    if user:
        return str(_read_user(user).get("model") or "").strip()
    file_model = str(_read_platform().get("model") or "").strip()
    if file_model:
        return file_model
    env_model = os.getenv("EVOL_MODEL", "").strip()
    if env_model and env_model != "gpt-4o":
        return env_model
    return ""
