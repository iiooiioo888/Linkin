"""租戶執行路徑設定。

每個登入帳號一份，落在使用者設定目錄的 ``execution_path.json``。
未登入的程序路徑只用內建默認，不寫檔。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DEFAULT_FORCE_COMPANY_KEYWORDS: tuple[str, ...] = ("opc", "plc")
_MAX_KEYWORDS = 64
_MAX_KEYWORD_LEN = 64


@dataclass(frozen=True)
class ExecutionPathConfig:
    """租戶可調的選路設定。"""

    allow_user_path_choice: bool = True
    default_execution_strategy: Literal["simple", "company"] | None = None
    force_company_keywords: tuple[str, ...] = DEFAULT_FORCE_COMPANY_KEYWORDS

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "allow_user_path_choice": self.allow_user_path_choice,
            "default_execution_strategy": self.default_execution_strategy,
            "force_company_keywords": list(self.force_company_keywords),
        }


def _clean_keywords(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return DEFAULT_FORCE_COMPANY_KEYWORDS
    seen: list[str] = []
    for item in raw:
        token = str(item or "").strip()
        if not token:
            continue
        token = token[:_MAX_KEYWORD_LEN]
        key = token.lower()
        if key in {existing.lower() for existing in seen}:
            continue
        seen.append(token)
        if len(seen) >= _MAX_KEYWORDS:
            break
    return tuple(seen)


def parse_execution_path_config(raw: dict[str, Any] | None) -> ExecutionPathConfig:
    data = raw or {}
    allow = data.get("allow_user_path_choice", True)
    default = data.get("default_execution_strategy")
    if default not in ("simple", "company"):
        default = None
    if "force_company_keywords" in data:
        keywords = _clean_keywords(data.get("force_company_keywords"))
    else:
        keywords = DEFAULT_FORCE_COMPANY_KEYWORDS
    return ExecutionPathConfig(
        allow_user_path_choice=bool(allow),
        default_execution_strategy=default,
        force_company_keywords=keywords,
    )


def load_execution_path_config(user_id: str | None = None) -> ExecutionPathConfig:
    """讀目前租戶的設定。沒有檔案時回內建默認。"""
    from backend.core.user_settings import active_settings_user, read_json

    uid = user_id if user_id is not None else active_settings_user()
    if not uid:
        return ExecutionPathConfig()
    return parse_execution_path_config(read_json(uid, "execution_path.json"))


def save_execution_path_config(
    updates: dict[str, Any],
    *,
    user_id: str | None = None,
) -> ExecutionPathConfig:
    """合併寫入。未出現的欄位保留原值。``clear_default`` 會清掉默認路徑。"""
    from backend.core.user_settings import active_settings_user, read_json, write_json

    uid = user_id if user_id is not None else active_settings_user()
    current = load_execution_path_config(uid)
    payload: dict[str, Any] = current.to_public_dict()
    if "allow_user_path_choice" in updates and updates["allow_user_path_choice"] is not None:
        payload["allow_user_path_choice"] = bool(updates["allow_user_path_choice"])
    if updates.get("clear_default"):
        payload["default_execution_strategy"] = None
    elif "default_execution_strategy" in updates:
        default = updates.get("default_execution_strategy")
        if default in ("simple", "company"):
            payload["default_execution_strategy"] = default
        elif default in (None, ""):
            payload["default_execution_strategy"] = None
        else:
            raise ValueError("default_execution_strategy 只能是 simple 或 company")
    if "force_company_keywords" in updates and updates["force_company_keywords"] is not None:
        payload["force_company_keywords"] = list(_clean_keywords(updates["force_company_keywords"]))
    parsed = parse_execution_path_config(payload)
    if not uid:
        return parsed
    stored = parsed.to_public_dict()
    stored["owner_user_id"] = uid
    previous = read_json(uid, "execution_path.json")
    if isinstance(previous, dict) and previous.get("owner_user_id"):
        stored["owner_user_id"] = previous["owner_user_id"]
    write_json(uid, "execution_path.json", stored)
    return parsed
