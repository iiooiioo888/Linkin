"""OPC 路由 — WebSocket 订阅。"""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from opc_service.client import opc_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["OPC WebSocket"])


@router.websocket("/ws/subscribe")
async def ws_subscribe(websocket: WebSocket):
    """WebSocket 端点：订阅标签值变更。

    客户端发送 JSON 消息：
      {"action": "subscribe", "tag_names": ["Temperature", "Pressure"]}
      {"action": "unsubscribe"}

    服务器推送 JSON 消息：
      {"tag_name": "Temperature", "value": 25.5, "timestamp": "...", "status": "Good"}
    """
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    subscription_active = False

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"error": "无效的 JSON 格式"})
                )
                continue

            action = msg.get("action", "")

            if action == "subscribe":
                tag_names = msg.get("tag_names", [])
                if not tag_names:
                    await websocket.send_text(
                        json.dumps({"error": "tag_names 为必填"})
                    )
                    continue
                try:
                    await opc_client.subscribe(tag_names, queue)
                    subscription_active = True
                    await websocket.send_text(
                        json.dumps(
                            {
                                "status": "subscribed",
                                "tag_names": tag_names,
                            }
                        )
                    )
                    # 启动后台任务推送变更
                    asyncio.create_task(
                        _push_updates(websocket, queue)
                    )
                except Exception as exc:
                    await websocket.send_text(
                        json.dumps({"error": f"订阅失败：{exc}"})
                    )

            elif action == "unsubscribe":
                subscription_active = False
                await websocket.send_text(
                    json.dumps({"status": "unsubscribed"})
                )

            else:
                await websocket.send_text(
                    json.dumps({"error": f"未知动作：{action}"})
                )

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端已断开连接")
    finally:
        subscription_active = False


async def _push_updates(websocket: WebSocket, queue: asyncio.Queue):
    """从队列读取变更事件并推送给 WebSocket 客户端。"""
    try:
        while True:
            event = await queue.get()
            try:
                await websocket.send_text(
                    json.dumps(event, default=str)
                )
            except Exception:
                break
    except asyncio.CancelledError:
        pass