"""靈境面向的 Minecraft MCP：鐵律校驗、建築派發、監控狀態。"""

from __future__ import annotations

import logging
from typing import Any

from backend.linkin.constitution import max_blocks_per_call
from backend.linkin.tools import (
    ToolValidationError,
    is_sensitive_admin,
    validate_admin_execute,
    validate_no_command_chain,
)
from backend.tools import minecraft_mcp as mcp

logger = logging.getLogger(__name__)

# 公司運行時角色：故事工作室 + 靈境建築席
MC_WRITE_ROLES = [
    "manager",
    "creative_lead",
    "story_writer",
    "custom_linkin_build_director",
    "custom_linkin_build_executor",
    "linkin_build_director",
    "linkin_build_executor",
    "custom_linkin_build_*",
]
MC_ADMIN_ROLES = [
    "manager",
    "custom_linkin_build_director",
    "linkin_build_director",
]
MC_READ_ROLES = [
    *MC_WRITE_ROLES,
    "reviewer",
    "synthesizer",
    "narrative_editor",
    "custom_linkin_*",
]

STYLE_MATERIALS: dict[str, str] = {
    "精灵古典": "OAK_PLANKS",
    "林冠木石": "MOSSY_COBBLESTONE",
    "月光庭园": "OAK_PLANKS",
    "树桥聚落": "JUNGLE_WOOD",
    "织梦典章": "QUARTZ_BLOCK",
    "白石圣殿": "QUARTZ_BLOCK",
    "契约广场": "SMOOTH_STONE",
    "金线回廊": "GOLD_BLOCK",
    "蒸汽帆索": "COPPER_BLOCK",
    "自由贸易港": "SPRUCE_PLANKS",
    "裂隙工坊": "IRON_BLOCK",
    "黄铜市集": "COPPER_BLOCK",
    "水雾苔石": "MOSS_BLOCK",
    "隐士木屋": "DARK_OAK_PLANKS",
    "灵脉神殿": "PRISMARINE",
    "雾中庭园": "MOSS_BLOCK",
}


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError(f"{field} 必須為整數") from exc


def _max_blocks() -> int:
    cfg = mcp.load_config()
    const_limit = max_blocks_per_call() or 5000
    return min(cfg.max_fill, const_limit, 5000)


def prepare_place(args: dict[str, Any]) -> dict[str, Any]:
    validate_no_command_chain(args)
    xyz = mcp.parse_xyz(args.get("location") or args)
    if xyz is None:
        x, y, z = _as_int(args.get("x"), "x"), _as_int(args.get("y"), "y"), _as_int(args.get("z"), "z")
    else:
        x, y, z = xyz
    material = mcp.normalize_material(str(args.get("material") or "STONE"))
    world = str(args.get("world") or mcp.load_config().world).strip()
    return {"x": x, "y": y, "z": z, "material": material, "world": world}


def prepare_break(args: dict[str, Any]) -> dict[str, Any]:
    validate_no_command_chain(args)
    xyz = mcp.parse_xyz(args.get("location") or args)
    if xyz is None:
        x, y, z = _as_int(args.get("x"), "x"), _as_int(args.get("y"), "y"), _as_int(args.get("z"), "z")
    else:
        x, y, z = xyz
    world = str(args.get("world") or mcp.load_config().world).strip()
    return {"x": x, "y": y, "z": z, "world": world}


def prepare_fill(args: dict[str, Any]) -> dict[str, Any]:
    validate_no_command_chain(args)
    x1 = _as_int(args.get("x1"), "x1")
    y1 = _as_int(args.get("y1"), "y1")
    z1 = _as_int(args.get("z1"), "z1")
    x2 = _as_int(args.get("x2"), "x2")
    y2 = _as_int(args.get("y2"), "y2")
    z2 = _as_int(args.get("z2"), "z2")
    volume = mcp.fill_volume(x1, y1, z1, x2, y2, z2)
    limit = _max_blocks()
    if volume > limit:
        raise ToolValidationError(
            f"單次 fill 不得超過 {limit} 方塊（收到 {volume}）",
            code="block_limit",
            extra={"block_count": volume, "max_blocks": limit},
        )
    if volume <= 0:
        raise ToolValidationError("fill 範圍無效", code="block_limit")
    material = mcp.normalize_material(str(args.get("material") or "STONE"))
    world = str(args.get("world") or mcp.load_config().world).strip()
    return {
        "x1": x1,
        "y1": y1,
        "z1": z1,
        "x2": x2,
        "y2": y2,
        "z2": z2,
        "material": material,
        "world": world,
        "block_count": volume,
    }


