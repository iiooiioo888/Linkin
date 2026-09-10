"""服务器运维底层桥接：psutil / docker / systemd / 文件系统的安全封装。

设计遵循 Minecraft MCP 同款双层护栏哲学（AGENTS.md 铁律 #5）：

- **读操作**（磁盘/CPU/内存/Docker/systemd 状态）永远安全执行、跨平台降级
- **写操作**（清理/重启/轮转/备份）需 ``confirm``，且 ``dry_run`` 时只模拟不落盘
- **路径牢笼**：所有文件操作必须落在 ``STORAGE_ROOT`` 允许清单内（防路径穿越）
- **服务允许清单**：只能操作白名单内的 systemd 服务（防重启任意服务）
- **危险模式兜底**：任何字符串参数命中 ``rm -rf /`` 等一律拒绝（defense-in-depth）
- **审计**：所有写操作（含模拟）写入 JSONL 审计日志

配置经环境变量，``load_config()`` 每次读取（与 minecraft_mcp 一致）：
    EVOL_SA_ENABLED        默认 false → dry_run（只模拟，不落盘）
    EVOL_SA_STORAGE_ROOT   默认 /data/mmorpg（Windows 回退到工作区）
    EVOL_SA_BACKUP_DIR     默认 STORAGE_ROOT/backups
    EVOL_SA_AUDIT_PATH     默认 backend/data/linkin/server_audit.jsonl
    EVOL_SA_SERVICES       逗号分隔允许清单（默认 linkin-api,mysql,redis-server,nginx）

**绝不接受自由 shell 命令**——只暴露具名工具，参数强类型校验。
"""

from __future__ import annotations

import fnmatch
import gzip
import json
import logging
import os
import re
import shutil
import subprocess
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

logger = logging.getLogger(__name__)

try:  # psutil 为运维指标的软依赖；缺失时读操作降级而非崩溃
    import psutil
except Exception:
    psutil = None  # type: ignore[assignment]

# ── 默认值与常量 ──
DEFAULT_STORAGE_ROOT = "/data/mmorpg"
DEFAULT_SERVICES = ("linkin-api", "mysql", "redis-server", "nginx")
MAX_DELETE_PER_CALL = 5000          # 单次清理删除文件数上限（防误删爆炸）
MAX_BACKUP_BYTES = 2 * 1024**3      # 单次备份字节上限（2 GiB）
MAX_LOG_BYTES = 64 * 1024**2        # 单日志轮转上限（64 MiB）
MAX_SCAN_FILES = 20_000             # 磁盘增长分析扫描文件数上限
SUBPROCESS_TIMEOUT = 60             # systemd 调用超时（秒）
LOG_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")

_TRUE = {"1", "true", "yes", "on", "y"}

# 服务名：仅允许 systemd 单元名的安全字符
SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@-]{1,64}$")

# 危险模式兜底：即便我们不接受自由 shell，也对所有字符串参数做一层防御
DANGEROUS_RE = re.compile(
    r"("
    r"rm\s+-[rf]{1,2}\s+/(\s|$)|rm\s+-rf\s+\*|mkfs(\.|\s)|dd\s+if=|:\(\)\s*\{|"
    r">\s*/dev/[sh]d|chmod\s+-R\s+0?777\s+/|chown\s+-R\s+.*\s+/(\s|$)|"
    r"shutdown|reboot|halt\b|poweroff|init\s+0|init\s+6|"
    r"format\s+[a-z]:|del\s+/[sfq]|rmdir\s+/s"
    r")",
    re.IGNORECASE,
)


