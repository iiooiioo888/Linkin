"""AI Hub FastAPI 路由：/api/v1/chat/completions 與 /api/v1/agent/tasks。"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

from backend.billing.context import billing_user_id
from backend.hub.catalog import catalog_payload
from backend.hub.errors import HubError
from backend.hub.runtime import runtime
from backend.hub.service import (
    authenticate,
    complete_chat,
    create_agent_task,
    get_agent_task,
)

hub_router = APIRouter(prefix="/api/v1", tags=["ai-hub"])
compat_router = APIRouter(prefix="/v1", tags=["ai-hub-nginx-compat"])
health_router = APIRouter(tags=["ai-hub-health"])

_TASK_ID_RE = re.compile(r"^agt_[0-9A-HJKMNP-TV-Z]{26}$")
_ALLOWED_CT = {
    "application/json",
    "application/json; charset=utf-8",
    "application/json;charset=utf-8",
}


def problem_response(exc: HubError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_problem(),
        media_type="application/problem+json",
        headers=exc.headers,
    )


def _check_content_type(request: Request) -> None:
    ct = (request.headers.get("content-type") or "").strip().lower()
    if ct not in _ALLOWED_CT:
        raise HubError(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type 必須為 application/json")


def _region(x_client_region: str | None, cf_ipcountry: str | None) -> str:
    raw = (x_client_region or cf_ipcountry or "ZZ").strip().upper()
    if len(raw) != 2:
        return "ZZ"
    return raw


async def _read_body(request: Request) -> dict[str, Any]:
    _check_content_type(request)
    try:
        data = await request.json()
    except json.JSONDecodeError as exc:
        raise HubError(400, "BAD_REQUEST", "JSON 無法解析") from exc
    if not isinstance(data, dict):
        raise HubError(400, "BAD_REQUEST", "Body 必須為 JSON 物件")
    return data


def _strategy(header: str | None, body: dict[str, Any]) -> str:
    value = header or body.get("routing_strategy") or "quality_first"
    return str(value)


async def _chat_impl(
    request: Request,
    authorization: str | None,
    x_routing_strategy: str | None,
    x_failover_config: str | None,
    x_request_id: str | None,
    x_client_region: str | None,
    cf_ipcountry: str | None,
) -> JSONResponse:
    try:
        user = authenticate(authorization)
        body = await _read_body(request)
        request_id = x_request_id or str(uuid.uuid4())
        billing_token = billing_user_id.set(f"hub:{user.id}")
        try:
            payload = complete_chat(
                user,
                body,
                strategy=_strategy(x_routing_strategy, body),
                region=_region(x_client_region, cf_ipcountry),
                failover_raw=x_failover_config,
                request_id=request_id,
            )
        finally:
            billing_user_id.reset(billing_token)
        headers = {
            "X-Request-Id": request_id,
            "X-Trace-Id": request_id.replace("-", "")[:32].ljust(32, "0"),
            "X-Chosen-Provider": str(payload.get("chosen_provider") or ""),
            "X-Cost-Usd": f"{payload.get('cost_usd', 0):.6f}",
            "X-Latency-Ms": str(payload.get("latency_ms") or 0),
            "X-Hub-Cache": str(payload.get("cache") or "MISS"),
            "X-RateLimit-Remaining": "47",
        }
        return JSONResponse(content=payload, headers=headers)
    except HubError as exc:
        return problem_response(exc)


async def _create_task_impl(
    request: Request,
    authorization: str | None,
    x_routing_strategy: str | None,
    x_failover_config: str | None,
    x_request_id: str | None,
    x_client_region: str | None,
    cf_ipcountry: str | None,
    idempotency_key: str | None,
) -> JSONResponse:
    try:
        user = authenticate(authorization)
        body = await _read_body(request)
        request_id = x_request_id or str(uuid.uuid4())
        billing_token = billing_user_id.set(f"hub:{user.id}")
        try:
            task = create_agent_task(
                user,
                body,
                strategy=_strategy(x_routing_strategy, body),
                region=_region(x_client_region, cf_ipcountry),
                failover_raw=x_failover_config,
                idempotency_key=idempotency_key,
                request_id=request_id,
            )
        finally:
            billing_user_id.reset(billing_token)
        body_out = {
            "task_id": task.task_id,
            "status": "queued" if task.status == "queued" else task.status,
            "poll_url": f"/api/v1/agent/tasks/{task.task_id}",
            "eta_ms": 15000,
        }
        # 同步執行完成時仍先符合建立契約：若已 succeeded 則直接反映
        if task.status == "queued":
            status_code = 202
        elif task.status == "succeeded":
            body_out["status"] = "queued"
            status_code = 202
        else:
            status_code = 202
            body_out["status"] = "queued"
        return JSONResponse(status_code=status_code, content=body_out)
    except HubError as exc:
        return problem_response(exc)


async def _get_task_impl(
    task_id: str,
    authorization: str | None,
) -> JSONResponse:
    try:
        if not _TASK_ID_RE.match(task_id):
            raise HubError(400, "BAD_REQUEST", "task_id 格式不合法")
        user = authenticate(authorization)
        task = get_agent_task(user, task_id)
        payload: dict[str, Any] = {
            "task_id": task.task_id,
            "status": task.status,
            "progress_pct": task.progress_pct,
            "chosen_provider": task.chosen_provider or None,
            "cost_usd": task.cost_usd,
            "latency_ms": task.latency_ms,
            "trace_id": task.trace_id,
        }
        if task.result:
            payload["result"] = task.result
        if task.error_code:
            payload["error"] = {"code": task.error_code, "detail": task.error_detail}
        return JSONResponse(content=payload)
    except HubError as exc:
        return problem_response(exc)


def _chat_route():
    async def chat(
        request: Request,
        authorization: str | None = Header(default=None),
        x_routing_strategy: str | None = Header(default=None),
        x_failover_config: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_client_region: str | None = Header(default=None),
        cf_ipcountry: str | None = Header(default=None, alias="CF-IPCountry"),
    ):
        return await _chat_impl(
            request,
            authorization,
            x_routing_strategy,
            x_failover_config,
            x_request_id,
            x_client_region,
            cf_ipcountry,
        )

    return chat


def _create_task_route():
    async def create_task(
        request: Request,
        authorization: str | None = Header(default=None),
        x_routing_strategy: str | None = Header(default=None),
        x_failover_config: str | None = Header(default=None),
        x_request_id: str | None = Header(default=None),
        x_client_region: str | None = Header(default=None),
        cf_ipcountry: str | None = Header(default=None, alias="CF-IPCountry"),
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ):
        return await _create_task_impl(
            request,
            authorization,
            x_routing_strategy,
            x_failover_config,
            x_request_id,
            x_client_region,
            cf_ipcountry,
            idempotency_key,
        )

    return create_task


def _get_task_route():
    async def get_task(task_id: str, authorization: str | None = Header(default=None)):
        return await _get_task_impl(task_id, authorization)

    return get_task


hub_router.add_api_route(
    "/chat/completions", _chat_route(), methods=["POST"], name="hub_chat"
)
hub_router.add_api_route(
    "/agent/tasks", _create_task_route(), methods=["POST"], name="hub_create_task"
)
hub_router.add_api_route(
    "/agent/tasks/{task_id}", _get_task_route(), methods=["GET"], name="hub_get_task"
)
compat_router.add_api_route(
    "/chat/completions", _chat_route(), methods=["POST"], name="hub_chat_compat"
)
compat_router.add_api_route(
    "/agent/tasks", _create_task_route(), methods=["POST"], name="hub_create_task_compat"
)
compat_router.add_api_route(
    "/agent/tasks/{task_id}",
    _get_task_route(),
    methods=["GET"],
    name="hub_get_task_compat",
)


@health_router.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "service": "ai-hub-core",
        "catalog_size": 9,
        "cache_hit_rate": runtime.cache.hit_rate(),
    }


@health_router.get("/metrics")
async def metrics():
    return {
        "upstream_calls": len(runtime.upstream_calls),
        "call_logs": len(runtime.store.call_logs),
        "cache_hits": runtime.cache.hits,
        "cache_misses": runtime.cache.misses,
        "cache_hit_rate": runtime.cache.hit_rate(),
        "provider_metrics": runtime.store.provider_metrics,
        "circuits": runtime.circuits.snapshot(),
    }


def _catalog_route():
    async def catalog(authorization: str | None = Header(default=None)):
        try:
            authenticate(authorization)
            return catalog_payload()
        except HubError as exc:
            return problem_response(exc)

    return catalog


hub_router.add_api_route("/catalog", _catalog_route(), methods=["GET"], name="hub_catalog")
compat_router.add_api_route(
    "/catalog", _catalog_route(), methods=["GET"], name="hub_catalog_compat"
)


def register_hub(app) -> None:
    app.include_router(hub_router)
    app.include_router(compat_router)
    app.include_router(health_router)
    from backend.hub.probe import maybe_start_probe

    maybe_start_probe()
