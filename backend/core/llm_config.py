"""运行时 LLM 配置存储。

允许通过 API / 前端界面动态配置 LLM 供应商参数
（API Key、端点、模型），无需修改 .env 或重启服务。
配置持久化到 JSON 文件（位于 EVOL_CONFIG_DIR，容器内
挂载为持久卷），重启后自动恢复。

优先级：运行时配置 > 环境变量。
"""

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_config: dict | None = None


def _config_path() -> Path:
    directory = Path(
        os.getenv("EVOL_CONFIG_DIR", "/app/data" if os.path.exists("/app") else "backend/data")
    )
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "llm_config.json"


def get_runtime_config() -> dict:
    """取得当前生效的 LLM 配置。

    回传栏位：api_key、api_base、model。
    未设定运行时配置的栏位以环境变量补齐。
    """
    global _config
    with _lock:
        if _config is None:
            _config = _load_from_file()
        cfg = dict(_config)

    if not cfg.get("api_key"):
        cfg["api_key"] = os.getenv("OPENAI_API_KEY", "")
    if not cfg.get("model"):
        env_model = os.getenv("EVOL_MODEL", "").strip()
        api_base = str(cfg.get("api_base") or os.getenv("OPENAI_API_BASE", "") or "")
        if env_model:
            cfg["model"] = env_model
        elif api_base:
            from backend.core.provider_pool import classify_provider, static_catalog

            rows = static_catalog(classify_provider(api_base, ""))
            cfg["model"] = rows[0]["id"] if rows else "gpt-4o"
        else:
            cfg["model"] = "gpt-4o"
    return cfg


def _load_from_file() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("LLM 配置文件读取失败（忽略）：%s", exc)
    return {}


def save_runtime_config(
    api_key: str | None = None,
    api_base: str | None = None,
    model: str | None = None,
) -> dict:
    """更新运行时配置并持久化。

    传入 None 的栏位保持原值；传入空字串可清除。
    同时写入环境变量，让 LiteLLM 预设金鑰機制同步生效。
    """
    global _config
    with _lock:
        if _config is None:
            _config = _load_from_file()
        if api_key is not None:
            _config["api_key"] = api_key.strip()
        if api_base is not None:
            _config["api_base"] = api_base.strip()
        if model is not None:
            _config["model"] = model.strip()
        snapshot = dict(_config)
        try:
            with open(_config_path(), "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("LLM 配置持久化失败（内存中仍生效）：%s", exc)

    _sync_env(snapshot)
    try:
        from backend.core.api_router import sync_primary_into_routes

        sync_primary_into_routes()
        snapshot = get_runtime_config()
    except Exception:  # noqa: BLE001 — 路由同步失敗不得擋住主配置
        logger.debug("同步 primary 路由失敗", exc_info=True)
    return snapshot


def _sync_env(snapshot: dict) -> None:
    if snapshot.get("api_key"):
        os.environ["OPENAI_API_KEY"] = snapshot["api_key"]
    if snapshot.get("api_base"):
        os.environ["OPENAI_API_BASE"] = snapshot["api_base"]


def merge_runtime_config(fields: dict) -> dict:
    """合併任意欄位並持久化（模型目錄、運維狀態）。"""
    global _config
    with _lock:
        if _config is None:
            _config = _load_from_file()
        for key, value in fields.items():
            _config[key] = value
        snapshot = dict(_config)
        try:
            with open(_config_path(), "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            logger.warning("LLM 配置持久化失败（内存中仍生效）：%s", exc)
    _sync_env(snapshot)
    return snapshot


def reset_runtime_config() -> None:
    """測試用：清掉記憶體快取，下次讀檔。"""
    global _config
    with _lock:
        _config = None


def masked_key(api_key: str) -> str:
    """回传脱敏后的金钥（供 API 展示）。"""
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return api_key[:2] + "*" * (len(api_key) - 2)
    return f"{api_key[:4]}...{api_key[-4:]}"


def get_explicit_model() -> str:
    """回传用户明確配置過的模型（配置檔或 EVOL_MODEL 環境變數）。

    與 get_runtime_config().get('model') 的差異：此函式不含
    「gpt-4o」預設回退，未配置時回傳空字串，供需要區分
    「使用者配置 vs 系統預設」的模組使用（如預算層級路由）。
    """
    global _config
    with _lock:
        if _config is None:
            _config = _load_from_file()
        file_model = (_config.get("model") or "").strip()
    if file_model:
        return file_model
    env_model = os.getenv("EVOL_MODEL", "").strip()
    # .env 模板的 gpt-4o 預設值不視為顯式配置
    if env_model and env_model != "gpt-4o":
        return env_model
    return ""