def prepare_command(args: dict[str, Any]) -> dict[str, Any]:
    validate_no_command_chain(args)
    confirmed = bool(args.get("confirmed") or args.get("confirm"))
    normalized = validate_admin_execute({"command": args.get("command")}, confirmed=confirmed)
    return normalized


def execute_named_tool(
    tool_name: str,
    args: dict[str, Any] | None = None,
    *,
    role: str | None = None,
) -> dict[str, Any]:
    """校驗後呼叫 MCP。供 API 與公司包裝器共用。"""
    args = dict(args or {})
    name = str(tool_name or "").strip()
    if name in {mcp.PLACE_BLOCK, mcp.POSE_BLOCK}:
        params = prepare_place(args)
        result = mcp.place_block(
            params["x"], params["y"], params["z"], params["material"], params["world"], role=role
        )
        result["params"] = params
        return result
    if name == mcp.BREAK_BLOCK:
        params = prepare_break(args)
        result = mcp.break_block(params["x"], params["y"], params["z"], params["world"], role=role)
        result["params"] = params
        return result
    if name == mcp.FILL_BLOCK:
        params = prepare_fill(args)
        result = mcp.fill_block(
            params["x1"],
            params["y1"],
            params["z1"],
            params["x2"],
            params["y2"],
            params["z2"],
            params["material"],
            params["world"],
            role=role,
        )
        result["params"] = params
        return result
    if name == mcp.EXECUTE_COMMAND:
        params = prepare_command(args)
        result = mcp.execute_command(params["command"], role=role)
        result["params"] = params
        result["sensitive"] = is_sensitive_admin(params["command"])
        return result
    if name == mcp.GET_PLAYER:
        player = str(args.get("player") or args.get("name") or "").strip()
        if not player:
            raise ToolValidationError("get_player 需要 player")
        return mcp.get_player(player, role=role)
    if name == mcp.GET_ONLINE_PLAYERS:
        return mcp.get_online_players(role=role)
    raise ToolValidationError(f"未知 Minecraft 工具：{name}", code="unknown_tool")


def execute_for_agent(tool_name: str, **kwargs: Any) -> str:
    """公司 tool_registry 執行入口：校驗失敗以字串回傳，不拋給角色。"""
    try:
        result = execute_named_tool(tool_name, kwargs)
    except ToolValidationError as exc:
        payload = {"ok": False, "error": str(exc), "code": exc.code, **exc.extra, "tool": tool_name}
        return mcp.format_tool_result(payload)
    if not result.get("ok"):
        return mcp.format_tool_result(result)
    return mcp.format_tool_result(result)


