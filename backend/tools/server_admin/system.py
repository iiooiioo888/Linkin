"""系統查詢工具（自 backend.tools.server_admin 抽出）。

psutil／docker／systemd 的唯讀查詢與磁碟成長分析、日誌尾巴。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import (
    LOG_NAME_RE,
    MAX_SCAN_FILES,
    SUBPROCESS_TIMEOUT,
    ServerAdminConfig,
    ServerAdminError,
    load_config,
)
from .guards import (
    _append_audit,
    _check_service,
    _guard_dangerous,
    _human_bytes,
    _resolve_under_root,
)

try:  # psutil 为运维指标的软依赖；缺失时读操作降级而非崩溃
    import psutil
except Exception:
    psutil = None  # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════
# 读操作（永远安全执行，跨平台优雅降级）
# ═══════════════════════════════════════════════════════════


def get_disk_usage(target: str | Path | None = None, *, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """磁盘使用率。target 必须在存储根内；根不存在时回退到最近的已存在祖先。"""
    cfg = config or load_config()
    path = _resolve_under_root(cfg, target)  # 越界时抛 ServerAdminError(path_denied)
    probe = path
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    usage = shutil.disk_usage(str(probe))
    percent = round(usage.used / usage.total * 100, 2) if usage.total else 0.0
    result = {
        "ok": True,
        "path": str(path),
        "probe_path": str(probe),
        "total_gb": round(usage.total / 1024**3, 2),
        "used_gb": round(usage.used / 1024**3, 2),
        "free_gb": round(usage.free / 1024**3, 2),
        "percent": percent,
        "warning": percent >= 90,
    }
    _append_audit(cfg, {"tool": "get_disk_usage", "ok": True, "target": str(target or "")})
    return result


def get_system_load(*, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """CPU / 内存 / load average。psutil 缺失时降级。"""
    cfg = config or load_config()
    if psutil is None:
        result = {"ok": False, "reason": "psutil 未安装", "cpu_percent": None, "memory": None}
        _append_audit(cfg, {"tool": "get_system_load", "ok": False, "reason": "no_psutil"})
        return result
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    load = None
    if hasattr(os, "getloadavg"):
        try:
            load = [round(x, 2) for x in os.getloadavg()]
        except OSError:
            load = None
    result = {
        "ok": True,
        "cpu_percent": round(float(cpu), 2),
        "cpu_count": psutil.cpu_count(logical=True),
        "memory": {
            "total_gb": round(mem.total / 1024**3, 2),
            "available_gb": round(mem.available / 1024**3, 2),
            "used_gb": round(mem.used / 1024**3, 2),
            "percent": round(mem.percent, 2),
        },
        "load_avg": load,
        "warning": cpu >= 90 or mem.percent >= 90,
    }
    _append_audit(cfg, {"tool": "get_system_load", "ok": True, "cpu": result["cpu_percent"]})
    return result


def get_memory_usage(*, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """内存使用（get_system_load 的内存子集，便于角色单独调用）。"""
    full = get_system_load(config=config)
    return {"ok": full.get("ok", False), "memory": full.get("memory"), "reason": full.get("reason")}


def get_docker_status(*, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """所有容器状态。docker 守护进程不可达时优雅降级（不抛异常）。"""
    cfg = config or load_config()
    try:
        import docker  # 延迟导入：无守护进程也不该拖垮模块加载

        client = docker.from_env(timeout=3)
        client.ping()
        containers = client.containers.list(all=True)
        statuses: dict[str, Any] = {}
        for c in containers:
            started: Any = "stopped"
            image = ""
            try:
                if c.status == "running":
                    started = c.attrs.get("State", {}).get("StartedAt", "running")
                tags = getattr(c.image, "tags", None) or []
                image = str(tags[0]) if tags else ""
            except Exception:
                started = c.status
            statuses[c.name] = {"status": c.status, "uptime": started, "image": image}
        running = sum(1 for s in statuses.values() if s["status"] == "running")
        result = {
            "ok": True,
            "available": True,
            "container_count": len(statuses),
            "running": running,
            "containers": statuses,
            "warning": any(s["status"] == "exited" for s in statuses.values()),
        }
    except Exception as exc:
        result = {
            "ok": True,
            "available": False,
            "reason": f"{type(exc).__name__}: {str(exc)[:160]}",
            "container_count": 0,
            "running": 0,
            "containers": {},
        }
    _append_audit(cfg, {"tool": "get_docker_status", "ok": True, "available": result.get("available")})
    return result


def check_service(name: str, *, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """查询 systemd 服务活跃状态（只读）。非 systemd 主机降级。"""
    cfg = config or load_config()
    service = _check_service(cfg, name)
    if shutil.which("systemctl") is None:
        result = {"ok": True, "available": False, "service": service, "reason": "systemctl 不存在（非 systemd 主机）"}
        _append_audit(cfg, {"tool": "check_service", "ok": True, "service": service, "available": False})
        return result
    if cfg.dry_run:
        result = {"ok": True, "available": True, "service": service, "active": "unknown", "dry_run": True}
        _append_audit(cfg, {"tool": "check_service", "ok": True, "service": service, "dry_run": True})
        return result
    try:
        proc = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT, check=False,
        )
        active = proc.stdout.strip() or "unknown"
        result = {"ok": True, "available": True, "service": service, "active": active}
    except (subprocess.TimeoutExpired, OSError) as exc:
        result = {"ok": False, "available": True, "service": service, "reason": str(exc)[:160]}
    _append_audit(cfg, {"tool": "check_service", "ok": result.get("ok", False), "service": service})
    return result


def analyze_disk_growth(days: int = 7, top: int = 10, *, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """分析存储根：各顶层目录占用 + 近 days 天增长来源 + 最大新增文件。

    回答「磁盘为什么涨得这么快 / 什么占用最多」的只读诊断工具。
    """
    cfg = config or load_config()
    days = max(1, min(int(days), 365))
    top = max(1, min(int(top), 50))
    root = _resolve_under_root(cfg)
    cutoff = time.time() - days * 86400
    dir_sizes: dict[str, int] = {}
    recent_by_dir: dict[str, int] = {}
    largest_recent: list[dict[str, Any]] = []
    scanned = 0
    truncated = False
    if root.exists():
        for path in root.rglob("*"):
            if scanned >= MAX_SCAN_FILES:
                truncated = True
                break
            try:
                if not path.is_file():
                    continue
                scanned += 1
                stat = path.stat()
                rel = path.relative_to(root)
                top_dir = rel.parts[0] if len(rel.parts) > 1 else "(root)"
                dir_sizes[top_dir] = dir_sizes.get(top_dir, 0) + stat.st_size
                if stat.st_mtime >= cutoff:
                    recent_by_dir[top_dir] = recent_by_dir.get(top_dir, 0) + stat.st_size
                    largest_recent.append({"path": str(rel), "size": int(stat.st_size), "mtime": stat.st_mtime})
            except (OSError, ValueError):
                continue
    largest_recent.sort(key=lambda r: r["size"], reverse=True)
    result = {
        "ok": True,
        "root": str(root),
        "days": days,
        "scanned_files": scanned,
        "truncated": truncated,
        "total_human": _human_bytes(sum(dir_sizes.values())),
        "by_directory": [
            {"dir": k, "bytes": v, "human": _human_bytes(v)}
            for k, v in sorted(dir_sizes.items(), key=lambda kv: kv[1], reverse=True)[:top]
        ],
        "recent_growth": [
            {"dir": k, "bytes": v, "human": _human_bytes(v)}
            for k, v in sorted(recent_by_dir.items(), key=lambda kv: kv[1], reverse=True)[:top]
        ],
        "largest_recent": [
            {"path": r["path"], "human": _human_bytes(r["size"])} for r in largest_recent[:top]
        ],
    }
    _append_audit(cfg, {"tool": "analyze_disk_growth", "ok": True, "days": days, "scanned": scanned})
    return result


def tail_log(name: str = "app", lines: int = 100, *, config: ServerAdminConfig | None = None) -> dict[str, Any]:
    """读取日志尾部（只读）。name="audit" 读运维审计；其余仅限 logs/ 目录内文件名。"""
    cfg = config or load_config()
    lines = max(1, min(int(lines), 1000))
    text = str(name or "app").strip() or "app"
    _guard_dangerous(text)
    if text == "audit":
        path = cfg.audit_path.expanduser()
    else:
        if not LOG_NAME_RE.match(text):
            raise ServerAdminError(
                "非法日志名（仅允许字母数字与 ._-，不含路径分隔符）",
                code="path_denied",
                extra={"name": text[:120]},
            )
        logs_dir = _resolve_under_root(cfg, "logs")
        path = _resolve_under_root(cfg, Path("logs") / text)
        if path != logs_dir and logs_dir not in path.parents:
            raise ServerAdminError("日志路径越界", code="path_denied", extra={"name": text})
    if not path.exists() or not path.is_file():
        _append_audit(cfg, {"tool": "tail_log", "ok": False, "name": text, "reason": "missing"})
        return {"ok": False, "reason": f"日志不存在：{path.name}", "name": path.name, "lines": []}
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > 256 * 1024:
                fh.seek(size - 256 * 1024)
                fh.readline()  # 丢弃可能不完整的首行
            data = fh.read()
    except OSError as exc:
        return {"ok": False, "reason": f"读取失败：{str(exc)[:120]}", "name": path.name, "lines": []}
    decoded = data.decode("utf-8", errors="replace").splitlines()
    tail = decoded[-lines:]
    result = {
        "ok": True,
        "name": path.name,
        "size_human": _human_bytes(size),
        "line_count": len(tail),
        "truncated": len(decoded) > len(tail),
        "lines": tail,
    }
    _append_audit(cfg, {"tool": "tail_log", "ok": True, "name": path.name, "lines": len(tail)})
    return result
