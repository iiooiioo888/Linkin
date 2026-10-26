"""OPC 寫入埠。只接受帶 guardrail.decision 簽章的請求，對應服務埠 8081。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from linkin_core.contracts.signatures import args_hash, verify_token
from opc_service.guard import write_guard

app = FastAPI(title="opc-write", docs_url=None, redoc_url=None)


class WriteBody(BaseModel):
    node_id: str = Field(min_length=1, max_length=256)
    value: float
    tenant_id: str
    trace_id: str
    guardrail_token: str = ""


@app.get("/healthz")
@app.get("/readyz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> str:
    return "linkin_opc_write_port_up 1\n"


@app.post("/api/v1/opc/write-request")
def write_request(body: WriteBody) -> dict[str, Any]:
    payload = {"node_id": body.node_id, "value": body.value}
    try:
        claims = verify_token(body.guardrail_token)
    except (ValueError, RuntimeError) as exc:
        return {"ok": False, "error_code": "guardrail_denied", "detail": str(exc)}
    if claims.get("tool") not in {"opc_write", "opc.write"} or claims.get("tenant_id") != body.tenant_id:
        return {"ok": False, "error_code": "guardrail_denied", "detail": "簽章與寫入不符"}
    if claims.get("args_hash") != args_hash(payload):
        return {"ok": False, "error_code": "guardrail_denied", "detail": "簽章與參數不符"}
    passed, message = write_guard.validate_write(body.node_id, body.value)
    if not passed:
        return {"ok": False, "error_code": "guardrail_denied", "detail": message}
    return {"ok": True, "status": "accepted", "request_id": body.trace_id, "detail": message}
