"""Minecraft MCP 橋接層（MineMCP JSON-RPC）。

將 Paper 服務端 MineMCP 的操作能力封裝成公司運行時可調用的工具。
遠端協定對齊 AxenoDev/MineMCP：JSON-RPC `tools/call`，Token 走 URL 參數。
放置方塊的遠端工具名是 MineMCP 的 `pose_block`（非 place_block）。

未啟用或無 Token 時走乾跑，不連真實伺服器，測試無需 Minecraft。
寫入前必須經過本模組允許清單與靈境鐵律，禁止把檔案系統工具暴露給角色。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:3000"
DEFAULT_RPC_PATH = "/sse"
DEFAULT_WORLD = "world"
DEFAULT_TIMEOUT = 30.0
DEFAULT_AUDIT = Path("backend/data/linkin/mcp_audit.jsonl")
MAX_AUDIT_RECENT = 40

# 對公司角色暴露的工具名（place_block 為對內名稱，遠端映射 pose_block）
PLACE_BLOCK = "place_block"
POSE_BLOCK = "pose_block"
BREAK_BLOCK = "break_block"
FILL_BLOCK = "fill_block"
EXECUTE_COMMAND = "execute_command"
GET_PLAYER = "get_player"
GET_ONLINE_PLAYERS = "get_online_players"

COMPANY_TOOL_NAMES: tuple[str, ...] = (
    PLACE_BLOCK,
    POSE_BLOCK,
    BREAK_BLOCK,
    FILL_BLOCK,
    EXECUTE_COMMAND,
    GET_PLAYER,
    GET_ONLINE_PLAYERS,
)

# MineMCP 遠端名稱
REMOTE_TOOL_NAMES: dict[str, str] = {
    PLACE_BLOCK: "pose_block",
    POSE_BLOCK: "pose_block",
    BREAK_BLOCK: "break_block",
    FILL_BLOCK: "fill_block",
    EXECUTE_COMMAND: "execute_command",
    GET_PLAYER: "get_player",
    GET_ONLINE_PLAYERS: "get_online_players",
}

# 即使 LLM 試圖走通用呼叫，也不得把檔案工具交給角色
FILE_REMOTE_TOOLS = frozenset(
    {
        "read_file",
        "write_file",
        "read_file_base64",
        "write_file_base64",
        "list_directory",
    }
)

_TRUE = {"1", "true", "yes", "on"}

_MC_EXPLICIT_RE = re.compile(
    r"(minecraft|minemcp|pose_block|place_block|fill_block|break_block|"
    r"get_player|get_online_players)",
    re.IGNORECASE,
)
_MC_COORD_RE = re.compile(r"\(?\s*-?\d+(?:\.\d+)?\s*[,，\s]\s*-?\d+(?:\.\d+)?\s*[,，\s]\s*-?\d+(?:\.\d+)?")
_MC_BLOCK_RE = re.compile(
    r"(方块|方塊|钻石|鑽石|橡木|石英|放置|破坏|破壞|填满|填滿|玩家信息|玩家資訊)",
    re.IGNORECASE,
)

_MATERIAL_ALIASES: dict[str, str] = {
    "钻石块": "DIAMOND_BLOCK",
    "鑽石塊": "DIAMOND_BLOCK",
    "钻石": "DIAMOND_BLOCK",
    "鑽石": "DIAMOND_BLOCK",
    "金块": "GOLD_BLOCK",
    "金塊": "GOLD_BLOCK",
    "铁块": "IRON_BLOCK",
    "鐵塊": "IRON_BLOCK",
    "橡木板": "OAK_PLANKS",
    "石头": "STONE",
    "石頭": "STONE",
    "石英": "QUARTZ_BLOCK",
    "铜块": "COPPER_BLOCK",
    "銅塊": "COPPER_BLOCK",
    "苔石": "MOSSY_COBBLESTONE",
    "苔藓": "MOSS_BLOCK",
    "苔蘚": "MOSS_BLOCK",
}

_rpc_ids = count(1)
_rpc_lock = threading.Lock()
_audit_lock = threading.Lock()


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def _next_rpc_id() -> int:
    with _rpc_lock:
        return next(_rpc_ids)


@dataclass(frozen=True)
class MinecraftMcpConfig:
    enabled: bool
    url: str
    token: str
    rpc_path: str
    world: str
    timeout: float
    audit_path: Path
    allow_files: bool
    max_fill: int

    @property
    def live(self) -> bool:
        return self.enabled and bool(self.token)

    @property
    def dry_run(self) -> bool:
        return not self.live

    @property
    def public_url(self) -> str:
        parsed = urlparse(self.url)
        host = parsed.netloc or parsed.path or self.url
        return f"{parsed.scheme or 'http'}://{host}{self.rpc_path}"


def load_config() -> MinecraftMcpConfig:
    timeout_raw = os.getenv("EVOL_MC_MCP_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        timeout = float(timeout_raw)
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    max_fill_raw = os.getenv("EVOL_MC_MCP_MAX_FILL", "5000")
    try:
        max_fill = int(max_fill_raw)
    except ValueError:
        max_fill = 5000
    audit = os.getenv("EVOL_MC_MCP_AUDIT_PATH", "").strip()
    return MinecraftMcpConfig(
        enabled=_env_flag("EVOL_MC_MCP_ENABLED", False),
        url=(os.getenv("EVOL_MC_MCP_URL") or DEFAULT_URL).strip().rstrip("/"),
        token=(os.getenv("EVOL_MC_MCP_TOKEN") or "").strip(),
        rpc_path=(os.getenv("EVOL_MC_MCP_RPC_PATH") or DEFAULT_RPC_PATH).strip() or DEFAULT_RPC_PATH,
        world=(os.getenv("EVOL_MC_MCP_WORLD") or DEFAULT_WORLD).strip() or DEFAULT_WORLD,
        timeout=max(3.0, min(timeout, 120.0)),
        audit_path=Path(audit) if audit else DEFAULT_AUDIT,
        allow_files=_env_flag("EVOL_MC_MCP_ALLOW_FILES", False),
        max_fill=max(1, min(max_fill, 5000)),
    )


def is_minecraft_control_query(query: str) -> bool:
    """查詢是否在指揮 Minecraft 世界（座標+方塊，或明示 MCP 工具名）。"""
    text = query or ""
    if _MC_EXPLICIT_RE.search(text):
        return True
    return bool(_MC_COORD_RE.search(text) and _MC_BLOCK_RE.search(text))


def normalize_material(material: str) -> str:
    raw = (material or "").strip()
    if not raw:
        return "STONE"
    alias = _MATERIAL_ALIASES.get(raw) or _MATERIAL_ALIASES.get(raw.lower())
    if alias:
        return alias
    slug = raw.replace(" ", "_").replace("-", "_").upper()
    slug = re.sub(r"[^A-Z0-9_]", "", slug)
    return slug or "STONE"


def parse_xyz(location: Any) -> tuple[int, int, int] | None:
    if isinstance(location, (list, tuple)) and len(location) >= 3:
        try:
            return int(location[0]), int(location[1]), int(location[2])
        except (TypeError, ValueError):
            return None
    if isinstance(location, dict):
        try:
            return int(location["x"]), int(location["y"]), int(location["z"])
        except (KeyError, TypeError, ValueError):
            return None
    text = str(location or "").strip()
    nums = re.findall(r"-?\d+", text)
    if len(nums) >= 3:
        return int(nums[0]), int(nums[1]), int(nums[2])
    return None


def fill_volume(x1: int, y1: int, z1: int, x2: int, y2: int, z2: int) -> int:
    return (abs(int(x2) - int(x1)) + 1) * (abs(int(y2) - int(y1)) + 1) * (abs(int(z2) - int(z1)) + 1)


def _rpc_endpoint(cfg: MinecraftMcpConfig) -> str:
    path = cfg.rpc_path if cfg.rpc_path.startswith("/") else f"/{cfg.rpc_path}"
    url = f"{cfg.url}{path}"
    if cfg.token:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}token={cfg.token}"
    return url


def _append_audit(record: dict[str, Any], cfg: MinecraftMcpConfig | None = None) -> None:
    cfg = cfg or load_config()
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **record,
    }
    try:
        path = cfg.audit_path
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(payload, ensure_ascii=False)
        with _audit_lock, path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        logger.warning("Minecraft MCP 審計寫入失敗：%s", exc)


def recent_audit(limit: int = 20, cfg: MinecraftMcpConfig | None = None) -> list[dict[str, Any]]:
    cfg = cfg or load_config()
    path = cfg.audit_path
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines[-max(1, min(limit, MAX_AUDIT_RECENT)) :]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _extract_rpc_payload(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict):
        return {"ok": False, "error": f"非 JSON 物件回應：{body!r}"[:300]}
    if body.get("error"):
        err = body["error"]
        if isinstance(err, dict):
            return {"ok": False, "error": str(err.get("message") or err)}
        return {"ok": False, "error": str(err)}
    result = body.get("result", body)
    text = ""
    if isinstance(result, dict):
        content = result.get("content")
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            text = "\n".join(parts)
    return {
        "ok": True,
        "result": result,
        "text": text,
        "raw": body,
    }


def jsonrpc_request(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    cfg: MinecraftMcpConfig | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """對 MineMCP 發送 JSON-RPC。測試可注入 httpx.Client。"""
    cfg = cfg or load_config()
    payload = {
        "jsonrpc": "2.0",
        "id": _next_rpc_id(),
        "method": method,
        "params": params or {},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.token:
        headers["Authorization"] = f"Bearer {cfg.token}"
    url = _rpc_endpoint(cfg)
    owns_client = client is None
    if owns_client:
        client = httpx.Client(timeout=cfg.timeout)
    try:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        try:
            body = response.json()
        except json.JSONDecodeError:
            return {"ok": False, "error": f"非 JSON 回應：{response.text[:300]}"}
        parsed = _extract_rpc_payload(body)
        parsed["http_status"] = response.status_code
        return parsed
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"MCP HTTP 失敗：{exc}"}
    finally:
        if owns_client:
            client.close()


def _deny_file_tool(remote_name: str, cfg: MinecraftMcpConfig) -> dict[str, Any] | None:
    if remote_name in FILE_REMOTE_TOOLS and not cfg.allow_files:
        return {
            "ok": False,
            "error": f"已封鎖檔案系統工具 {remote_name}（預設不對靈境角色開放）",
            "code": "file_tool_blocked",
        }
    return None


def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    *,
    cfg: MinecraftMcpConfig | None = None,
    client: httpx.Client | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    """通用 MCP tools/call。未啟用時乾跑，不發 HTTP。"""
    cfg = cfg or load_config()
    arguments = dict(arguments or {})
    local_name = str(tool_name or "").strip()
    remote_name = REMOTE_TOOL_NAMES.get(local_name, local_name)
    blocked = _deny_file_tool(remote_name, cfg)
    if blocked:
        _append_audit(
            {"tool": local_name, "remote": remote_name, "ok": False, "error": blocked["error"], "role": role},
            cfg,
        )
        return blocked

    if remote_name not in set(REMOTE_TOOL_NAMES.values()) and not cfg.allow_files:
        err = {
            "ok": False,
            "error": f"未允許的 Minecraft 工具：{local_name}",
            "code": "unknown_tool",
        }
        _append_audit({**err, "tool": local_name, "role": role}, cfg)
        return err

    if cfg.dry_run:
        result = {
            "ok": True,
            "dry_run": True,
            "tool": local_name,
            "remote": remote_name,
            "arguments": arguments,
            "message": (
                "未連線 Minecraft MCP（乾跑）。"
                "設定 EVOL_MC_MCP_ENABLED=true 與 EVOL_MC_MCP_TOKEN 後才會寫入世界。"
            ),
        }
        _append_audit(
            {
                "tool": local_name,
                "remote": remote_name,
                "ok": True,
                "dry_run": True,
                "role": role,
                "args": {k: arguments[k] for k in list(arguments)[:8]},
            },
            cfg,
        )
        return result

    started = datetime.now(timezone.utc)
    rpc = jsonrpc_request(
        "tools/call",
        {"name": remote_name, "arguments": arguments},
        cfg=cfg,
        client=client,
    )
    elapsed_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    out = {
        "ok": bool(rpc.get("ok")),
        "dry_run": False,
        "tool": local_name,
        "remote": remote_name,
        "arguments": arguments,
        "result": rpc.get("result"),
        "text": rpc.get("text") or "",
        "error": rpc.get("error") or "",
        "duration_ms": elapsed_ms,
    }
    _append_audit(
        {
            "tool": local_name,
            "remote": remote_name,
            "ok": out["ok"],
            "dry_run": False,
            "role": role,
            "duration_ms": elapsed_ms,
            "error": out["error"][:300] if out["error"] else "",
        },
        cfg,
    )
    return out


def probe_connection(cfg: MinecraftMcpConfig | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    if cfg.dry_run:
        return {
            "ok": True,
            "connected": False,
            "dry_run": True,
            "message": "乾跑模式：未向 MineMCP 發送探測",
            "tools": list(COMPANY_TOOL_NAMES),
        }
    rpc = jsonrpc_request("tools/list", {}, cfg=cfg, client=client)
    names: list[str] = []
    result = rpc.get("result")
    if isinstance(result, dict):
        tools = result.get("tools") or []
        if isinstance(tools, list):
            for item in tools:
                if isinstance(item, dict) and item.get("name"):
                    names.append(str(item["name"]))
    return {
        "ok": bool(rpc.get("ok")),
        "connected": bool(rpc.get("ok")),
        "dry_run": False,
        "error": rpc.get("error") or "",
        "remote_tools": names,
        "tools": list(COMPANY_TOOL_NAMES),
    }


def connector_status(cfg: MinecraftMcpConfig | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    return {
        "enabled": cfg.enabled,
        "live": cfg.live,
        "dry_run": cfg.dry_run,
        "url": cfg.public_url,
        "world": cfg.world,
        "token_configured": bool(cfg.token),
        "allow_files": cfg.allow_files,
        "max_fill": cfg.max_fill,
        "tools": list(COMPANY_TOOL_NAMES),
        "remote_map": dict(REMOTE_TOOL_NAMES),
        "provider": "minemcp",
        "recent": recent_audit(12, cfg),
    }


def connector_status_brief(cfg: MinecraftMcpConfig | None = None) -> str:
    st = connector_status(cfg)
    mode = "乾跑" if st["dry_run"] else "已啟用連線"
    return (
        f"【Minecraft MCP】{mode}；公開端點 {st['url']}；預設世界 {st['world']}。"
        "可用工具：place_block / break_block / fill_block / execute_command / get_player。"
        "遠端放置工具名為 pose_block。"
    )


# ── 具體工具（同步，供公司 tool_registry） ──


def place_block(
    x: int,
    y: int,
    z: int,
    material: str,
    world: str | None = None,
    *,
    role: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    return call_mcp_tool(
        PLACE_BLOCK,
        {
            "world": (world or cfg.world),
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "material": normalize_material(material),
        },
        cfg=cfg,
        client=client,
        role=role,
    )


def break_block(
    x: int,
    y: int,
    z: int,
    world: str | None = None,
    *,
    role: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    return call_mcp_tool(
        BREAK_BLOCK,
        {"world": (world or cfg.world), "x": int(x), "y": int(y), "z": int(z)},
        cfg=cfg,
        client=client,
        role=role,
    )


def fill_block(
    x1: int,
    y1: int,
    z1: int,
    x2: int,
    y2: int,
    z2: int,
    material: str,
    world: str | None = None,
    *,
    role: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    cfg = load_config()
    return call_mcp_tool(
        FILL_BLOCK,
        {
            "world": (world or cfg.world),
            "x1": int(x1),
            "y1": int(y1),
            "z1": int(z1),
            "x2": int(x2),
            "y2": int(y2),
            "z2": int(z2),
            "material": normalize_material(material),
        },
        cfg=cfg,
        client=client,
        role=role,
    )


def execute_command(
    command: str,
    *,
    role: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    return call_mcp_tool(
        EXECUTE_COMMAND,
        {"command": str(command).strip()},
        client=client,
        role=role,
    )


def get_player(
    player: str,
    *,
    role: str | None = None,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    return call_mcp_tool(GET_PLAYER, {"player": str(player).strip()}, client=client, role=role)


def get_online_players(*, role: str | None = None, client: httpx.Client | None = None) -> dict[str, Any]:
    return call_mcp_tool(GET_ONLINE_PLAYERS, {}, client=client, role=role)


def format_tool_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)[:4000]

