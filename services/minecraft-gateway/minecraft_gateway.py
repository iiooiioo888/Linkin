"""Minecraft 適配入口。敏感動作沒有放行簽章就拒絕。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from linkin_core.contracts.minecraft import minecraft_requires_guardrail
from linkin_core.contracts.signatures import args_hash, is_sensitive, verify_token

app = FastAPI(title="minecraft-gateway", docs_url=None, redoc_url=None)


class ActionBody(BaseModel):
    server_id: str = "default"
    session_id: str = "default"
    action: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    trace_id: str
    guardrail_token: str = ""


@app.get("/healthz")
@app.get("/readyz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> str:
    return "linkin_minecraft_gateway_up 1\n"


@app.post("/api/v1/minecraft/action")
def action(body: ActionBody) -> dict[str, Any]:
    if minecraft_requires_guardrail(body.action) or is_sensitive(body.action):
        try:
            claims = verify_token(body.guardrail_token, tenant_id=body.tenant_id)
        except (ValueError, RuntimeError) as exc:
            return {"ok": False, "error_code": "guardrail_denied", "detail": str(exc)}
        if claims.get("tool") != body.action:
            return {"ok": False, "error_code": "guardrail_denied", "detail": "簽章與動作不符"}
        if claims.get("args_hash") != args_hash(body.args):
            return {"ok": False, "error_code": "guardrail_denied", "detail": "簽章與參數不符"}
    return {"ok": True, "detail": "accepted", "session_id": body.session_id, "action": body.action}