def _place_path_segment(
    points: list[dict[str, int]],
    *,
    material: str,
    width: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """沿路徑放置方塊；回傳 (applied, errors, dry_run_seen)。"""
    applied: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    dry_run = False
    cells: list[tuple[int, int, int]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        steps = max(abs(b["x"] - a["x"]), abs(b["y"] - a["y"]), abs(b["z"] - a["z"]), 1)
        for step in range(steps + 1):
            t = step / steps
            cell = (
                round(a["x"] + (b["x"] - a["x"]) * t),
                round(a["y"] + (b["y"] - a["y"]) * t),
                round(a["z"] + (b["z"] - a["z"]) * t),
            )
            if cell not in cells:
                cells.append(cell)
    for x, y, z in cells:
        for w in range(max(1, width)):
            try:
                result = execute_named_tool(
                    mcp.PLACE_BLOCK,
                    {"x": x, "y": y, "z": z + w, "material": material},
                )
                if result.get("dry_run"):
                    dry_run = True
                applied.append({"x": x, "y": y, "z": z + w, "ok": result.get("ok")})
            except ToolValidationError as exc:
                errors.append({"x": x, "y": y, "z": z + w, "error": str(exc), "code": exc.code})
    return applied, errors, dry_run


def dispatch_map_plan(plan: dict[str, Any], *, confirmed: bool = False) -> dict[str, Any]:
    """Phase 4：落地 map_plan 的 markers、paths、terrain patches。"""
    if not confirmed:
        raise ToolValidationError(
            "地圖落地需 confirm=true",
            code="needs_confirmation",
            extra={"needs_confirmation": True, "plan_id": plan.get("id")},
        )
    applied_plots: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    dry_run = False
    blocks_placed = 0

    for plot in plan.get("plots") or []:
        plot_id = plot.get("id")
        kind = plot.get("kind")
        try:
            if kind in {"marker", "poi"}:
                loc = plot.get("location") or {}
                material = plot.get("material") or "GOLD_BLOCK"
                result = execute_named_tool(
                    mcp.PLACE_BLOCK,
                    {"x": loc["x"], "y": loc["y"], "z": loc["z"], "material": material},
                )
                if result.get("dry_run"):
                    dry_run = True
                blocks_placed += 1
                applied_plots.append({"plot_id": plot_id, "kind": kind, "ok": result.get("ok"), "blocks": 1})
            elif kind == "path":
                seg_applied, seg_errors, seg_dry = _place_path_segment(
                    plot.get("points") or [],
                    material=str(plot.get("material") or "GRAVEL"),
                    width=int(plot.get("width") or 1),
                )
                if seg_dry:
                    dry_run = True
                blocks_placed += len(seg_applied)
                if seg_errors:
                    errors.extend([{"plot_id": plot_id, **e} for e in seg_errors])
                applied_plots.append(
                    {
                        "plot_id": plot_id,
                        "kind": kind,
                        "ok": len(seg_errors) == 0,
                        "blocks": len(seg_applied),
                    }
                )
            elif kind == "terrain":
                geom = plot.get("geometry") or {}
                result = execute_named_tool(
                    mcp.FILL_BLOCK,
                    {
                        "x1": geom["x1"],
                        "y1": geom["y1"],
                        "z1": geom["z1"],
                        "x2": geom["x2"],
                        "y2": geom["y2"],
                        "z2": geom["z2"],
                        "material": geom.get("material") or "GRASS_BLOCK",
                    },
                )
                if result.get("dry_run"):
                    dry_run = True
                vol = int((result.get("params") or {}).get("block_count") or 0)
                blocks_placed += vol or mcp.fill_volume(
                    geom["x1"], geom["y1"], geom["z1"], geom["x2"], geom["y2"], geom["z2"]
                )
                applied_plots.append({"plot_id": plot_id, "kind": kind, "ok": result.get("ok"), "blocks": vol})
        except ToolValidationError as exc:
            errors.append({"plot_id": plot_id, "kind": kind, "error": str(exc), "code": exc.code})

    ok = bool(applied_plots) and len(errors) < len(plan.get("plots") or [])
    status = "complete" if ok and not errors else ("partial" if applied_plots else "failed")
    return {
        "ok": ok or bool(applied_plots),
        "dry_run": dry_run,
        "plan_id": plan.get("id"),
        "status": status,
        "applied": applied_plots,
        "errors": errors,
        "blocks_placed": blocks_placed,
        "note": "Phase 4 落地 markers／徑道方塊／小型 terrain fill；大量塑形請分批 fill_block。",
    }


def dispatch_building(building: dict[str, Any]) -> dict[str, Any]:
    """把已校驗的建築方案落到世界：在錨點放一顆風格對應的標記方塊。"""
    xyz = mcp.parse_xyz(building.get("location"))
    if xyz is None:
        raise ToolValidationError("建築 location 無法解析為 x,y,z")
    style = str(building.get("style") or "")
    material = STYLE_MATERIALS.get(style, "OAK_PLANKS")
    result = execute_named_tool(
        mcp.PLACE_BLOCK,
        {"x": xyz[0], "y": xyz[1], "z": xyz[2], "material": material},
    )
    result["building_id"] = building.get("id")
    result["marker_material"] = material
    result["note"] = (
        "僅在錨點放置標記方塊，不會一次填入方案的全部方塊。"
        "大量塑形請由角色以 fill_block 分批執行，且不得超過單次上限。"
    )
    return result


def monitor_status() -> dict[str, Any]:
    cfg_status = mcp.connector_status()
    probe = mcp.probe_connection()
    return {
        **cfg_status,
        "connected": probe.get("connected", False),
        "probe": probe,
        "max_blocks": _max_blocks(),
        "company_tools": list(mcp.COMPANY_TOOL_NAMES),
        "write_roles": list(MC_WRITE_ROLES),
        "admin_roles": list(MC_ADMIN_ROLES),
    }


def register_company_tools(registry: Any) -> None:
    """向公司 tool_registry 註冊 Minecraft 工具。"""
    registry.register(
        name=mcp.PLACE_BLOCK,
        description="在 Minecraft 世界指定座標放置方塊（遠端 MineMCP 工具名 pose_block）",
        parameters={
            "x": {"type": "integer", "description": "X"},
            "y": {"type": "integer", "description": "Y"},
            "z": {"type": "integer", "description": "Z"},
            "location": {"type": "string", "description": "可選，如 '100, 64, 200'（優先於分開的 x/y/z）"},
            "material": {"type": "string", "description": "方塊材料，如 DIAMOND_BLOCK 或 钻石块"},
            "world": {"type": "string", "description": "世界名（可選，預設 EVOL_MC_MCP_WORLD）"},
        },
        execute=lambda **kwargs: execute_for_agent(mcp.PLACE_BLOCK, **kwargs),
        allowed_roles=list(MC_WRITE_ROLES),
        readonly=False,
        timeout_seconds=30.0,
    )
    registry.register(
        name=mcp.POSE_BLOCK,
        description="place_block 的 MineMCP 別名（pose_block）",
        parameters={
            "x": {"type": "integer", "description": "X"},
            "y": {"type": "integer", "description": "Y"},
            "z": {"type": "integer", "description": "Z"},
            "location": {"type": "string", "description": "可選座標字串"},
            "material": {"type": "string", "description": "方塊材料"},
            "world": {"type": "string", "description": "世界名（可選）"},
        },
        execute=lambda **kwargs: execute_for_agent(mcp.POSE_BLOCK, **kwargs),
        allowed_roles=list(MC_WRITE_ROLES),
        readonly=False,
        timeout_seconds=30.0,
    )
    registry.register(
        name=mcp.BREAK_BLOCK,
        description="破壞 Minecraft 世界指定座標的方塊",
        parameters={
            "x": {"type": "integer", "description": "X"},
            "y": {"type": "integer", "description": "Y"},
            "z": {"type": "integer", "description": "Z"},
            "world": {"type": "string", "description": "世界名（可選）"},
        },
        execute=lambda **kwargs: execute_for_agent(mcp.BREAK_BLOCK, **kwargs),
        allowed_roles=list(MC_WRITE_ROLES),
        readonly=False,
        timeout_seconds=30.0,
    )
    registry.register(
        name=mcp.FILL_BLOCK,
        description="以方塊填充區域；體積不得超過靈境單次方塊上限",
        parameters={
            "x1": {"type": "integer", "description": "起點 X"},
            "y1": {"type": "integer", "description": "起點 Y"},
            "z1": {"type": "integer", "description": "起點 Z"},
            "x2": {"type": "integer", "description": "終點 X"},
            "y2": {"type": "integer", "description": "終點 Y"},
            "z2": {"type": "integer", "description": "終點 Z"},
            "material": {"type": "string", "description": "方塊材料"},
            "world": {"type": "string", "description": "世界名（可選）"},
        },
        execute=lambda **kwargs: execute_for_agent(mcp.FILL_BLOCK, **kwargs),
        allowed_roles=list(MC_WRITE_ROLES),
        readonly=False,
        timeout_seconds=45.0,
    )
    registry.register(
        name=mcp.EXECUTE_COMMAND,
        description="執行 Minecraft 指令（敏感操作如踢人／停服需 confirmed=true）",
        parameters={
            "command": {"type": "string", "description": "不含斜線的指令，如 time set day"},
            "confirmed": {"type": "boolean", "description": "敏感操作二次確認"},
        },
        execute=lambda **kwargs: execute_for_agent(mcp.EXECUTE_COMMAND, **kwargs),
        allowed_roles=list(MC_ADMIN_ROLES),
        readonly=False,
        timeout_seconds=30.0,
    )
    registry.register(
        name=mcp.GET_PLAYER,
        description="讀取線上玩家資訊（生命、座標、物品欄等）",
        parameters={"player": {"type": "string", "description": "玩家名稱"}},
        execute=lambda **kwargs: execute_for_agent(mcp.GET_PLAYER, **kwargs),
        allowed_roles=list(MC_READ_ROLES),
        readonly=False,
        timeout_seconds=20.0,
    )
    registry.register(
        name=mcp.GET_ONLINE_PLAYERS,
        description="列出目前線上玩家",
        parameters={},
        execute=lambda **kwargs: execute_for_agent(mcp.GET_ONLINE_PLAYERS, **kwargs),
        allowed_roles=list(MC_READ_ROLES),
        readonly=False,
        timeout_seconds=20.0,
    )

