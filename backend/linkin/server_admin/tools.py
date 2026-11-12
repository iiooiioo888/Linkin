"""伺服器運維的工具目錄、工具分派與公司工具掛載（自 backend.linkin.server_admin 抽出）。"""

from __future__ import annotations

from typing import Any

from backend.tools import server_admin as sa
from backend.tools.server_admin import ServerAdminError

from .pending import create_approval

TOOL_CATALOG: dict[str, dict[str, Any]] = {
    "health": {"desc": "整體健康快照（磁盤/CPU/內存/Docker/白名單服務）", "params": {}},
    "patrol": {"desc": "主動巡檢：健康快照 + 規則提案（清理/輪轉/重啟自動轉人工批准）", "params": {}},
    "get_disk_usage": {"desc": "磁盤使用率（存儲根或子目錄）", "params": {"target": "可選子目錄，如 packages"}},
    "get_system_load": {"desc": "CPU / 內存 / load average", "params": {}},
    "get_memory_usage": {"desc": "內存使用", "params": {}},
    "get_docker_status": {"desc": "所有 Docker 容器狀態", "params": {}},
    "check_service": {"desc": "查詢 systemd 服務狀態（白名單內）", "params": {"name": "服務名，如 mysql"}},
    "analyze_disk_growth": {"desc": "磁盤增長分析：各目錄佔用、近 N 天增長來源、最大新文件", "params": {"days": "窗口天數(1-365)", "top": "返回條數(1-50)"}},
    "tail_log": {"desc": "讀日誌尾部（logs/ 內文件或 audit）", "params": {"name": "日誌文件名或 audit", "lines": "行數(1-1000)"}},
    "clean_old_packages": {"desc": "【寫】清理 packages/ 超過 N 天的 .zip", "params": {"days": "天數(默認7)"}},
    "clean_temp_files": {"desc": "【寫】清理 temp/ 超過 N 天的文件", "params": {"days": "天數(默認3)"}},
    "rotate_logs": {"desc": "【寫】gzip 輪轉 logs/ 超過 N MB 的 .log", "params": {"max_mb": "MB 閾值(默認100)"}},
    "restart_service": {"desc": "【寫】重啟白名單 systemd 服務", "params": {"name": "服務名"}},
    "backup_incremental": {"desc": "【寫】增量備份 assets/schematics 等到備份目錄", "params": {"subdir": "子目錄(默認assets)"}},
}


_KEYWORD_ROUTES: tuple[tuple[str, tuple[str, ...], dict[str, Any]], ...] = (
    ("patrol", ("巡檢", "巡检", "自動清理", "自动清理", "自動修復", "自动修复", "全面檢查", "全面检查", "體檢", "体检"), {}),
    ("clean_old_packages", ("zip", "打包", "舊包", "旧包", "過期包", "过期包"), {"days": 7}),
    ("clean_temp_files", ("temp", "臨時", "临时", "緩存文件", "缓存文件", "python 緩存", "python 缓存", "pyc"), {"days": 3}),
    ("rotate_logs", ("輪轉", "轮转", "rotate", "日誌太大", "日志太大", "log 太大"), {"max_mb": 100}),
    ("backup_incremental", ("備份", "备份", "backup", "歸檔", "归档"), {"subdir": "assets"}),
    ("restart_service", ("重啟", "重启", "restart", "崩潰", "崩溃", "掛了", "挂了", "down"), {}),
    ("analyze_disk_growth", ("為什麼漲", "为什么涨", "涨得", "漲得", "增長", "增长", "佔用最多", "占用最多", "什麼占", "什么占", "哪個目錄", "哪个目录", "磁盤", "磁盘", "disk", "空間不足", "空间不足", "快滿", "快满"), {"days": 7}),
    ("tail_log", ("日誌", "日志", "log", "報錯", "报错"), {"name": "app", "lines": 100}),
    ("get_docker_status", ("docker", "容器", "container"), {}),
    ("get_system_load", ("cpu", "內存", "内存", "memory", "負載", "负载", "load", "性能"), {}),
    ("check_service", ("mysql", "redis", "nginx", "服務狀態", "服务状态", "連接數", "连接数"), {}),
)


_SERVICE_HINTS = ("linkin-api", "mysql", "redis-server", "redis", "nginx")


def execute_tool(name: str, params: dict[str, Any] | None = None, *, confirm: bool = False, role: str = "") -> dict[str, Any]:
    """執行具名工具；寫工具未確認時回傳 pending_confirmation 預覽（無副作用）。"""
    params = dict(params or {})
    if name not in sa.ALL_TOOLS:
        raise ServerAdminError(f"未知運維工具：{name}", code="unknown_tool", extra={"tool": name})
    result = sa.execute_named_tool(name, params, confirm=confirm, role=role)
    result.setdefault("tool", name)
    if role:
        result.setdefault("role", role)
    return result


