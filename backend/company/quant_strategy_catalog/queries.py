"""策略目錄查詢：引擎 id、別名解析、狀態與分組、market_strategy_catalog。"""

from __future__ import annotations

from typing import Any

from .data import _ENGINE_ROWS, CATALOG_CATEGORIES, ENGINE_ALIASES
from .rows import _CATALOG_ROWS


def _engine_ids() -> set[str]:
    return {sid for sid, _name, _cat in _ENGINE_ROWS}


def resolve_strategy(name: str) -> str | None:
    """把目錄 id／別名解析成可回測引擎 id；無法回測則回 None。"""
    key = (name or "").strip().lower()
    if not key:
        return None
    engines = _engine_ids()
    if key in engines:
        return key
    mapped = ENGINE_ALIASES.get(key)
    if mapped in engines:
        return mapped
    return None


def _status_for(sid: str, engines: set[str]) -> str:
    if sid in engines or ENGINE_ALIASES.get(sid) in engines:
        return "wired"
    return "catalog"


def _all_items(engines: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for sid, name, cat in (*_ENGINE_ROWS, *_CATALOG_ROWS):
        if sid in seen:
            continue
        seen.add(sid)
        engine = resolve_strategy(sid) if sid in engines or sid in ENGINE_ALIASES else None
        if sid in engines:
            engine = sid
        items.append(
            {
                "id": sid,
                "name": name,
                "category": cat,
                "category_name": CATALOG_CATEGORIES.get(cat, cat),
                "status": _status_for(sid, engines),
                "engine": engine,
            }
        )
    return items


def _groups_for(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    for cid, label in CATALOG_CATEGORIES.items():
        children = [row for row in items if row["category"] == cid]
        if not children:
            continue
        groups.append(
            {
                "id": cid,
                "name": label,
                "total": len(children),
                "wired": sum(1 for row in children if row["status"] == "wired"),
                "items": children,
            }
        )
    return groups


def market_strategy_catalog(
    category: str = "",
    query: str = "",
    status: str = "",
    listing: bool = False,
) -> dict[str, Any]:
    """列出策略庫。未篩選時回摘要＋可回測引擎，避免塞爆上下文。"""
    engines = _engine_ids()
    items = _all_items(engines)
    cat = (category or "").strip().lower()
    if cat in {"oscillator", "osc"}:
        cat = "momentum"
    q = (query or "").strip().lower()
    want_status = (status or "").strip().lower()
    want_listing = listing is True or str(listing).strip().lower() in {"1", "true", "yes"}
    filtered = items
    if cat:
        if cat not in CATALOG_CATEGORIES:
            allowed = " / ".join(CATALOG_CATEGORIES)
            return {
                "ok": False,
                "error": f"未知分類 {category}，可用 {allowed}",
                "tool": "market_strategy_catalog",
            }
        filtered = [row for row in filtered if row["category"] == cat]
    if q:
        filtered = [
            row
            for row in filtered
            if q in row["id"] or q in row["name"].lower() or q in row["category"]
        ]
    if want_status in {"wired", "catalog"}:
        filtered = [row for row in filtered if row["status"] == want_status]

    cat_stats: list[dict[str, Any]] = []
    for cid, label in CATALOG_CATEGORIES.items():
        group = [row for row in items if row["category"] == cid]
        cat_stats.append(
            {
                "id": cid,
                "name": label,
                "total": len(group),
                "wired": sum(1 for row in group if row["status"] == "wired"),
            }
        )

    show_list = bool(cat or q or want_status or want_listing)
    payload: dict[str, Any] = {
        "ok": True,
        "inspired_by": "https://github.com/iiooiioo888/stock-quant",
        "engine_count": len(engines),
        "catalog_count": len(items),
        "wired_count": sum(1 for row in items if row["status"] == "wired"),
        "categories": cat_stats,
        "disclaimer": "wired 可 market_backtest；catalog 僅目錄／規劃，禁止當收益保證。",
    }
    if show_list:
        payload["matched"] = len(filtered)
        payload["items"] = filtered
        payload["groups"] = _groups_for(filtered)
        payload["hint"] = "把 items[].engine 或 wired 的 id 傳給 market_backtest.strategy。"
    else:
        payload["engines"] = [
            {"id": sid, "name": name, "category": cat}
            for sid, name, cat in _ENGINE_ROWS
            if sid in engines
        ]
        payload["hint"] = (
            "預設只回可回測引擎與分類計數。傳 listing=true 或 category=ma／momentum／mean_reversion／"
            "volatility／trend／pattern／breakout／composite／ml，或 query／status=wired|catalog 列出目錄。"
        )
    return payload
