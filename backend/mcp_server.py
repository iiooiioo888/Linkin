"""Linkin 對外 MCP Server：把 EvoLoop 本身暴露成 MCP 工具集。

讓 Claude Desktop / Cursor / 其他 MCP 客戶端連進來：
派任務、查狀態、取消／續跑、讀技能庫、列公司工具。

兩種傳輸（同一份 JSON-RPC dispatcher）：
- stdio：`python -m backend.mcp_server_stdio`（本機子行程，免 token）
- HTTP ：POST /mcp-server（JSON-RPC over HTTP；需 Bearer token
  `EVOL_MCP_SERVER_TOKEN`，未設定時拒絕遠端連線）

安全界線：
- 不暴露任意 shell／檔案寫入；工具面只到「派任務＋查狀態＋讀技能」。
- submit 走既有 /tasks 管線（含 RAHO 審計與 OPC 護欄），不繞過。
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "linkin-evoloop"
SERVER_VERSION = "1.0"

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "linkin_submit_task",
        "description": "派一個任務給 Linkin EvoLoop 運行時（auto 自動選 simple/company/opc 路徑）。回傳 task_id 供輪詢。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "任務描述"},
                "strategy": {"type": "string", "enum": ["auto", "simple", "company"], "description": "執行策略，預設 auto"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "linkin_task_status",
        "description": "查詢任務狀態：status/phase/評分/錯誤/是否可續跑/答案摘要。",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "linkin_list_tasks",
        "description": "列出最近的任務摘要（id/狀態/階段/查詢前綴）。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "筆數，預設 20"}},
        },
    },
    {
        "name": "linkin_cancel_task",
        "description": "請求取消執行中的任務（協作式＋45 秒強制保險絲）。",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "linkin_resume_task",
        "description": "對有檢查點的公司任務斷點續跑。",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "linkin_skills_list",
        "description": "列出技能庫（注入角色提示詞的可重用知識）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "linkin_skill_get",
        "description": "讀取單一技能的完整內容。",
        "inputSchema": {
            "type": "object",
            "properties": {"skill_id": {"type": "string"}},
            "required": ["skill_id"],
        },
    },
    {
        "name": "linkin_tools_list",
        "description": "列出公司工具註冊表目前可用的工具（含 MCP 掛載的）。",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "linkin_health",
        "description": "運行時健康檢查。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def _text(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _err(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}], "isError": True}


def _call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    from backend.company.skills import skills_store
    from backend.company.tools import tool_registry
    from backend.services.task_manager import task_manager

    try:
        if name == "linkin_submit_task":
            query = str(args.get("query") or "").strip()
            if not query:
                return _err("query 不可為空")
            record = task_manager.create_task(query, str(args.get("strategy") or "auto"), "")
            task_manager.start_task_from_thread(record)
            return _text(json.dumps(
                {"task_id": record.task_id, "strategy": record.strategy,
                 "hint": "用 linkin_task_status 輪詢"},
                ensure_ascii=False))
        if name == "linkin_task_status":
            rec = task_manager.get_task(str(args.get("task_id") or ""))
            if rec is None:
                return _err("任務不存在")
            d = rec.to_dict(events_limit=0)
            return _text(json.dumps({
                "task_id": d.get("task_id"),
                "status": d.get("status"),
                "phase": d.get("phase"),
                "resolved_path": d.get("resolved_path"),
                "score": d.get("score"),
                "error": d.get("error"),
                "resumable": d.get("resumable"),
                "answer_preview": (d.get("answer") or "")[:1500],
                "kanban_counts": {k: len(v) for k, v in (d.get("kanban") or {}).items() if v},
            }, ensure_ascii=False))
        if name == "linkin_list_tasks":
            limit = max(1, min(int(args.get("limit") or 20), 100))
            rows = sorted(task_manager.tasks.values(), key=lambda r: r.created_at, reverse=True)[:limit]
            return _text(json.dumps([
                {"task_id": r.task_id, "status": r.status, "phase": r.phase,
                 "query": (r.query or "")[:80]}
                for r in rows
            ], ensure_ascii=False))
        if name == "linkin_cancel_task":
            ok, msg = task_manager.cancel_task(str(args.get("task_id") or ""))
            return _text(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False)) if ok else _err(msg)
        if name == "linkin_resume_task":
            ok, msg = task_manager.resume_task(str(args.get("task_id") or ""))
            return _text(json.dumps({"ok": ok, "message": msg}, ensure_ascii=False)) if ok else _err(msg)
        if name == "linkin_skills_list":
            return _text(json.dumps([
                {"id": s.id, "name": s.name, "enabled": s.enabled,
                 "description": s.description, "trigger": s.trigger}
                for s in skills_store.list()
            ], ensure_ascii=False))
        if name == "linkin_skill_get":
            skill = skills_store.get(str(args.get("skill_id") or ""))
            if skill is None:
                return _err("技能不存在")
            return _text(json.dumps(skill.to_dict(), ensure_ascii=False))
        if name == "linkin_tools_list":
            return _text(json.dumps([
                {"name": t.name, "description": t.description, "readonly": t.readonly}
                for t in tool_registry.list_tools()
            ], ensure_ascii=False))
        if name == "linkin_health":
            return _text(json.dumps({"status": "ok", "server": SERVER_NAME, "ts": time.time()}, ensure_ascii=False))
        return _err(f"未知工具：{name}")
    except Exception as exc:
        logger.warning("MCP server 工具 %s 執行失敗：%s", name, exc)
        return _err(f"工具執行失敗：{exc}")


def handle_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """處理單條 JSON-RPC 訊息；notification 回 None。"""
    method = msg.get("method", "")
    msg_id = msg.get("id")
    params = msg.get("params") or {}

    result: dict[str, Any]
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        result = {"tools": TOOL_SCHEMAS}
    elif method == "tools/call":
        result = _call_tool(str(params.get("name") or ""), dict(params.get("arguments") or {}))
    elif method == "ping":
        result = {}
    else:
        if msg_id is None:
            return None
        return {"jsonrpc": "2.0", "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"}}

    if msg_id is None:
        return None
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def http_token() -> str:
    return (os.getenv("EVOL_MCP_SERVER_TOKEN") or "").strip()


def check_http_token(provided: str | None) -> bool:
    """HTTP 傳輸的 token 檢查：未設定 token 時一律拒絕（fail-closed）。"""
    expected = http_token()
    if not expected:
        return False
    return bool(provided) and provided == expected
