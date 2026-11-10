"""OpenAPI 3.1 草案。階段 0 不掛進現有 FastAPI。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from linkin_core.contracts.chat import ChatSseEvent, ChatStreamRequest
from linkin_core.contracts.common import ErrorBody
from linkin_core.contracts.guardrail import (
    GuardrailApproveRequest,
    GuardrailCheckRequest,
    GuardrailDecision,
)
from linkin_core.contracts.minecraft import MinecraftActionRequest, MinecraftActionResult
from linkin_core.contracts.opc import (
    OpcReadRequest,
    OpcReadResponse,
    OpcWriteAccepted,
    OpcWriteRequest,
)
from linkin_core.contracts.route import RouteDecision, RoutePreviewRequest
from linkin_core.contracts.tasks import TaskAccepted, TaskCreateRequest, TaskView
from linkin_core.contracts.tools import ToolInvokeRequest, ToolInvokeResponse
from linkin_core.contracts.version import CONTRACT_VERSION

_MODELS: tuple[type[BaseModel], ...] = (
    ErrorBody,
    RoutePreviewRequest,
    RouteDecision,
    ChatStreamRequest,
    ChatSseEvent,
    TaskCreateRequest,
    TaskAccepted,
    TaskView,
    ToolInvokeRequest,
    ToolInvokeResponse,
    GuardrailCheckRequest,
    GuardrailDecision,
    GuardrailApproveRequest,
    OpcReadRequest,
    OpcReadResponse,
    OpcWriteRequest,
    OpcWriteAccepted,
    MinecraftActionRequest,
    MinecraftActionResult,
)


def _schemas() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for model in _MODELS:
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        defs = schema.pop("$defs", {})
        out[model.__name__] = schema
        out.update(defs)
    return out


def _op(
    *,
    summary: str,
    body: str | None,
    response: str,
    status: str = "200",
    visibility: str = "public",
    deprecated: bool = False,
) -> dict[str, Any]:
    operation: dict[str, Any] = {
        "summary": summary,
        "deprecated": deprecated,
        "x-linkin-visibility": visibility,
        "responses": {
            status: {
                "description": summary,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{response}"},
                    }
                },
            },
            "400": {"$ref": "#/components/responses/Error"},
        },
    }
    if body:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{body}"},
                }
            },
        }
    return operation


def build_openapi() -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Linkin 服務契約",
            "version": CONTRACT_VERSION,
            "description": (
                "內網 BFF 與內部服務的草案。"
                "現有 /chat、/tasks 繼續由單體提供，此檔不取代實作。"
                "AI Hub 的 /api/v1/chat/completions 是另一條契約。"
            ),
        },
        "servers": [{"url": "https://linkin.internal"}],
        "tags": [
            {"name": "public"},
            {"name": "internal"},
            {"name": "legacy"},
        ],
        "paths": {
            "/api/v1/route-preview": {
                "post": _op(
                    summary="路由預覽",
                    body="RoutePreviewRequest",
                    response="RouteDecision",
                )
            },
            "/api/v1/chat/stream": {
                "post": _op(
                    summary="對話 SSE。首個事件為 route，其後為 token。",
                    body="ChatStreamRequest",
                    response="ChatSseEvent",
                )
            },
            "/api/v1/tasks": {
                "post": _op(
                    summary="受理公司任務",
                    body="TaskCreateRequest",
                    response="TaskAccepted",
                    status="202",
                )
            },
            "/api/v1/tasks/{task_id}": {
                "get": _op(summary="讀取任務", body=None, response="TaskView"),
            },
            "/api/v1/tools/{tool}/invoke": {
                "post": _op(
                    summary="內部工具呼叫",
                    body="ToolInvokeRequest",
                    response="ToolInvokeResponse",
                    visibility="internal",
                )
            },
            "/api/v1/guardrail/check": {
                "post": _op(
                    summary="護欄檢查",
                    body="GuardrailCheckRequest",
                    response="GuardrailDecision",
                    visibility="internal",
                )
            },
            "/api/v1/guardrail/approve": {
                "post": _op(
                    summary="人工審批 OPC 寫入或危險 Minecraft 動作",
                    body="GuardrailApproveRequest",
                    response="GuardrailDecision",
                    visibility="internal",
                )
            },
            "/api/v1/opc/read": {
                "get": {
                    "summary": "讀取 OPC 摘要",
                    "x-linkin-visibility": "internal",
                    "parameters": [
                        {
                            "name": "node_id",
                            "in": "query",
                            "required": True,
                            "schema": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 1,
                                "maxItems": 64,
                            },
                            "style": "form",
                            "explode": True,
                        },
                        {
                            "name": "tenant_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "trace_id",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                    ],
                    "responses": {
                        "200": {
                            "description": "讀取 OPC 摘要",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/OpcReadResponse"},
                                }
                            },
                        },
                        "400": {"$ref": "#/components/responses/Error"},
                    },
                }
            },
            "/api/v1/opc/write-request": {
                "post": _op(
                    summary="受理 OPC 寫入。必須帶 guardrail 決策。",
                    body="OpcWriteRequest",
                    response="OpcWriteAccepted",
                    status="202",
                    visibility="internal",
                )
            },
            "/api/v1/minecraft/action": {
                "post": _op(
                    summary="Minecraft 動作。危險動作必須帶 guardrail 決策。",
                    body="MinecraftActionRequest",
                    response="MinecraftActionResult",
                    visibility="internal",
                )
            },
            "/chat": {
                "post": _op(
                    summary="相容入口，轉到對話契約",
                    body="ChatStreamRequest",
                    response="ChatSseEvent",
                    visibility="legacy",
                    deprecated=True,
                )
            },
            "/chat/stream": {
                "post": _op(
                    summary="相容 SSE 入口",
                    body="ChatStreamRequest",
                    response="ChatSseEvent",
                    visibility="legacy",
                    deprecated=True,
                )
            },
            "/tasks": {
                "post": _op(
                    summary="相容任務入口",
                    body="TaskCreateRequest",
                    response="TaskAccepted",
                    status="202",
                    visibility="legacy",
                    deprecated=True,
                )
            },
            "/tasks/{task_id}": {
                "get": _op(
                    summary="相容任務讀取",
                    body=None,
                    response="TaskView",
                    visibility="legacy",
                    deprecated=True,
                )
            },
        },
        "components": {
            "schemas": _schemas(),
            "responses": {
                "Error": {
                    "description": "錯誤",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorBody"},
                        }
                    },
                }
            },
        },
    }
