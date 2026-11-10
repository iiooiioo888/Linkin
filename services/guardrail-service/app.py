"""guardrail-service HTTP。check 只收 tool-gateway，approve 只收 api-gateway。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header
from guardrail_service import CALLER_APPROVE, CALLER_CHECK, approve_decision, check_decision
from pydantic import BaseModel, Field

app = FastAPI(title="guardrail-service", docs_url=None, redoc_url=None)


class CheckBody(BaseModel):
    tool: str = Field(min_length=1, max_length=64)
    args: dict[str, Any] = Field(default_factory=dict)
    tenant_id: str
    trace_id: str


class ApproveBody(BaseModel):
    decision_id: str
    approved: bool
    approver: str
    tenant_id: str
    trace_id: str
    note: str = ""


@app.get("/healthz")
@app.get("/readyz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> str:
    return "linkin_guardrail_up 1\n"


@app.post("/api/v1/guardrail/check")
def check(body: CheckBody, x_linkin_caller: str = Header(default="")) -> dict[str, Any]:
    caller = x_linkin_caller or ""
    if caller != CALLER_CHECK:
        return _denied("只有 tool-gateway 可以呼叫 check")
    row = check_decision(
        tool=body.tool,
        args=body.args,
        tenant_id=body.tenant_id,
        trace_id=body.trace_id,
        caller=CALLER_CHECK,
    )
    return {"ok": True, **row}


@app.post("/api/v1/guardrail/approve")
def approve(body: ApproveBody, x_linkin_caller: str = Header(default="")) -> dict[str, Any]:
    if (x_linkin_caller or "") != CALLER_APPROVE:
        return _denied("審批入口只接受 api-gateway")
    try:
        row = approve_decision(
            decision_id=body.decision_id,
            approved=body.approved,
            approver=body.approver,
            tenant_id=body.tenant_id,
            trace_id=body.trace_id,
            caller=CALLER_APPROVE,
        )
    except KeyError:
        return {"ok": False, "error_code": "not_found", "detail": "找不到決策"}
    return {"ok": True, **row}


def _denied(detail: str) -> dict[str, Any]:
    return {"ok": False, "error_code": "forbidden", "detail": detail}
