"""技能庫（Skills）與 MCP 連線管理 API，含對外 MCP Server 端點。

自 backend.main 抽出；端點行為、模型與回應結構不變。
"""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.company.agent_skills_sync import sync_agent_skills
from backend.company.cli_runtimes import probe_all
from backend.company.mcp_clients import mcp_registry
from backend.company.skill_overrides import set_skill_enabled_override, skill_enabled_override
from backend.company.skills import skills_store
from backend.company.tools import tool_registry
from backend.mcp_server import check_http_token, handle_message
from backend.tenant.http import require_tenant_http

router = APIRouter(tags=["skills-mcp"])


# ═══════════════════════════════════════════════════════════
# 技能庫 API（Skills）— 注入角色提示詞的可重用知識
# ═══════════════════════════════════════════════════════════


class SkillBody(BaseModel):
    id: str | None = None
    name: str
    content: str
    description: str = ""
    trigger: str = ""
    enabled: bool = True
    roles: list[str] = []
    skill_budget: int = 2400


@router.get("/skills")
async def list_skills():
    """列出全部技能（enabled 含當前租戶覆寫）。"""
    skills_out: list[dict] = []
    for skill in skills_store.list():
        row = skill.to_dict()
        override = skill_enabled_override(skill.id)
        if override is not None:
            row["enabled"] = override
        skills_out.append(row)
    return {"skills": skills_out}


@router.post("/skills")
async def save_skill(body: SkillBody):
    """新增／更新技能（upsert）。"""
    require_tenant_http()
    try:
        skill = skills_store.upsert(
            body.name,
            body.content,
            skill_id=body.id,
            description=body.description,
            trigger=body.trigger,
            enabled=body.enabled,
            roles=body.roles,
            skill_budget=body.skill_budget,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "skill": skill.to_dict()}


