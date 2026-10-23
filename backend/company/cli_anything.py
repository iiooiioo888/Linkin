"""CLI-Anything hub：只查公開目錄，不安裝、不啟動個別軟體。"""

from __future__ import annotations

import os
import re
import shutil
import sys
import sysconfig
from pathlib import Path
from typing import Any

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_READ_ACTIONS = frozenset({"list", "search", "info", "installed"})
_MAX_QUERY = 80
_MAX_ITEMS = 40
_DESC_LIMIT = 160
NOTE = "這裡只查目錄。安裝、更新、解除或啟動個別 CLI 需要另行確認，Linkin 不會代為執行。"


def _candidate_bins() -> list[Path]:
    scripts = sysconfig.get_path("scripts") or ""
    return [
        Path(sys.executable).with_name("cli-hub"),
        Path(scripts) / "cli-hub" if scripts else Path("cli-hub"),
        Path.home() / ".local" / "bin" / "cli-hub",
    ]


def resolve_cli_hub_binary() -> str:
    """PATH 沒有 cli-hub 時，改看這個解釋器的 scripts 與使用者本地 bin。"""
    found = shutil.which("cli-hub")
    if found:
        return found
    for path in _candidate_bins():
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return ""


def _clean_query(value: str) -> str:
    text = "".join(ch for ch in (value or "") if ch.isprintable() and ch not in "\r\n\t")
    return " ".join(text.split())[:_MAX_QUERY]


def _https(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("https://") and " " not in text:
        return text[:300]
    return ""


def _project(cli: dict[str, Any], installed: set[str]) -> dict[str, Any]:
    name = str(cli.get("name") or "")
    return {
        "name": name,
        "display_name": str(cli.get("display_name") or name),
        "category": str(cli.get("category") or ""),
        "description": str(cli.get("description") or "")[:_DESC_LIMIT],
        "source": str(cli.get("_source") or ""),
        "version": str(cli.get("version") or ""),
        "homepage": _https(cli.get("homepage")),
        "installed": name in installed,
    }


def _load_hub() -> tuple[Any, Any, Any, Any, Any]:
    from cli_hub import __version__ as hub_version
    from cli_hub.installer import get_installed
    from cli_hub.registry import fetch_all_clis, get_cli, search_clis

    return hub_version, get_installed, fetch_all_clis, get_cli, search_clis


def _installed_names(get_installed: Any) -> set[str]:
    raw = get_installed() or {}
    if not isinstance(raw, dict):
        return set()
    return {str(name) for name in raw if _NAME_RE.fullmatch(str(name))}


def _base(action: str) -> dict[str, Any]:
    path = resolve_cli_hub_binary()
    return {
        "ok": False,
        "hub_installed": bool(path),
        "hub_path": path,
        "action": action,
        "items": [],
        "categories": [],
        "total": 0,
        "shown": 0,
        "note": NOTE,
        "detail": "",
    }


def query_cli_hub(
    action: str = "list",
    query: str = "",
    name: str = "",
    *,
    limit: int = 24,
    per_category: int = 8,
) -> dict[str, Any]:
    """查目錄。install／update／uninstall／launch 直接拒絕，不呼叫上游安裝器。"""
    action = (action or "list").strip().lower()
    cap = max(1, min(int(limit or 24), _MAX_ITEMS))
    row = _base(action)
    if action not in _READ_ACTIONS:
        row["detail"] = "這個動作需要另行確認，Linkin 只開放查目錄。"
        row["reason"] = "privilege"
        return row
    try:
        hub_version, get_installed, fetch_all_clis, get_cli, search_clis = _load_hub()
    except ImportError:
        row["hub_installed"] = False
        row["hub_path"] = ""
        row["detail"] = "尚未安裝 cli-anything-hub"
        return row

    row["version"] = str(hub_version)
    row["hub_installed"] = True
    try:
        installed = _installed_names(get_installed)
        if action == "installed":
            items = [{"name": item, "installed": True} for item in sorted(installed)]
            row.update(
                ok=True,
                items=items[:cap],
                total=len(items),
                shown=min(len(items), cap),
                detail="本機已安裝的 harness" if items else "尚未安裝個別 harness",
            )
            return row
        if action == "info":
            target = (name or query or "").strip()
            if not _NAME_RE.fullmatch(target):
                row["detail"] = "名稱只接受英數、點、底線與連字號。"
                return row
            found = get_cli(target)
            if not isinstance(found, dict):
                row.update(ok=True, detail="目錄裡沒有這個名稱。")
                return row
            item = _project(found, installed)
            row.update(ok=True, items=[item], total=1, shown=1, detail=item["name"])
            return row
        if action == "search":
            cleaned = _clean_query(query)
            if not cleaned:
                row["detail"] = "請提供搜尋字。"
                return row
            raw_rows = search_clis(cleaned)
            items = [
                _project(item, installed)
                for item in raw_rows
                if isinstance(item, dict) and _NAME_RE.fullmatch(str(item.get("name") or ""))
            ]
            items.sort(key=lambda item: (item["category"].lower(), item["name"].lower()))
            row.update(
                ok=True,
                items=items[:cap],
                total=len(items),
                shown=min(len(items), cap),
                detail=f"共 {len(items)} 筆",
            )
            return row
        raw_rows = fetch_all_clis()
        grouped: dict[str, list[str]] = {}
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            cli_name = str(item.get("name") or "")
            if not _NAME_RE.fullmatch(cli_name):
                continue
            category = str(item.get("category") or "uncategorized")
            grouped.setdefault(category, []).append(cli_name)
        categories: list[dict[str, Any]] = []
        total = 0
        shown = 0
        for category in sorted(grouped, key=str.lower):
            names = sorted(set(grouped[category]), key=str.lower)
            total += len(names)
            visible = names if per_category <= 0 else names[:per_category]
            shown += len(visible)
            categories.append({"category": category, "count": len(names), "names": visible})
        row.update(
            ok=True,
            categories=categories,
            total=total,
            shown=shown,
            detail=f"共 {total} 個 CLI，{len(categories)} 個分類",
        )
        return row
    except Exception as exc:
        row["detail"] = (str(exc) or "目錄查詢失敗")[:160]
        return row
