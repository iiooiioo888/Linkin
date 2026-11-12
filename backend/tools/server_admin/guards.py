"""安全護欄 helper（自 backend.tools.server_admin 抽出）。

危險參數掃描、路徑牢籠、服務允許清單、審計寫入、大小格式與舊檔掃描。
"""

from __future__ import annotations

import fnmatch
import json
import logging
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import DANGEROUS_RE, SERVICE_NAME_RE, ServerAdminConfig, ServerAdminError

logger = logging.getLogger(__name__)


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
