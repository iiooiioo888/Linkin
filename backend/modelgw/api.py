"""ModelGW FastAPI 掛載面（WIRE PR + P1/#130 回調 + G-OBS1 L2 讀點）。

路徑前綴 ``/modelgw``：
- GET  /modelgw/healthz
- GET  /modelgw/registry
- POST /modelgw/v1/admit
- POST /modelgw/v1/chat/completions
- POST /modelgw/internal/v1/deploy-callback  （HMAC＋冪等；不掛 AuthGate）
- GET  /api/internal/modelgw/path-counts     （G-OBS1 L2；loopback／token；禁 reset）

HTTP 映射（Core §8.1）：
- PROVISIONING → 503 + code=PROVISIONING（可選 Retry-After）
- UNSUPPORTED_MODEL／ADMISSION_REJECTED／MODEL_NOT_READY → 400 + body code
拒用 202／409／425（admit）；回調冪等衝突用 409。
不改 Hub 公開行為、不讀 HUB_CATALOG。
"""

from __future__ import annotations

import hmac
import ipaddress
import os
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from backend.modelgw.errors import CODE_PROVISIONING, ModelGWError
from backend.modelgw.runtime import (
    get_service,
    path_counts_snapshot,
    retry_after_seconds,
    wire_mode,
)

modelgw_router = APIRouter(prefix="/modelgw", tags=["modelgw"])
# G-OBS1 L2：受控內部讀點（與 /modelgw 並列；非 hub /metrics）
internal_modelgw_router = APIRouter(
    prefix="/api/internal/modelgw", tags=["modelgw-internal"]
)


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


def _callback_error_response(code: str, detail: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "type": f"https://modelgw.example.com/errors/{code}",
            "title": code,
            "code": code,
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
    # tenant_id 可選＋預設 ""；admit 實際走 get_for_tenant（缺列不回落）
    _tenant = str(body.get("tenant_id") if body.get("tenant_id") is not None else "")
    try:
        result = get_service().admit_or_raise(model_id, tenant_id=_tenant)
        status_val: str | None = None
        rec = getattr(result, "record", None)
        if rec is not None:
            st = getattr(rec, "status", None)
            if st is None:
                status_val = None
            elif hasattr(st, "value"):
                status_val = getattr(st, "value", None)
            else:
                status_val = str(st) if st is not None else None
        return JSONResponse(
            content={
                "decision": "ALLOW",
                "model_id": model_id,
                "tenant_id": _tenant,
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
    # tenant_id 可選＋預設 ""（與 admit 同形；不從 AuthGate／header 猜）
    _tenant = str(body.get("tenant_id") if body.get("tenant_id") is not None else "")

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
            tenant_id=_tenant,
        )
    except ModelGWError as exc:
        return problem_response(exc)
    except Exception as exc:
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
                "tenant_id": _tenant,
            },
        }
    )


@modelgw_router.post("/internal/v1/deploy-callback")
async def deploy_callback(request: Request) -> JSONResponse:
    """部署完成回調（internal）：HMAC 必填＋Idempotency-Key；寫 READY／FAILED／TERMINATING。

    不掛用戶 AuthGate；不做 Bearer。公網 443 本波不做（由部署面限制）。
    """
    from backend.modelgw.callback import CallbackError, process_deploy_callback
    from backend.modelgw.sql_registry import SqliteRegistry

    raw = await request.body()
    try:
        import json as _json

        body = _json.loads(raw.decode("utf-8") if raw else b"{}")
    except Exception:
        return _bad_request("JSON 無法解析")
    if not isinstance(body, dict):
        return _bad_request("Body 必須為 JSON 物件")

    svc = get_service()
    reg = svc.registry
    if not isinstance(reg, SqliteRegistry):
        return _callback_error_response(
            "REGISTRY_NOT_PERSISTENT",
            "部署回調需要 SQL Registry（設 MODELGW_DATABASE_URL／MODELGW_REGISTRY_BACKEND=sql）",
            503,
        )

    idem = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
    sig = request.headers.get("X-ModelGW-Signature") or request.headers.get(
        "x-modelgw-signature"
    )
    ts = request.headers.get("X-ModelGW-Timestamp") or request.headers.get(
        "x-modelgw-timestamp"
    )
    nonce = request.headers.get("X-ModelGW-Nonce") or request.headers.get(
        "x-modelgw-nonce"
    )

    try:
        result = process_deploy_callback(
            reg,
            body,
            idempotency_key=str(idem or ""),
            body_bytes=raw,
            signature_header=sig,
            timestamp=ts,
            nonce=nonce,
        )
    except CallbackError as exc:
        return _callback_error_response(exc.code, exc.detail, exc.http_status)

    return JSONResponse(content=result)


def _path_counts_token() -> str:
    return (os.getenv("MODELGW_PATH_COUNTS_TOKEN") or "").strip()


def _client_host(request: Request) -> str:
    """直連 peer；**不**信任 X-Forwarded-For（防偽造繞過 loopback 閘）。"""
    if request.client and request.client.host:
        return str(request.client.host)
    return ""


def _token_ok(request: Request) -> bool:
    expected = _path_counts_token()
    if not expected:
        return False
    got = (
        request.headers.get("X-ModelGW-Internal-Token")
        or request.headers.get("x-modelgw-internal-token")
        or ""
    ).strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)


def _allow_private() -> bool:
    raw = (os.getenv("MODELGW_PATH_COUNTS_ALLOW_PRIVATE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _is_path_counts_client_allowed(request: Request) -> bool:
    """受控內部讀點閘：預設僅 loopback；可選 private；token 可提升。

    - loopback → 允許
    - RFC1918／link-local private → 僅當 ALLOW_PRIVATE=1 **或** token 正確
    - 其餘（含非 IP／公網）→ 必須 token；無 token 設定則 fail-closed
    - **禁止**無防護公網裸洩
    """
    host = _client_host(request)
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        # ASGI TestClient 等非 IP host：僅 token
        return _token_ok(request)

    if addr.is_loopback:
        return True
    if addr.is_private or addr.is_link_local:
        return bool(_allow_private() or _token_ok(request))
    # 公網／其他：必須 token
    return _token_ok(request)


@internal_modelgw_router.get("/path-counts")
async def internal_path_counts(request: Request) -> JSONResponse:
    """G-OBS1 L2 受控內部讀點：進程內 path_counts 快照。

    語義＝自本進程啟動起；**不**呼叫 ``reset_path_counts``；
    **≠** hub ``GET /metrics``。多 worker 無匯總時 ``multi_worker_incomplete=true``。
    """
    if not _is_path_counts_client_allowed(request):
        return JSONResponse(
            status_code=403,
            content={
                "type": "https://modelgw.example.com/errors/PATH_COUNTS_FORBIDDEN",
                "title": "Forbidden",
                "code": "PATH_COUNTS_FORBIDDEN",
                "detail": "path-counts 僅 loopback／受控內網／token；禁公網裸洩",
            },
            media_type="application/problem+json",
        )
    # 刻意不呼叫 reset_path_counts
    body = path_counts_snapshot()
    body["hub_metrics_is_not_path_counts"] = True
    return JSONResponse(content=body)


def register_modelgw(app) -> None:
    """掛到 FastAPI app；不改 Hub 路由。"""
    app.include_router(modelgw_router)
    app.include_router(internal_modelgw_router)
