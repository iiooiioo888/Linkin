"""ModelGW FastAPI 掛載面（WIRE PR）。

路徑前綴 ``/modelgw``：
- GET  /modelgw/healthz
- GET  /modelgw/registry
- POST /modelgw/v1/admit
- POST /modelgw/v1/chat/completions

HTTP 映射（Core §8.1）：
- PROVISIONING → 503 + code=PROVISIONING（可選 Retry-After）
- UNSUPPORTED_MODEL／ADMISSION_REJECTED／MODEL_NOT_READY → 400 + body code
拒用 202／409／425。不改 Hub 公開行為、不讀 HUB_CATALOG。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.modelgw.errors import CODE_PROVISIONING, ModelGWError
from backend.modelgw.runtime import get_service, retry_after_seconds, wire_mode

modelgw_router = APIRouter(prefix="/modelgw", tags=["modelgw"])


def problem_response(exc: ModelGWError) -> JSONResponse:
    status = int(exc.http_hint or 400)
    if exc.code == CODE_PROVISIONING:
        status = 503
    headers: dict[str, str] = {}
    if status == 503 and exc.code == CODE_PROVISIONING:
        headers["Retry-After"] = retry_after_seconds()
    return JSONResponse(
        status_code=status,
        content=exc.to_problem(),
        media_type="application/problem+json",
        headers=headers,
    )


def _bad_request(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={
            "type": "https://modelgw.example.com/errors/BAD_REQUEST",
            "title": "Bad Request",
            "code": "BAD_REQUEST",
            "detail": detail,
        },
        media_type="application/problem+json",
    )


async def _read_json_object(request: Request) -> dict[str, Any] | JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _bad_request("JSON 無法解析")
    if not isinstance(body, dict):
        return _bad_request("Body 必須為 JSON 物件")
    return body


@modelgw_router.get("/healthz")
async def healthz() -> dict[str, Any]:
    svc = get_service()
    return {
        "status": "ok",
        "service": "modelgw",
        "wire_mode": wire_mode(),
        "registry_size": len(svc.registry.all()),
        "ready_count": len(svc.registry.ready()),
    }


@modelgw_router.get("/registry")
async def list_registry() -> dict[str, Any]:
    svc = get_service()
    return {
        "wire_mode": wire_mode(),
        "models": [r.to_dict() for r in svc.registry.all()],
    }


@modelgw_router.post("/v1/admit")
async def admit_endpoint(request: Request) -> JSONResponse:
    body = await _read_json_object(request)
    if isinstance(body, JSONResponse):
        return body
    model_id = str(body.get("model_id") or body.get("model") or "").strip()
    if not model_id:
        return _bad_request("缺少 model_id")
    try:
        result = get_service().admit_or_raise(model_id)
        status_val = None
        rec = getattr(result, "record", None)
        if rec is not None:
            st = getattr(rec, "status", None)
            status_val = st.value if hasattr(st, "value") else st
        return JSONResponse(
            content={
                "decision": "ALLOW",
                "model_id": model_id,
                "code": None,
                "record_status": status_val,
            }
        )
    except ModelGWError as exc:
        return problem_response(exc)


@modelgw_router.post("/v1/chat/completions")
async def chat_completions(request: Request) -> JSONResponse:
    """薄包裝：準入 → 選路 → 呼叫注入 llm（預設 core.llm.call_llm）。"""
    body = await _read_json_object(request)
    if isinstance(body, JSONResponse):
        return body
    model_id = str(body.get("model") or body.get("model_id") or "").strip()
    messages = body.get("messages")
    if not model_id:
        return _bad_request("缺少 model")
    if not isinstance(messages, list) or not messages:
        return _bad_request("messages 不可為空")

    extras_raw = body.get("failover_models") or body.get("extras") or []
    extras = [str(x).strip() for x in extras_raw if str(x).strip()] if isinstance(extras_raw, list) else []

    def llm_for_invoke(*, prompt: str, model: str, messages: list | None = None, **kwargs: Any) -> str:
        from backend.core.llm import call_llm

        system = None
        if messages:
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "system":
                    system = str(m.get("content") or "")
                    break
        return call_llm(prompt or "", system=system, model=model)

    try:
        result = get_service().invoke_chat(
            model_id,
            [m for m in messages if isinstance(m, dict)],
            llm_for_invoke,
            extras=extras,
        )
    except ModelGWError as exc:
        return problem_response(exc)
    except Exception as exc:  # 上游／LiteLLM 錯誤
        return JSONResponse(
            status_code=502,
            content={
                "type": "https://modelgw.example.com/errors/UPSTREAM_FAILED",
                "title": "Upstream Failed",
                "code": "UPSTREAM_FAILED",
                "detail": str(exc)[:120],
            },
            media_type="application/problem+json",
        )

    return JSONResponse(
        content={
            "id": "modelgw-chat",
            "object": "chat.completion",
            "model": result.model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result.text},
                    "finish_reason": "stop",
                }
            ],
            "modelgw": {
                "failover_hops": result.failover_hops,
                "skipped_open": result.skipped_open,
                "wire_mode": wire_mode(),
            },
        }
    )


def register_modelgw(app) -> None:
    """掛到 FastAPI app；不改 Hub 路由。"""
    app.include_router(modelgw_router)