class ServerAdminError(ValueError):
    """运维工具参数或安全护栏校验失败。"""

    def __init__(self, message: str, *, code: str = "invalid", extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.extra = extra or {}


@dataclass
class ServerAdminConfig:
    enabled: bool = False
    storage_root: Path = field(default_factory=lambda: Path(DEFAULT_STORAGE_ROOT))
    backup_dir: Path = field(default_factory=lambda: Path(DEFAULT_STORAGE_ROOT) / "backups")
    audit_path: Path = field(default_factory=lambda: Path("backend/data/linkin/server_audit.jsonl"))
    allow_services: tuple[str, ...] = DEFAULT_SERVICES

    @property
    def dry_run(self) -> bool:
        """未显式启用即视为乾跑（只模拟，不落盘）——与 Minecraft MCP 一致。"""
        return not self.enabled


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in _TRUE


def load_config() -> ServerAdminConfig:
    """每次读取环境变量（测试用 monkeypatch.setenv 即时生效）。"""
    enabled = _env_bool("EVOL_SA_ENABLED", False)
    root_raw = os.getenv("EVOL_SA_STORAGE_ROOT", "").strip() or DEFAULT_STORAGE_ROOT
    storage_root = Path(root_raw).expanduser()
    backup_raw = os.getenv("EVOL_SA_BACKUP_DIR", "").strip()
    backup_dir = Path(backup_raw).expanduser() if backup_raw else storage_root / "backups"
    audit_raw = os.getenv("EVOL_SA_AUDIT_PATH", "").strip()
    audit_path = (
        Path(audit_raw).expanduser()
        if audit_raw
        else Path("backend/data/linkin/server_audit.jsonl")
    )
    services_raw = os.getenv("EVOL_SA_SERVICES", "").strip()
    allow_services = (
        tuple(s.strip() for s in services_raw.split(",") if s.strip())
        if services_raw
        else DEFAULT_SERVICES
    )
    return ServerAdminConfig(
        enabled=enabled,
        storage_root=storage_root,
        backup_dir=backup_dir,
        audit_path=audit_path,
        allow_services=allow_services,
    )


# ── 安全护栏 ──


def _guard_dangerous(value: Any) -> None:
    """对任意字符串（含嵌套）扫描危险模式，命中即拒绝。"""
    if isinstance(value, str):
        if DANGEROUS_RE.search(value):
            raise ServerAdminError(
                "参数命中危险操作模式，已拒绝", code="dangerous_input", extra={"input": value[:120]}
            )
    elif isinstance(value, dict):
        for item in value.values():
            _guard_dangerous(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _guard_dangerous(item)


def _resolve_under_root(cfg: ServerAdminConfig, target: str | Path | None = None) -> Path:
    """把 target 解析为绝对路径，并确保落在 storage_root 内（防路径穿越）。"""
    root = cfg.storage_root.expanduser()
    try:
        root_resolved = root.resolve()
    except OSError:
        root_resolved = root.absolute()
    if target is None or str(target).strip() == "":
        return root_resolved
    text = str(target).strip()
    _guard_dangerous(text)
    candidate_path = Path(text).expanduser()
    if candidate_path.is_absolute():
        candidate = candidate_path
    else:
        candidate = root / candidate_path
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate.absolute()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise ServerAdminError(
            f"路径越界：{text} 不在存储根 {root} 内",
            code="path_denied",
            extra={"target": text, "root": str(root)},
        )
    return resolved


def _check_service(cfg: ServerAdminConfig, name: str) -> str:
    """校验服务名格式与允许清单，返回规范化名称。"""
    text = str(name or "").strip()
    _guard_dangerous(text)
    if not text:
        raise ServerAdminError("需要服务名", code="invalid")
    if not SERVICE_NAME_RE.match(text):
        raise ServerAdminError(
            f"非法服务名：{text}", code="invalid_service", extra={"service": text}
        )
    if text not in cfg.allow_services:
        raise ServerAdminError(
            f"服务「{text}」不在允许清单。允许：{'、'.join(cfg.allow_services)}",
            code="service_denied",
            extra={"service": text, "allowed": list(cfg.allow_services)},
        )
    return text


def _append_audit(cfg: ServerAdminConfig, entry: dict[str, Any]) -> None:
    """把一次操作追加到 JSONL 审计日志（失败不阻断主流程）。"""
    row = {"ts": time.time(), "dry_run": cfg.dry_run, **entry}
    try:
        cfg.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with cfg.audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:  # 审计写失败不该让运维操作整体失败
        logger.warning("写入运维审计失败：%s", exc)


def _human_bytes(num: float) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024:
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}PB"


def _scan_old_files(directory: Path, patterns: Iterable[str], days: int) -> list[dict[str, Any]]:
    """扫描 directory 下匹配 patterns（空=全部）且 mtime 早于 days 天的文件。"""
    if not directory.exists() or not directory.is_dir():
        return []
    cutoff = time.time() - max(0, int(days)) * 86400
    matched: list[dict[str, Any]] = []
    pats = list(patterns)
    for path in directory.rglob("*"):
        try:
            if not path.is_file():
                continue
            if pats and not any(fnmatch.fnmatch(path.name, p) for p in pats):
                continue
            stat = path.stat()
            if stat.st_mtime < cutoff:
                matched.append(
                    {"path": str(path), "name": path.name, "size": int(stat.st_size), "mtime": stat.st_mtime}
                )
        except OSError:
            continue
    matched.sort(key=lambda r: r["mtime"])
    return matched


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
