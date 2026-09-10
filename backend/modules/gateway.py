"""統一模組業務 API 閘道。

後續世界／整合模組只要：
1. ``register_module(ModuleSpec)``（capabilities.routes 為允許清單）
2. 把實作掛在 ``api_prefix``（Minecraft 為 ``/linkin``）

客戶端一律走 ``/modules/{id}/api/{path}``，閘道校驗後轉發到該模組
``api_prefix``，寫入仍經原護欄，不另開旁路。
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from starlette.responses import Response

from backend.modules.registry import ModuleSpec

_HOP_BY_HOP = {"content-length", "transfer-encoding"}


def _as_header_map(raw: Any) -> dict[str, str]:
    """ASGI ``send`` 的 headers 是 ``[(bytes, bytes), ...]``；Starlette Response 要 Mapping。"""
    pairs: list[tuple[Any, Any]] = []
    if isinstance(raw, dict):
        pairs = list(raw.items())
    elif isinstance(raw, (list, tuple)):
        for row in raw:
            if isinstance(row, (list, tuple)) and len(row) >= 2:
                pairs.append((row[0], row[1]))
    out: dict[str, str] = {}
    for key, value in pairs:
        k = key.decode("latin-1") if isinstance(key, (bytes, bytearray)) else str(key)
        if k.lower() in _HOP_BY_HOP:
            continue
        v = value.decode("latin-1") if isinstance(value, (bytes, bytearray)) else str(value)
        out[k] = v
    return out


def gateway_prefix(module_id: str) -> str:
    return f"/modules/{module_id}/api"


def normalize_module_path(path: str) -> str:
    rel = "/" + (path or "").strip().lstrip("/")
    if rel != "/":
        rel = rel.rstrip("/") or "/"
    return rel


def path_allowed(spec: ModuleSpec, path: str) -> bool:
    """允許 capabilities.routes 的精確或子路徑（例如 /npcs/{id}/dialogue）。"""
    rel = normalize_module_path(path)
    if rel == "/":
        return False
    for route in spec.allowed_routes():
        base = normalize_module_path(route)
        if rel == base or rel.startswith(base.rstrip("/") + "/"):
            return True
    return False


async def forward_to_prefix(app: Any, request: Request, dest_path: str) -> Response:
    """同進程 ASGI 轉發，保留 method／query／body，避免 HTTP 迴圈。"""
    body = await request.body()
    scope = dict(request.scope)
    scope["path"] = dest_path
    scope["raw_path"] = dest_path.encode("utf-8")
    chunks: list[bytes] = []
    status_code = 500
    resp_headers: Any = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        nonlocal status_code, resp_headers
        kind = message.get("type")
        if kind == "http.response.start":
            status_code = int(message.get("status") or 500)
            resp_headers = message.get("headers") or []
        elif kind == "http.response.body":
            chunks.append(message.get("body") or b"")

    await app(scope, receive, send)
    return Response(
        content=b"".join(chunks),
        status_code=status_code,
        headers=_as_header_map(resp_headers),
    )


async def dispatch_module_api(spec: ModuleSpec, request: Request, path: str) -> Response:
    rel = normalize_module_path(path)
    if not path_allowed(spec, rel):
        raise HTTPException(status_code=404, detail=f"模組能力路徑不存在：{spec.id}{rel}")
    prefix = (spec.api_prefix or "").rstrip("/")
    if not prefix.startswith("/"):
        raise HTTPException(status_code=500, detail=f"模組 {spec.id} 未設定 api_prefix")
    dest = f"{prefix}{rel}"
    if dest.startswith("/modules/"):
        raise HTTPException(status_code=500, detail="模組 api_prefix 不可指向閘道本身")
    return await forward_to_prefix(request.app, request, dest)