def execute_for_agent(name: str, params: dict[str, Any] | None = None, *, role: str = "") -> dict[str, Any]:
    """公司運行時入口：寫工具未帶 confirmed 時自動轉人工批准隊列。"""
    params = dict(params or {})
    confirmed = bool(params.pop("confirmed", False) or params.pop("confirm", False))
    try:
        if name in sa.WRITE_TOOLS and not confirmed:
            preview = execute_tool(name, params, role=role)
            record = create_approval(name, params, preview, question=f"由公司角色 {role or 'agent'} 發起")
            return {
                "ok": True,
                "status": "pending_approval",
                "approval_id": record["id"],
                "message": preview.get("message", "已轉人工批准"),
                "tool": name,
            }
        return execute_tool(name, params, confirm=confirmed, role=role)
    except ServerAdminError as exc:
        return {"ok": False, "code": exc.code, "message": str(exc), "tool": name}


_COMPANY_TOOL_NAMES: dict[str, str] = {
    "get_disk_usage": "server_disk_usage",
    "get_system_load": "server_system_load",
    "get_memory_usage": "server_memory_usage",
    "get_docker_status": "server_docker_status",
    "check_service": "server_service_status",
    "analyze_disk_growth": "server_disk_growth",
    "tail_log": "server_tail_log",
    "clean_old_packages": "server_clean_packages",
    "clean_temp_files": "server_clean_temp",
    "rotate_logs": "server_rotate_logs",
    "restart_service": "server_restart_service",
    "backup_incremental": "server_backup",
}


_WRITE_ROLES = ["manager", "devops", "sre", "server_admin"]


def register_company_tools(registry: Any) -> None:
    """向公司 tool_registry 註冊運維工具（讀開放、寫限維運角色且經批准隊列）。"""
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_disk_usage"],
        description="磁盤使用率（存儲根或子目錄，只讀）",
        parameters={"target": {"type": "string", "description": "可選子目錄，如 packages"}},
        execute=lambda **kw: execute_for_agent("get_disk_usage", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_system_load"],
        description="CPU / 內存 / load average（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_system_load", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_memory_usage"],
        description="內存使用（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_memory_usage", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["get_docker_status"],
        description="所有 Docker 容器狀態（只讀）",
        parameters={},
        execute=lambda **kw: execute_for_agent("get_docker_status", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["check_service"],
        description="查詢 systemd 服務狀態（白名單內，只讀）",
        parameters={"name": {"type": "string", "description": "服務名，如 mysql"}},
        execute=lambda **kw: execute_for_agent("check_service", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["analyze_disk_growth"],
        description="磁盤增長分析：各目錄佔用與近 N 天增長來源（只讀）",
        parameters={
            "days": {"type": "integer", "description": "窗口天數（默認 7）"},
            "top": {"type": "integer", "description": "返回條數（默認 10）"},
        },
        execute=lambda **kw: execute_for_agent("analyze_disk_growth", kw),
        readonly=True,
        timeout_seconds=60.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["tail_log"],
        description="讀取 logs/ 內日誌或審計日誌尾部（只讀）",
        parameters={
            "name": {"type": "string", "description": "日誌文件名或 audit"},
            "lines": {"type": "integer", "description": "行數（默認 100）"},
        },
        execute=lambda **kw: execute_for_agent("tail_log", kw),
        readonly=True,
        timeout_seconds=30.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["clean_old_packages"],
        description="【寫·需批准】清理 packages/ 超過 N 天的 .zip",
        parameters={"days": {"type": "integer", "description": "天數（默認 7）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("clean_old_packages", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["clean_temp_files"],
        description="【寫·需批准】清理 temp/ 超過 N 天的文件",
        parameters={"days": {"type": "integer", "description": "天數（默認 3）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("clean_temp_files", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["rotate_logs"],
        description="【寫·需批准】gzip 輪轉 logs/ 超過 N MB 的 .log",
        parameters={"max_mb": {"type": "integer", "description": "MB 閾值（默認 100）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("rotate_logs", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["restart_service"],
        description="【寫·需批准】重啟白名單 systemd 服務",
        parameters={"name": {"type": "string", "description": "服務名（白名單內）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("restart_service", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=90.0,
    )
    registry.register(
        name=_COMPANY_TOOL_NAMES["backup_incremental"],
        description="【寫·需批准】增量備份 assets/schematics 到備份目錄",
        parameters={"subdir": {"type": "string", "description": "子目錄（默認 assets）"}, "confirmed": {"type": "boolean", "description": "已人工批准時為 true"}},
        execute=lambda **kw: execute_for_agent("backup_incremental", kw),
        allowed_roles=list(_WRITE_ROLES),
        readonly=False,
        timeout_seconds=120.0,
    )
