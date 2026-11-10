"""CLI 運行時目錄：要用外部命令才能執行的技能／MCP。

Linkin 只檢查本機是否看得到命令，不代為安裝、不讀取 Cookie 或金鑰。
安裝仍由操作者在自己的環境執行（見各條目的 install）。
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CliRuntime:
    id: str
    skill_id: str
    binary: str
    title: str
    summary: str
    install: str
    group: str
    check_args: tuple[str, ...] = ("--help",)


# 固定目錄。新增項目時同步測試與 docs/mcp/agent-skills.md。
CLI_RUNTIMES: tuple[CliRuntime, ...] = (
    CliRuntime(
        id="agent-reach",
        skill_id="agent-reach",
        binary="agent-reach",
        title="Agent Reach",
        summary="即時閱讀與搜尋路由。不要從 PyPI 安裝同名套件。",
        install="pipx install https://github.com/Panniantong/agent-reach/archive/main.zip",
        group="採集",
    ),
    CliRuntime(
        id="just-scrape",
        skill_id="just-scrape",
        binary="just-scrape",
        title="just-scrape",
        summary="單頁結構化抓取。需要 SGAI_API_KEY，金鑰留在本機。",
        install="npm install -g just-scrape@latest",
        group="採集",
    ),
    CliRuntime(
        id="agent-browser",
        skill_id="agent-browser",
        binary="agent-browser",
        title="agent-browser",
        summary="瀏覽器自動化。安裝後還要在本機執行 agent-browser install 取得 Chromium。",
        install="npm install -g agent-browser",
        group="採集",
    ),
)

_BY_ID = {item.id: item for item in CLI_RUNTIMES}


def get_runtime(runtime_id: str) -> CliRuntime | None:
    return _BY_ID.get(runtime_id)


def probe_runtime(
    spec: CliRuntime,
    *,
    which: Callable[[str], str | None] | None = None,
    run: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    timeout: float = 8,
) -> dict[str, Any]:
    """回報命令是否在 PATH。找到時才跑固定的 --help，不接受外部參數。"""
    finder = which or shutil.which
    runner = run or subprocess.run
    path = finder(spec.binary) or ""
    row: dict[str, Any] = {
        "id": spec.id,
        "skill_id": spec.skill_id,
        "binary": spec.binary,
        "title": spec.title,
        "summary": spec.summary,
        "install": spec.install,
        "group": spec.group,
        "installed": bool(path),
        "path": path,
        "ok": False,
        "detail": "尚未安裝",
    }
    if not path:
        return row
    try:
        proc = runner(
            [path, *spec.check_args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        row["detail"] = "檢查逾時"
        return row
    except OSError as exc:
        row["detail"] = str(exc)[:160]
        return row
    text = (proc.stdout or proc.stderr or "").strip()
    first = text.splitlines()[0] if text else ""
    row["ok"] = proc.returncode == 0
    row["detail"] = (first or f"exit {proc.returncode}")[:160]
    return row


def probe_all(**kwargs: Any) -> list[dict[str, Any]]:
    return [probe_runtime(spec, **kwargs) for spec in CLI_RUNTIMES]


def format_status(rows: list[dict[str, Any]] | None = None) -> str:
    rows = probe_all() if rows is None else rows
    lines = ["CLI 技能運行時（只檢查，不安裝）", ""]
    for row in rows:
        state = "已安裝" if row.get("installed") else "未安裝"
        hint = row.get("path") if row.get("installed") else row.get("install")
        lines.append(f"{row.get('group', ''):<6} {row.get('title', ''):<16} {state:<6} {hint}")
        if row.get("installed") and row.get("detail"):
            lines.append(f"{'':<6} {'':<16} {'':<6} {row['detail']}")
    lines.append("")
    lines.append("安裝請在本機執行上列命令。Cookie 與金鑰不要寫進倉庫。")
    return "\n".join(lines)
