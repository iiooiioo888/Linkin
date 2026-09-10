"""整合層 HTTP API：狀態目錄＋召回編排＋顯式動作。

端點：
- ``GET  /integrations``：六個整合的啟用狀態與健康檢查
- ``GET  /integrations/catalog``：靜態目錄（顯示名／角色／預設埠）供 GUI
- ``POST /integrations/recall``：token 節省召回編排（ContextAssembler）
- ``POST /integrations/{name}/toggle``：運行時顯式啟停（寫審計軌跡）
- ``POST /integrations/yao/*``／``ouroboros/*``／``openpencil/*``：顯式動作

契約：召回結果只作為注入片段；生成一律走 ``call_llm``（C-LLM-001）。
啟用／動作皆為顯式；禁止串流／webhook 自動呼叫（C-INTEG-002）。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.integrations.base import IntegrationConfig
from backend.integrations.context_assembler import ContextAssembler, RecallPolicy
from backend.integrations.memos import MemosClient
from backend.integrations.openpencil import OpenPencilClient
from backend.integrations.openviking import OpenVikingClient
from backend.integrations.ouroboros import OuroborosClient
from backend.integrations.weknora import WeKnoraClient
from backend.integrations.yao import YaoClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["integrations"])

# ── GUI 靜態目錄（與客戶端對齊；不發網路請求）──

INTEGRATION_CATALOG: list[dict[str, Any]] = [
    {
        "name": "memos",
        "display_name": "MemOS",
        "role": "memory",
        "group": "recall",
        "summary": "長期記憶存取；召回取代完整歷史（token 節省主力）",
        "default_url": "http://localhost:8000",
        "env_enabled": "LINKIN_MEMOS_ENABLED",
        "env_url": "LINKIN_MEMOS_BASE_URL",
        "docs_url": "https://github.com/MemTensor/MemOS",
    },
    {
        "name": "openviking",
        "display_name": "OpenViking",
        "role": "context",
        "group": "recall",
        "summary": "上下文資料庫；L0 摘要 → L1 概覽分層載入",
        "default_url": "http://localhost:1933",
        "env_enabled": "LINKIN_OPENVIKING_ENABLED",
        "env_url": "LINKIN_OPENVIKING_BASE_URL",
        "docs_url": "https://github.com/volcengine/OpenViking",
    },
    {
        "name": "weknora",
        "display_name": "WeKnora",
        "role": "knowledge",
        "group": "recall",
        "summary": "企業級 RAG 知識庫；hybrid search／ask",
        "default_url": "http://localhost:8080",
        "env_enabled": "LINKIN_WEKNORA_ENABLED",
        "env_url": "LINKIN_WEKNORA_BASE_URL",
        "docs_url": "https://github.com/Tencent/WeKnora",
    },
    {
        "name": "yao",
        "display_name": "Yao",
        "role": "workspace",
        "group": "agent",
        "summary": "自架 agent 工作區與任務板；對話 → 任務須顯式建立",
        "default_url": "http://localhost:5099",
        "env_enabled": "LINKIN_YAO_ENABLED",
        "env_url": "LINKIN_YAO_BASE_URL",
        "docs_url": "https://github.com/YaoApp/yao",
    },
    {
        "name": "ouroboros",
        "display_name": "Ouroboros",
        "role": "agent_os",
        "group": "agent",
        "summary": "訪談 ambiguity 閘門／三階段評估／演化迴圈",
        "default_url": "http://localhost:8600",
        "env_enabled": "LINKIN_OUROBOROS_ENABLED",
        "env_url": "LINKIN_OUROBOROS_BASE_URL",
        "docs_url": "https://github.com/ouroboros-os/ouroboros",
    },
    {
        "name": "openpencil",
        "display_name": "OpenPencil",
        "role": "design",
        "group": "design",
        "summary": "AI-native Design-as-Code；prompt → 畫布須顯式觸發",
        "default_url": "http://localhost:4300",
        "env_enabled": "LINKIN_OPENPENCIL_ENABLED",
        "env_url": "LINKIN_OPENPENCIL_BASE_URL",
        "docs_url": "https://github.com/openpencil/openpencil",
    },
]

# ── 運行時單例（測試可經 build_registry 注入假 transport）──


def build_registry(**http_kwargs: Any) -> dict[str, Any]:
    """建立六個整合客戶端；``http_kwargs``（如假 transport）透傳給所有客戶端。"""
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
    meta = next((m for m in INTEGRATION_CATALOG if m["name"] == name), {})
    status: dict[str, Any] = {
        "name": name,
        "display_name": meta.get("display_name", name),
        "role": meta.get("role", ""),
        "group": meta.get("group", ""),
        "summary": meta.get("summary", ""),
        "docs_url": meta.get("docs_url", ""),
        "enabled": cfg.enabled,
        "base_url": cfg.base_url,
    }
    if cfg.enabled:
        if name in ("yao", "openpencil"):
            status["health"] = client.health()
        else:
            probe = client.http.get("health")
            status["health"] = {
                "ok": probe.ok,
                "reason_code": probe.reason_code,
                "latency_ms": probe.latency_ms,
            }
    else:
        status["health"] = {"ok": True, "enabled": False, "reason_code": "integration:disabled"}
    return status


def _require_client(name: str) -> Any | dict[str, Any]:
    client = get_registry().get(name)
    if client is None:
        return {"ok": False, "error_code": "ERR_UNKNOWN_INTEGRATION"}
    if not client.http.enabled:
        return {"ok": False, "error_code": "ERR_INTEGRATION_DISABLED", "name": name}
    return client


@router.get("/catalog")
def catalog() -> dict[str, Any]:
    """靜態目錄（不探測健康）；供 GUI 首屏渲染。"""
    return {"catalog": INTEGRATION_CATALOG}


@router.get("")
def list_integrations() -> dict[str, Any]:
    """整合目錄與健康狀態。"""
    items = [_status_of(name, client) for name, client in get_registry().items()]
    return {"integrations": items}


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


# ── Yao 顯式動作 ──


class YaoCreateTaskRequest(BaseModel):
    workspace_id: str
    title: str
    prompt: str
    agent_id: str = ""


@router.get("/yao/workspaces")
def yao_list_workspaces() -> dict[str, Any]:
    client = _require_client("yao")
    if isinstance(client, dict):
        return client
    resp = client.list_workspaces()
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


@router.get("/yao/workspaces/{workspace_id}/tasks")
def yao_list_tasks(workspace_id: str, status: str = "") -> dict[str, Any]:
    client = _require_client("yao")
    if isinstance(client, dict):
        return client
    resp = client.list_tasks(workspace_id, status=status)
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


@router.post("/yao/tasks")
def yao_create_task(req: YaoCreateTaskRequest) -> dict[str, Any]:
    """顯式建立任務（對話 → 任務板）；禁止串流自動呼叫。"""
    client = _require_client("yao")
    if isinstance(client, dict):
        return client
    resp = client.create_task(
        req.workspace_id, title=req.title, prompt=req.prompt, agent_id=req.agent_id
    )
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


# ── Ouroboros 顯式動作 ──


class OuroborosInterviewRequest(BaseModel):
    goal: str
    context: str = ""


class OuroborosAutoRequest(BaseModel):
    goal: str
    ambiguity: float = Field(ge=0.0, le=1.0)
    force: bool = False


class OuroborosEvaluateRequest(BaseModel):
    execution_id: str


@router.post("/ouroboros/interview")
def ouroboros_interview(req: OuroborosInterviewRequest) -> dict[str, Any]:
    client = _require_client("ouroboros")
    if isinstance(client, dict):
        return client
    resp = client.interview(req.goal, context=req.context)
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


@router.post("/ouroboros/auto")
def ouroboros_auto(req: OuroborosAutoRequest) -> dict[str, Any]:
    """顯式啟動 auto；本地 ambiguity 閘門阻擋（>0.2 且非 force）。"""
    client = _require_client("ouroboros")
    if isinstance(client, dict):
        return client
    return client.start_auto(req.goal, ambiguity=req.ambiguity, force=req.force)


@router.post("/ouroboros/evaluate")
def ouroboros_evaluate(req: OuroborosEvaluateRequest) -> dict[str, Any]:
    """顯式三階段評估；禁止串流完成自動觸發。"""
    client = _require_client("ouroboros")
    if isinstance(client, dict):
        return client
    return client.evaluate(req.execution_id)


# ── OpenPencil 顯式動作 ──


class OpenPencilGenerateRequest(BaseModel):
    prompt: str
    project_id: str = ""
    style: str = ""


@router.get("/openpencil/projects")
def openpencil_list_projects() -> dict[str, Any]:
    client = _require_client("openpencil")
    if isinstance(client, dict):
        return client
    resp = client.list_projects()
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


@router.post("/openpencil/generate")
def openpencil_generate(req: OpenPencilGenerateRequest) -> dict[str, Any]:
    """顯式觸發設計生成；禁止串流完成自動觸發。"""
    client = _require_client("openpencil")
    if isinstance(client, dict):
        return client
    resp = client.generate_design(req.prompt, project_id=req.project_id, style=req.style)
    return {"ok": resp.ok, "data": resp.data, "error_code": resp.error_code, "reason_code": resp.reason_code}


def register_integrations(app: Any) -> None:
    app.include_router(router)
