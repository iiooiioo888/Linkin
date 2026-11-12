"""維護操作與工具註冊表（自 backend.tools.server_admin 抽出）。

清理／輪轉／重啟／備份（需 confirm、乾跑、審計）與具名工具調度。
"""

from __future__ import annotations

import gzip
import shutil
import subprocess
import time
from pathlib import Path, PurePosixPath
from typing import Any

from .config import (
    MAX_BACKUP_BYTES,
    MAX_DELETE_PER_CALL,
    MAX_LOG_BYTES,
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
    _scan_old_files,
)
from .system import (
    analyze_disk_growth,
    check_service,
    get_disk_usage,
    get_docker_status,
    get_memory_usage,
    get_system_load,
    tail_log,
)

# ═══════════════════════════════════════════════════════════
# 写操作（需 confirm；dry_run 时只模拟）
# ═══════════════════════════════════════════════════════════


def _pending(message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": True, "status": "pending_confirmation", "message": message, **extra}


def clean_old_packages(
    days: int = 7, *, confirm: bool = False, config: ServerAdminConfig | None = None
) -> dict[str, Any]:
    """清理 storage_root/packages 下超过 days 天的 .zip 打包文件。"""
    cfg = config or load_config()
    days = max(0, min(int(days), 3650))
    packages_dir = _resolve_under_root(cfg, "packages")
    matched = _scan_old_files(packages_dir, ["*.zip"], days)
    total = sum(r["size"] for r in matched)
    if not confirm:
        return _pending(
            f"将删除 {days} 天前的 {len(matched)} 个 ZIP 包（{_human_bytes(total)}），请确认",
            tool="clean_old_packages", days=days, count=len(matched), bytes=total,
        )
    if cfg.dry_run:
        _append_audit(cfg, {"tool": "clean_old_packages", "ok": True, "status": "simulated", "days": days, "count": len(matched), "bytes": total})
        return {
            "ok": True, "status": "simulated", "dry_run": True, "days": days,
            "would_delete": len(matched), "would_free_bytes": total,
            "would_free_human": _human_bytes(total),
            "sample": [r["name"] for r in matched[:20]],
        }
    to_delete = matched[:MAX_DELETE_PER_CALL]
    deleted, freed, errors = 0, 0, []
    for row in to_delete:
        try:
            path = _resolve_under_root(cfg, row["path"])
            path.unlink()
            deleted += 1
            freed += row["size"]
        except (OSError, ServerAdminError) as exc:
            errors.append(f"{row['name']}: {str(exc)[:80]}")
    _append_audit(cfg, {"tool": "clean_old_packages", "ok": True, "status": "executed", "days": days, "deleted": deleted, "freed": freed, "errors": len(errors)})
    return {
        "ok": True, "status": "executed", "days": days, "deleted": deleted,
        "freed_bytes": freed, "freed_human": _human_bytes(freed), "errors": errors[:10],
    }


def clean_temp_files(
    days: int = 3, *, confirm: bool = False, config: ServerAdminConfig | None = None
) -> dict[str, Any]:
    """清空 storage_root/temp 下超过 days 天的临时文件。"""
    cfg = config or load_config()
    days = max(0, min(int(days), 3650))
    temp_dir = _resolve_under_root(cfg, "temp")
    matched = _scan_old_files(temp_dir, [], days)
    total = sum(r["size"] for r in matched)
    if not confirm:
        return _pending(
            f"将删除 temp 中 {days} 天前的 {len(matched)} 个文件（{_human_bytes(total)}），请确认",
            tool="clean_temp_files", days=days, count=len(matched), bytes=total,
        )
    if cfg.dry_run:
        _append_audit(cfg, {"tool": "clean_temp_files", "ok": True, "status": "simulated", "days": days, "count": len(matched), "bytes": total})
        return {
            "ok": True, "status": "simulated", "dry_run": True, "days": days,
            "would_delete": len(matched), "would_free_bytes": total, "would_free_human": _human_bytes(total),
        }
    to_delete = matched[:MAX_DELETE_PER_CALL]
    deleted, freed, errors = 0, 0, []
    for row in to_delete:
        try:
            _resolve_under_root(cfg, row["path"]).unlink()
            deleted += 1
            freed += row["size"]
        except (OSError, ServerAdminError) as exc:
            errors.append(f"{row['name']}: {str(exc)[:80]}")
    _append_audit(cfg, {"tool": "clean_temp_files", "ok": True, "status": "executed", "days": days, "deleted": deleted, "freed": freed})
    return {"ok": True, "status": "executed", "days": days, "deleted": deleted, "freed_bytes": freed, "freed_human": _human_bytes(freed), "errors": errors[:10]}


def rotate_logs(
    max_mb: int = 100, *, confirm: bool = False, config: ServerAdminConfig | None = None
) -> dict[str, Any]:
    """轮转 storage_root/logs 下超过 max_mb 的 .log：gzip 归档 + 清空原文件。"""
    cfg = config or load_config()
    max_mb = max(1, min(int(max_mb), MAX_LOG_BYTES // 1024**2))
    threshold = max_mb * 1024**2
    logs_dir = _resolve_under_root(cfg, "logs")
    candidates: list[dict[str, Any]] = []
    if logs_dir.exists():
        for path in logs_dir.rglob("*.log"):
            try:
                if path.is_file() and path.stat().st_size > threshold:
                    candidates.append({"path": str(path), "name": path.name, "size": int(path.stat().st_size)})
            except OSError:
                continue
    if not confirm:
        return _pending(
            f"将 gzip 归档并清空 {len(candidates)} 个 >{max_mb}MB 的日志，请确认",
            tool="rotate_logs", max_mb=max_mb, count=len(candidates),
        )
    if cfg.dry_run:
        _append_audit(cfg, {"tool": "rotate_logs", "ok": True, "status": "simulated", "max_mb": max_mb, "count": len(candidates)})
        return {"ok": True, "status": "simulated", "dry_run": True, "max_mb": max_mb, "would_rotate": len(candidates), "files": [r["name"] for r in candidates[:20]]}
    rotated, errors = 0, []
    stamp = time.strftime("%Y%m%d%H%M%S")
    for row in candidates:
        try:
            src = _resolve_under_root(cfg, row["path"])
            dest = src.with_name(f"{src.name}.{stamp}.gz")
            with src.open("rb") as fh_in, gzip.open(dest, "wb") as fh_out:
                shutil.copyfileobj(fh_in, fh_out)
            src.write_bytes(b"")  # 清空原文件（保留 inode，服务可继续写）
            rotated += 1
        except (OSError, ServerAdminError) as exc:
            errors.append(f"{row['name']}: {str(exc)[:80]}")
    _append_audit(cfg, {"tool": "rotate_logs", "ok": True, "status": "executed", "max_mb": max_mb, "rotated": rotated})
    return {"ok": True, "status": "executed", "max_mb": max_mb, "rotated": rotated, "errors": errors[:10]}


def restart_service(
    name: str, *, confirm: bool = False, config: ServerAdminConfig | None = None
) -> dict[str, Any]:
    """重启 systemd 服务（允许清单内）。需 confirm；dry_run 时模拟。"""
    cfg = config or load_config()
    service = _check_service(cfg, name)
    if not confirm:
        return _pending(f"将重启服务 {service}，请确认", tool="restart_service", service=service)
    if shutil.which("systemctl") is None:
        _append_audit(cfg, {"tool": "restart_service", "ok": False, "service": service, "reason": "unsupported"})
        return {"ok": True, "status": "unsupported", "service": service, "reason": "systemctl 不存在（非 systemd 主机）"}
    if cfg.dry_run:
        _append_audit(cfg, {"tool": "restart_service", "ok": True, "status": "simulated", "service": service})
        return {"ok": True, "status": "simulated", "dry_run": True, "service": service, "message": f"（乾跑）将执行 systemctl restart {service}"}
    try:
        proc = subprocess.run(
            ["systemctl", "restart", service],
            capture_output=True, text=True, timeout=SUBPROCESS_TIMEOUT, check=False,
        )
        success = proc.returncode == 0
        _append_audit(cfg, {"tool": "restart_service", "ok": success, "status": "executed", "service": service, "rc": proc.returncode})
        return {"ok": success, "status": "executed", "service": service, "returncode": proc.returncode, "output": (proc.stdout or proc.stderr)[:300]}
    except (subprocess.TimeoutExpired, OSError) as exc:
        _append_audit(cfg, {"tool": "restart_service", "ok": False, "status": "error", "service": service})
        return {"ok": False, "status": "error", "service": service, "reason": str(exc)[:200]}


def backup_incremental(
    subdir: str = "assets", *, confirm: bool = False, config: ServerAdminConfig | None = None
) -> dict[str, Any]:
    """增量备份 storage_root/<subdir> 到 backup_dir/<subdir>（跳过大小+mtime 相同的文件）。"""
    cfg = config or load_config()
    src_dir = _resolve_under_root(cfg, subdir)
    subdir_pure = PurePosixPath(str(subdir).strip("/\\") or "assets")
    dest_dir = (cfg.backup_dir.expanduser() / str(subdir_pure)).expanduser()
    if not src_dir.exists():
        return {"ok": True, "status": "noop", "reason": f"源目录不存在：{src_dir}", "copied": 0}
    files: list[tuple[Path, Path]] = []
    total_bytes = 0
    for path in src_dir.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src_dir)
        dest = dest_dir / rel
        try:
            src_stat = path.stat()
        except OSError:
            continue
        # 增量：目标存在且大小+mtime 一致则跳过
        if dest.exists():
            try:
                dest_stat = dest.stat()
                if dest_stat.st_size == src_stat.st_size and int(dest_stat.st_mtime) == int(src_stat.st_mtime):
                    continue
            except OSError:
                pass
        files.append((path, dest))
        total_bytes += src_stat.st_size
        if total_bytes > MAX_BACKUP_BYTES:
            break
    if not confirm:
        return _pending(
            f"将增量备份 {subdir} 的 {len(files)} 个文件（{_human_bytes(total_bytes)}）到 {dest_dir}，请确认",
            tool="backup_incremental", subdir=str(subdir_pure), count=len(files), bytes=total_bytes,
        )
    if cfg.dry_run:
        _append_audit(cfg, {"tool": "backup_incremental", "ok": True, "status": "simulated", "subdir": str(subdir_pure), "count": len(files), "bytes": total_bytes})
        return {"ok": True, "status": "simulated", "dry_run": True, "subdir": str(subdir_pure), "would_copy": len(files), "would_copy_bytes": total_bytes, "would_copy_human": _human_bytes(total_bytes)}
    copied, copied_bytes, errors = 0, 0, []
    for src, dest in files:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            copied += 1
            copied_bytes += src.stat().st_size
        except OSError as exc:
            errors.append(f"{src.name}: {str(exc)[:80]}")
    _append_audit(cfg, {"tool": "backup_incremental", "ok": True, "status": "executed", "subdir": str(subdir_pure), "copied": copied, "bytes": copied_bytes})
    return {"ok": True, "status": "executed", "subdir": str(subdir_pure), "copied": copied, "copied_bytes": copied_bytes, "copied_human": _human_bytes(copied_bytes), "errors": errors[:10]}


# ── 具名工具注册表（唯一对外入口；绝不暴露自由 shell）──
READONLY_TOOLS = frozenset(
    {
        "get_disk_usage",
        "get_system_load",
        "get_memory_usage",
        "get_docker_status",
        "check_service",
        "analyze_disk_growth",
        "tail_log",
    }
)


WRITE_TOOLS = frozenset(
    {"clean_old_packages", "clean_temp_files", "rotate_logs", "restart_service", "backup_incremental"}
)


ALL_TOOLS = READONLY_TOOLS | WRITE_TOOLS


def execute_named_tool(
    name: str, params: dict[str, Any] | None = None, *, confirm: bool = False, role: str = ""
) -> dict[str, Any]:
    """唯一入口：按名调度运维工具。未知工具/危险参数一律拒绝。"""
    params = dict(params or {})
    _guard_dangerous({"tool": name, **params})
    tool = str(name or "").strip()
    if tool not in ALL_TOOLS:
        raise ServerAdminError(f"未知运维工具：{tool}", code="unknown_tool", extra={"tool": tool})
    cfg = load_config()
    confirm_flag = bool(confirm or params.get("confirmed") or params.get("confirm"))

    if tool == "get_disk_usage":
        return get_disk_usage(params.get("target") or params.get("path"), config=cfg)
    if tool == "get_system_load":
        return get_system_load(config=cfg)
    if tool == "get_memory_usage":
        return get_memory_usage(config=cfg)
    if tool == "get_docker_status":
        return get_docker_status(config=cfg)
    if tool == "check_service":
        return check_service(str(params.get("name") or params.get("service") or ""), config=cfg)
    if tool == "analyze_disk_growth":
        return analyze_disk_growth(int(params.get("days", 7)), int(params.get("top", 10)), config=cfg)
    if tool == "tail_log":
        return tail_log(str(params.get("name", "app")), int(params.get("lines", 100)), config=cfg)
    if tool == "clean_old_packages":
        return clean_old_packages(int(params.get("days", 7)), confirm=confirm_flag, config=cfg)
    if tool == "clean_temp_files":
        return clean_temp_files(int(params.get("days", 3)), confirm=confirm_flag, config=cfg)
    if tool == "rotate_logs":
        return rotate_logs(int(params.get("max_mb", 100)), confirm=confirm_flag, config=cfg)
    if tool == "restart_service":
        return restart_service(str(params.get("name") or params.get("service") or ""), confirm=confirm_flag, config=cfg)
    if tool == "backup_incremental":
        return backup_incremental(str(params.get("subdir", "assets")), confirm=confirm_flag, config=cfg)
    raise ServerAdminError(f"未实现的工具：{tool}", code="unknown_tool")  # 理论不可达
