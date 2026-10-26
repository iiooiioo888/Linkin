"""tool-gateway HTTP。外部不直接呼叫，只收 api-gateway、seat-executor、context-service。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header
from pydantic import BaseModel, Field
from tool_gateway import AUDITS, invoke

app = FastAPI(title="tool-gateway", docs_url=None, redoc_url=None)
_CALLERS = {"api-gateway", "seat-executor", "context-service"}


class InvokeBody(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    trace_id: str
    guardrail_token: str = ""


def _missing(tool: str, args: dict[str, Any], token: str) -> dict[str, Any]:
    return {"ok": False, "detail": "適配器未設定", "tool": tool}


@app.get("/healthz")
@app.get("/readyz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> str:
    return f"linkin_tool_gateway_audits {len(AUDITS)}\n"


@app.post("/api/v1/tools/{tool}/invoke")
def invoke_route(
    tool: str,
    body: InvokeBody,
    x_linkin_caller: str = Header(default=""),
) -> dict[str, Any]:
    if x_linkin_caller not in _CALLERS:
        return {"ok": False, "error_code": "forbidden", "detail": "呼叫端不在允許清單"}
    return invoke(
        tool,
        body.args,
        {
            "tenant_id": body.tenant_id,
            "trace_id": body.trace_id,
            "guardrail_token": body.guardrail_token,
        },
        adapters={
            "opc_read": _missing,
            "opc_write": _missing,
            "minecraft": _missing,
            "local": _missing,
        },
        execute=False,
    )