@router.post("/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str):
    """啟用／停用技能（當前租戶覆寫，不改全域技能庫定義）。"""
    require_tenant_http()
    skill = skills_store.get(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="技能不存在")
    override = skill_enabled_override(skill_id)
    effective = override if override is not None else skill.enabled
    set_skill_enabled_override(skill_id, not effective)
    out = skill.to_dict()
    out["enabled"] = not effective
    return {"ok": True, "skill": out}


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """刪除技能。"""
    require_tenant_http()
    if not skills_store.delete(skill_id):
        raise HTTPException(status_code=404, detail="技能不存在")
    return {"ok": True, "deleted": skill_id}


@router.get("/skills/cli-runtimes")
async def list_skill_cli_runtimes():
    """檢查要用 CLI 才能執行的技能：命令是否在 PATH。不安裝、不讀憑證。"""
    return {"runtimes": await asyncio.to_thread(probe_all)}


@router.get("/skills/cli-hub")
async def list_cli_hub_catalog(action: str = "list", q: str = "", name: str = "", full: int = 0):
    """查 CLI-Anything 目錄。full=1 時列出每個分類的全部名稱。不安裝、不啟動。"""
    from backend.company.cli_anything import query_cli_hub

    per_category = 0 if full else 8
    limit = 40 if action.strip().lower() == "search" else 24
    return await asyncio.to_thread(
        query_cli_hub,
        action,
        q,
        name,
        limit=limit,
        per_category=per_category,
    )


@router.get("/skills/preview")
async def preview_skill_prompt(role: str | None = None):
    """預覽某角色實際會被注入的技能區塊（除錯用）。"""
    return {"role": role or "*", "prompt": skills_store.render_prompt(role)}


@router.post("/skills/sync-agent-packs")
async def sync_agent_skill_packs():
    """從 .agents/skills/ 與 agent_mcp_manifest 同步技能庫與 MCP 註冊表。"""
    report = await asyncio.to_thread(sync_agent_skills)
    return {"ok": True, **report.to_dict()}


# ═══════════════════════════════════════════════════════════
# MCP 連線管理 API — 通用 MCP server 註冊／探測／工具掛載
# ═══════════════════════════════════════════════════════════


class McpServerBody(BaseModel):
    id: str | None = None
    name: str
    transport: str = "stdio"
    command: str = ""
    env: dict[str, str] = {}
    url: str = ""
    headers: dict[str, str] = {}
    enabled: bool = True
    allowed_tools: list[str] = []
    readonly: bool = True
    timeout: float = 20.0


class McpCallBody(BaseModel):
    tool: str
    args: dict[str, Any] = {}


@router.get("/mcp/servers")
async def list_mcp_servers():
    """列出全部 MCP server 與最近探測結果。"""
    return {"servers": [s.to_dict() for s in mcp_registry.list()]}


@router.post("/mcp/servers")
async def save_mcp_server(body: McpServerBody):
    """新增／更新 MCP server（upsert）。"""
    try:
        srv = mcp_registry.upsert(
            body.name,
            body.transport,
            server_id=body.id,
            command=body.command,
            env=body.env,
            url=body.url,
            headers=body.headers,
            enabled=body.enabled,
            allowed_tools=body.allowed_tools,
            readonly=body.readonly,
            timeout=body.timeout,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "server": srv.to_dict()}


@router.post("/mcp/servers/{server_id}/toggle")
async def toggle_mcp_server(server_id: str):
    """啟用／停用 server。"""
    srv = mcp_registry.get(server_id)
    if not srv:
        raise HTTPException(status_code=404, detail="server 不存在")
    updated = mcp_registry.set_enabled(server_id, not srv.enabled)
    return {"ok": True, "server": updated.to_dict()}


@router.delete("/mcp/servers/{server_id}")
async def delete_mcp_server(server_id: str):
    """刪除 server。"""
    if not mcp_registry.delete(server_id):
        raise HTTPException(status_code=404, detail="server 不存在")
    return {"ok": True, "deleted": server_id}


@router.post("/mcp/servers/{server_id}/probe")
async def probe_mcp_server(server_id: str):
    """探測連線並回傳工具清單。"""
    try:
        result = await asyncio.to_thread(mcp_registry.probe, server_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="server 不存在") from None
    return result


@router.post("/mcp/servers/{server_id}/call")
async def call_mcp_tool(server_id: str, body: McpCallBody):
    """手動呼叫工具（測試用；角色執行走 tool_registry 閉環）。"""
    try:
        result = await asyncio.to_thread(mcp_registry.call, server_id, body.tool, body.args)
    except KeyError:
        raise HTTPException(status_code=404, detail="server 不存在")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
    return {"ok": True, "result": str(result)[:8000]}


@router.post("/mcp/mount")
async def mount_mcp_tools():
    """把啟用 server 的工具掛進公司工具註冊表（啟動時也會自動跑）。"""
    mounted = await asyncio.to_thread(mcp_registry.mount_tools, tool_registry, force=True)
    return {"ok": True, "mounted": mounted, "count": len(mounted)}


@router.get("/mcp/tools")
async def list_mcp_tools():
    """列出目前已掛載的 MCP 工具（含內建總數）。"""
    rows = [
        {"name": t.name, "description": t.description, "readonly": t.readonly}
        for t in tool_registry.list_tools()
        if t.name.startswith(tuple(f"{s.id}__" for s in mcp_registry.list()))
    ] if mcp_registry.list() else []
    return {"tools": rows, "total_registry": len(tool_registry.list_tools())}


# ═══════════════════════════════════════════════════════════
# 對外 MCP Server：把 Linkin 暴露成 MCP 工具集（Claude/Cursor 等）
# ═══════════════════════════════════════════════════════════


@router.post("/mcp-server")
async def mcp_server_endpoint(request: Request):
    """MCP streamable-HTTP 端點（JSON-RPC）。

    驗證：Bearer EVOL_MCP_SERVER_TOKEN；未設定 token 時 fail-closed 拒絕。
    接受單條訊息或批次陣列；notification 不佔回應位。
    """
    auth = request.headers.get("authorization", "")
    provided = auth[7:].strip() if auth.lower().startswith("bearer ") else None
    if not check_http_token(provided):
        raise HTTPException(
            status_code=401,
            detail="MCP server 需要 Bearer token（.env 的 EVOL_MCP_SERVER_TOKEN）",
        )
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="body 需為 JSON") from None
    messages = body if isinstance(body, list) else [body]
    replies = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        reply = await asyncio.to_thread(handle_message, msg)
        if reply is not None:
            replies.append(reply)
    if isinstance(body, list):
        return replies
    return replies[0] if replies else {}
