"""靈境 REST 路由共用 helpers：LLM 降級、工具錯誤轉 HTTP、實體刪除。"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from fastapi import HTTPException

from backend.linkin.knowledge import delete_entity
from backend.linkin.tools import ToolValidationError

logger = logging.getLogger("backend.linkin.api")

def _llm_ready() -> bool:
    if os.getenv("EVOL_LINKIN_NO_LLM", "").strip().lower() in {"1", "true", "yes"}:
        return False
    try:
        from backend.core.llm_config import get_runtime_config

        cfg = get_runtime_config()
        key = str(cfg.get("api_key") or os.getenv("OPENAI_API_KEY") or "").strip()
    except Exception:
        key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    return bool(key) and not key.startswith("sk-your")

def _try_call_llm(prompt: str, *, system: str, fallback: str) -> str:
    if not _llm_ready():
        return fallback
    try:
        from backend.core.llm import call_llm

        text = call_llm(prompt, system=system)
        return (text or "").strip() or fallback
    except Exception:
        logger.warning("靈境 LLM 呼叫失敗，改用本地模板", exc_info=True)
        return fallback

def _extract_json_object(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

def _delete_entity_or_404(collection: str, rec_id: str) -> dict[str, Any]:
    if not delete_entity(collection, rec_id):
        raise HTTPException(status_code=404, detail=f"{collection} 不存在")
    return {"deleted": True, "id": rec_id}

def _tool_http(exc: ToolValidationError) -> HTTPException:
    status = 409 if exc.code == "needs_confirmation" else 400
    return HTTPException(
        status_code=status,
        detail={"message": str(exc), "code": exc.code, **exc.extra},
    )
