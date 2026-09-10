"""整合層 HTTP API：狀態目錄＋召回編排。

端點（全部唯讀或顯式動作；寫入外部平台一律為顯式 POST）：
- ``GET  /integrations``：五個整合的啟用狀態與健康檢查
- ``POST /integrations/recall``：token 節省召回編排（ContextAssembler）
- ``POST /integrations/{name}/enable|disable``：運行時顯式啟停（寫審計軌跡）

契約：召回結果只作為注入片段；生成一律走 ``call_llm``（C-LLM-001）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.integrations.base import IntegrationConfig
from backend.integrations.context_assembler import ContextAssembler, RecallPolicy
from backend.integrations.memos import MemosClient
from backend.integrations.memos import config_from_env as memos_env
from backend.integrations.openviking import OpenVikingClient
from backend.integrations.openviking import config_from_env as viking_env
from backend.integrations.openpencil import OpenPencilClient
from backend.integrations.ouroboros import OuroborosClient
from backend.integrations.ouroboros import config_from_env as ouroboros_env
from backend.integrations.weknora import WeKnoraClient
from backend.integrations.weknora import config_from_env as weknora_env
from backend.integrations.yao import YaoClient
from backend.integrations.yao import config_from_env as yao_env

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# ── 運行時單例（測試可經 build_registry 注入假 transport）──


def build_registry(**http_kwargs: Any) -> dict[str, Any]:
    """建立五個整合客戶端；``http_kwargs``（如假 transport）透傳給所有客戶端。"""
    return {
        "memos": MemosClient(**http_kwargs),
        "openviking": OpenVikingClient(**http_kwargs),
        "weknora": WeKnoraClient(**http_kwargs),
        "yao": YaoClient(**http_kwargs),
        "ouroboros": OuroborosClient(**http_kwargs),
        "openpencil": OpenPencilClient(**http_kwargs),
    }


_REGISTRY: dict[str, Any] | None = None


def get_registry() -> dict[str, Any]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = build_registry()
    return _REGISTRY


def reset_registry() -> None:
    """測試隔離。"""
    global _REGISTRY
    _REGISTRY = None


def _status_of(name: str, client: Any) -> dict[str, Any]:
    cfg: IntegrationConfig = client.http.config
    status: dict[str, Any] = {"name": name, "enabled": cfg.enabled, "base_url": cfg.base_url}
    if cfg.enabled:
        probe = client.http.get("health") if name not in ("yao", "openpencil") else None
        if name in ("yao", "openpencil"):
            probe = None
            status["health"] = client.health()
        if probe is not None:
            status["health"] = {"ok": probe.ok, "reason_code": probe.reason_code, "latency_ms": probe.latency_ms}
    return status


@router.get("")
def list_integrations() -> dict[str, Any]:
    """整合目錄與健康狀態。"""
    return {"integrations": [_status_of(name, client) for name, client in get_registry().items()]}


class RecallRequest(BaseModel):
    query: str
    history: list[dict[str, str]] = []
    user_id: str = "default"
    cube_ids: list[str] = []
    knowledge_base_id: str = ""
    audit_path: bool = False


@router.post("/recall")
def recall(req: RecallRequest) -> dict[str, Any]:
    """token 節省召回：記憶（MemOS）＋分層上下文（OpenViking）＋知識（WeKnora）。"""
    reg = get_registry()
    assembler = ContextAssembler(
        memos=reg["memos"], viking=reg["openviking"], weknora=reg["weknora"], policy=RecallPolicy()
    )
    out = assembler.assemble(
        req.query,
        req.history,
        user_id=req.user_id,
        cube_ids=req.cube_ids,
        knowledge_base_id=req.knowledge_base_id,
        audit_path=req.audit_path,
    )
    return {
        "injection": out.render_injection(),
        "fragments": out.fragments,
        "history": out.history,
        "reason_codes": out.reason_codes,
        "degraded_sources": out.degraded_sources,
        "token_report": out.token_report,
    }


class ToggleRequest(BaseModel):
    enabled: bool


@router.post("/{name}/toggle")
def toggle_integration(name: str, req: ToggleRequest) -> dict[str, Any]:
    """顯式啟停（運行時）；禁止串流／webhook 自動呼叫本端點。"""
    reg = get_registry()
    client = reg.get(name)
    if client is None:
        return {"ok": False, "error_code": "ERR_UNKNOWN_INTEGRATION"}
    object.__setattr__(client.http.config, "enabled", req.enabled)  # frozen dataclass：受控切換
    logger.info("整合 %s 已%s（顯式動作）", name, "啟用" if req.enabled else "停用")
    return {"ok": True, "name": name, "enabled": req.enabled}


def register_integrations(app: Any) -> None:
    app.include_router(router)
