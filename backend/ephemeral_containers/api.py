"""臨時容器任務 HTTP / WebSocket API。"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from backend.auth.gate import ws_authorized
from backend.ephemeral_containers.config import ephemeral_containers_enabled, image_allowlist
from backend.ephemeral_containers.broadcaster import container_task_broadcaster
from backend.ephemeral_containers.models import ContainerTaskCreate, ContainerTaskPublic
from backend.ephemeral_containers.store import container_task_store
from backend.ephemeral_containers.worker import container_task_worker

containers_router = APIRouter(prefix="/linkin/containers", tags=["linkin-containers"])


def _require_feature() -> None:
    if not ephemeral_containers_enabled():
        raise HTTPException(
            status_code=503,
            detail="臨時容器執行未啟用（設定 EVOL_EPHEMERAL_CONTAINERS=1）",
        )


@containers_router.get("/config")
async def containers_config():
    return {
        "enabled": ephemeral_containers_enabled(),
        "allowlist": sorted(image_allowlist()),
    }


@containers_router.post("/tasks")
async def create_container_task(body: ContainerTaskCreate, request: Request):
    _require_feature()
    user = getattr(request.state, "gate_user", "") or ""
    record = container_task_store.create(body, submitted_by=str(user))
    container_task_worker.enqueue(record.task_id)
    return {"task_id": record.task_id, "status": record.status}


@containers_router.get("/tasks/{task_id}")
async def get_container_task(task_id: str):
    _require_feature()
    record = container_task_store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    return ContainerTaskPublic.model_validate(record.to_dict())


@containers_router.get("/tasks/{task_id}/logs")
async def get_container_task_logs(task_id: str, tail: int = 5000):
    _require_feature()
    record = container_task_store.get(task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任務不存在")
    text = record.logs or ""
    if tail > 0 and len(text) > tail:
        text = text[-tail:]
    return {
        "task_id": task_id,
        "status": record.status,
        "logs": text,
        "truncated": record.logs_truncated,
    }


@containers_router.websocket("/tasks/{task_id}/ws")
async def container_task_ws(websocket: WebSocket, task_id: str):
    if not ephemeral_containers_enabled():
        await websocket.close(code=4503, reason="feature disabled")
        return
    if not ws_authorized(websocket):
        await websocket.close(code=4401, reason="unauthorized")
        return
    record = container_task_store.get(task_id)
    if record is None:
        await websocket.close(code=4004, reason="not found")
        return

    await websocket.accept()
    await container_task_broadcaster.subscribe(task_id, websocket)
    try:
        await websocket.send_json(
            {
                "task_id": task_id,
                "event": "snapshot",
                "data": record.to_dict(),
            }
        )
        if record.logs:
            await websocket.send_json(
                {
                    "task_id": task_id,
                    "event": "log",
                    "data": {"chunk": record.logs},
                }
            )
        while True:
            try:
                data = await websocket.receive_text()
                if data == "ping":
                    await websocket.send_json(
                        {"task_id": task_id, "event": "pong", "data": {}}
                    )
                elif data == "close":
                    break
            except WebSocketDisconnect:
                break
    finally:
        await container_task_broadcaster.unsubscribe(task_id, websocket)


def register_ephemeral_containers(app) -> None:
    app.include_router(containers_router)
