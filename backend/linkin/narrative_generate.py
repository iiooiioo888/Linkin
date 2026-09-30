"""Phase 1 敘事草案 AI 一鍵生成：依使用者 brief 填充草稿鍵，不 commit。

寫入策略：成功時以 **replace-per-key** 覆寫所請求的草稿鍵；任一席解析或審查失敗時不修改任何既有草稿。
分派：經 ``backend.linkin.app_agents`` 的四部門應用席（執行者產出、審查員鐵律），
計量仍只經 ``backend.core.llm.call_llm``。
"""

from __future__ import annotations

import logging
from typing import Any

from backend.linkin.app_agents import AppAgentError, dispatch_application_drafts
from backend.linkin.narrative_commit import KNOWN_DRAFT_KEYS
from backend.linkin.narrative_starter import _llm_ready

logger = logging.getLogger(__name__)

DEFAULT_LOCALE = "zh-Hant"


class NarrativeGenerateError(ValueError):
    def __init__(self, message: str, *, code: str = "generate_failed", detail: str = ""):
        super().__init__(message)
        self.code = code
        self.detail = detail or message


def _normalize_keys(keys: list[str] | None) -> list[str]:
    if not keys:
        return sorted(KNOWN_DRAFT_KEYS)
    normalized: list[str] = []
    for raw in keys:
        key = str(raw or "").strip()
        if not key:
            continue
        if key not in KNOWN_DRAFT_KEYS:
            raise NarrativeGenerateError(f"未知草稿鍵：{key}", code="invalid_keys")
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise NarrativeGenerateError("需要至少一個草稿鍵", code="invalid_keys")
    return normalized


def generate_narrative_drafts(
    *,
    brief: str,
    locale: str = DEFAULT_LOCALE,
    keys: list[str] | None = None,
    region: str = "织庭都",
    theme: str = "",
) -> dict[str, Any]:
    """依 brief 分派應用層席位。成功回傳 ``{drafts, source, keys, agents}``。"""
    text = (brief or "").strip()
    if not text:
        raise NarrativeGenerateError("需要 brief（主題／種子描述）", code="missing_brief")

    target_keys = _normalize_keys(keys)
    region = (region or "织庭都").strip() or "织庭都"
    locale = (locale or DEFAULT_LOCALE).strip() or DEFAULT_LOCALE

    if not _llm_ready():
        raise NarrativeGenerateError(
            "LLM 未配置（請設定 API 金鑰或關閉 EVOL_LINKIN_NO_LLM）",
            code="llm_unavailable",
        )

    try:
        dispatched = dispatch_application_drafts(
            brief=text,
            keys=target_keys,
            locale=locale,
            region=region,
            theme=theme,
        )
    except AppAgentError as exc:
        logger.warning("應用層席位生成失敗：%s", exc)
        raise NarrativeGenerateError(str(exc), code=exc.code, detail=exc.detail) from exc
    except Exception as exc:
        logger.warning("敘事草案 LLM 呼叫失敗", exc_info=True)
        raise NarrativeGenerateError(
            "LLM 呼叫失敗",
            code="llm_failed",
            detail=str(exc),
        ) from exc

    return {
        "drafts": dispatched["drafts"],
        "source": "llm",
        "keys": target_keys,
        "agents": dispatched["agents"],
    }


__all__ = [
    "DEFAULT_LOCALE",
    "NarrativeGenerateError",
    "generate_narrative_drafts",
]
