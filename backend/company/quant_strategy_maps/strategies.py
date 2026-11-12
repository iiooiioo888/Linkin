"""策略圖：分類拓撲、單策略工作流／生命週期、預覽與 Archify 檢視。"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_catalog import CATALOG_CATEGORIES, resolve_strategy

from .ir import (
    _CATEGORY_EDGES,
    _CATEGORY_FLOW,
    _ENGINE_OVERRIDE,
    ARCHIFY_SOURCE,
    CATALOG_SOURCE,
    _edge,
    _find_item,
    _ir,
    _listing,
    _node,
    _unique_wired,
)
from .overview import generic_lifecycle, overview_architecture, overview_data_flow


def group_architecture(group: dict[str, Any]) -> dict[str, Any]:
    gid = group["id"]
    name = group["name"]
    wired = _unique_wired(group)
    catalog_n = max(0, int(group.get("total") or 0) - len(wired))
    nodes = [
        _node(
            f"hub_{gid}",
            f"【{name}】",
            "data",
            status="hub",
            detail=f"{len(wired)} 引擎 / {group.get('total', 0)} 目錄",
        )
    ]
    edges: list[dict[str, Any]] = []
    for item in wired:
        engine = str(item.get("engine") or item["id"])
        nodes.append(
            _node(
                engine,
                item.get("name") or engine,
                "service",
                status="wired",
                detail=engine,
            )
        )
        edges.append(_edge(f"hub_{gid}", engine, "wired"))
        edges.append(_edge(engine, "backtest", engine))
    if catalog_n:
        nodes.append(_node("planned", f"{catalog_n} 規劃項", "external", status="catalog"))
        edges.append(_edge(f"hub_{gid}", "planned", "目錄"))
    nodes.append(_node("backtest", "market_backtest", "api", status="hub"))
    return _ir(
        f"【{name}】策略拓撲",
        "architecture",
        nodes,
        edges,
        extra_meta={"view": f"group:{gid}", "category": gid},
    )


def _workflow_spec(item: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, str]]]:
    engine = item.get("engine") or item.get("id")
    cat = item.get("category") or "ma"
    override = _ENGINE_OVERRIDE.get(str(engine))
    if override:
        node_spec, edge_spec = override
    else:
        node_spec = _CATEGORY_FLOW.get(cat) or _CATEGORY_FLOW["ma"]
        edge_spec = _CATEGORY_EDGES.get(cat) or _CATEGORY_EDGES["ma"]
    role_lane = {
        "external": "source",
        "data": "source",
        "service": "signal",
        "api": "trade",
        "frontend": "report",
    }
    nodes = [
        _node(nid, label, role, lane=role_lane.get(role, "signal"), status=item.get("status") or "")
        for nid, label, role in node_spec
    ]
    if item.get("status") != "wired":
        nodes.append(_node("blocked", "規劃・不可回測", "external", lane="report", status="catalog"))
    edges = [_edge(a, b, label) for a, b, label in edge_spec]
    if item.get("status") != "wired":
        last = node_spec[-1][0]
        edges.append(_edge(last, "blocked", "未接通"))
    lanes = [
        {"id": "source", "label": "行情"},
        {"id": "signal", "label": "指標／訊號"},
        {"id": "trade", "label": "進出場"},
        {"id": "report", "label": "產出"},
    ]
    return nodes, edges, lanes


def strategy_workflow(item: dict[str, Any]) -> dict[str, Any]:
    nodes, edges, lanes = _workflow_spec(item)
    title = f"{item.get('name') or item['id']} · 工作流"
    return _ir(
        title,
        "workflow",
        nodes,
        edges,
        lanes=lanes,
        extra_meta={"view": f"strategy:{item['id']}", "strategy": item["id"]},
    )


def strategy_lifecycle(item: dict[str, Any]) -> dict[str, Any]:
    wired = item.get("status") == "wired"
    nodes = [
        _node("pick", f"選 {item.get('id')}", "data", status="hub"),
        _node("resolve", resolve_strategy(item.get("id") or "") or "無引擎", "service"),
        _node("bars", "market_kline", "external"),
        _node("run", "market_backtest", "api", status="wired" if wired else "catalog"),
        _node("stats", "夏普／回撤", "frontend", status="hub"),
        _node("block", "目錄項不可跑", "external", status="catalog"),
    ]
    edges = [
        _edge("pick", "resolve", "別名"),
        _edge("resolve", "bars", "wired" if wired else ""),
        _edge("bars", "run", "K 線"),
        _edge("run", "stats", "績效" if wired else ""),
    ]
    if not wired:
        edges.append(_edge("resolve", "block", "catalog"))
    return _ir(
        f"{item.get('name') or item['id']} · 生命週期",
        "lifecycle",
        nodes,
        edges,
        extra_meta={"view": f"lifecycle:{item['id']}", "strategy": item["id"]},
    )


def strategy_maps(strategy_id: str, catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    data = catalog or _listing()
    item = _find_item(data, strategy_id)
    if item is None:
        return {
            "ok": False,
            "error": f"未知策略 {strategy_id}。先呼叫 market_strategy_catalog 或 archify_strategies。",
            "tool": "archify_strategies",
        }
    group = next((g for g in (data.get("groups") or []) if g["id"] == item["category"]), None)
    return {
        "ok": True,
        "inspired_by": ARCHIFY_SOURCE,
        "catalog": CATALOG_SOURCE,
        "item": item,
        "architecture": group_architecture(group) if group else overview_architecture(data),
        "workflow": strategy_workflow(item),
        "lifecycle": strategy_lifecycle(item),
        "hint": (
            f"wired 用 market_backtest.strategy = {item.get('engine') or item['id']}"
            if item.get("status") == "wired"
            else "規劃項，尚未接通引擎，不可回測。"
        ),
    }


def _demo_preview_chart(engine: str, symbol: str, reason: str) -> dict[str, Any]:
    """行情源失敗時仍給實驗室一條可畫的確定性曲線。"""
    n = 72
    seed = sum(ord(ch) for ch in f"{engine}:{symbol}") or 1
    equity: list[dict[str, Any]] = []
    hold: list[dict[str, Any]] = []
    close: list[dict[str, Any]] = []
    eq = 1.0
    price = 80.0 + (seed % 40)
    base = price
    peak = 1.0
    max_dd = 0.0
    for i in range(n):
        wave = ((i + seed) % 13 - 6) * 0.004
        price = max(5.0, price * (1 + wave))
        eq = max(0.4, eq * (1 + wave * 0.7 + ((i % 9) - 4) * 0.0015))
        peak = max(peak, eq)
        if peak:
            max_dd = max(max_dd, (peak - eq) / peak)
        stamp = str(i)
        close.append({"t": stamp, "v": round(price, 4)})
        hold.append({"t": stamp, "v": round(price / base, 6)})
        equity.append({"t": stamp, "v": round(eq, 6)})
    return {
        "ok": True,
        "demo": True,
        "symbol": symbol,
        "strategy": engine,
        "total_return": round(equity[-1]["v"] - 1.0, 6),
        "max_drawdown": round(max_dd, 6),
        "sharpe": round(0.4 + (seed % 10) / 20, 2),
        "trades": 3 + seed % 8,
        "last_signal": "hold",
        "chart": {"equity": equity, "hold": hold, "close": close},
        "note": f"示範曲線（{reason[:120]}）",
        "disclaimer": "示範曲線僅供介面預覽，禁止當作收益保證。",
    }


def strategy_preview(strategy_id: str, symbol: str = "600519") -> dict[str, Any]:
    """實驗室預覽：工作流 IR +（可回測時）權益／收盤曲線。"""
    payload = strategy_maps(strategy_id)
    if not payload.get("ok"):
        return payload
    item = payload.get("item") or {}
    code = (symbol or "600519").strip() or "600519"
    payload["symbol"] = code
    if item.get("status") != "wired":
        payload["chart"] = None
        return payload
    from backend.company.quant_tools import market_backtest

    engine = str(item.get("engine") or item.get("id") or "")
    try:
        chart = market_backtest(code, strategy=engine, include_chart=True)
    except Exception as exc:
        chart = {"ok": False, "error": str(exc)[:400], "tool": "market_backtest"}
    series = chart.get("chart") if isinstance(chart, dict) else None
    has_equity = isinstance(series, dict) and bool(series.get("equity"))
    if not chart.get("ok") or not has_equity:
        reason = str(chart.get("error") or "行情源暫時不可用")
        payload["chart"] = _demo_preview_chart(engine, code, reason)
        return payload
    payload["chart"] = chart
    return payload


def strategy_catalog_maps() -> dict[str, Any]:
    data = _listing()
    groups = []
    views = [
        {"id": "overview", "title": "策略庫總覽", "kind": "architecture"},
        {"id": "data_flow", "title": "行情 → 回測 → 角色", "kind": "data-flow"},
        {"id": "lifecycle", "title": "回測生命週期", "kind": "lifecycle"},
    ]
    for group in data.get("groups") or []:
        groups.append(
            {
                "id": group["id"],
                "name": group["name"],
                "total": group["total"],
                "wired": group["wired"],
                "items": group["items"],
                "architecture": group_architecture(group),
            }
        )
        views.append(
            {
                "id": f"group:{group['id']}",
                "title": f"【{group['name']}】",
                "kind": "architecture",
            }
        )
    return {
        "ok": True,
        "inspired_by": ARCHIFY_SOURCE,
        "catalog": CATALOG_SOURCE,
        "engine_count": data.get("engine_count"),
        "catalog_count": data.get("catalog_count"),
        "wired_count": data.get("wired_count"),
        "overview": overview_architecture(data),
        "data_flow": overview_data_flow(data),
        "lifecycle": generic_lifecycle(),
        "groups": groups,
        "views": views,
        "disclaimer": data.get("disclaimer"),
          "hint": "Archify CLI 可視化。點分類看該類可回測引擎；點策略看工作流。角色可 archify_strategies。",
    }


def archify_strategies(view: str = "overview", id: str = "") -> dict[str, Any]:
    """公司工具：依 view 回傳 Archify IR。"""
    want = (view or "overview").strip().lower()
    key = (id or "").strip()
    data = _listing()
    if want in {"overview", "catalog", "all", ""}:
        return strategy_catalog_maps()
    if want in {"data_flow", "data-flow", "flow"}:
        return {"ok": True, "ir": overview_data_flow(data), "view": "data_flow"}
    if want == "lifecycle" and not key:
        return {"ok": True, "ir": generic_lifecycle(), "view": "lifecycle"}
    if want in {"group", "category"} or want.startswith("group:"):
        cid = key or want.split(":", 1)[-1]
        cid = cid.strip().lower()
        if cid in {"oscillator", "osc"}:
            cid = "momentum"
        group = next((g for g in (data.get("groups") or []) if g["id"] == cid), None)
        if group is None:
            allowed = " / ".join(CATALOG_CATEGORIES)
            return {"ok": False, "error": f"未知分類 {cid}，可用 {allowed}", "tool": "archify_strategies"}
        return {"ok": True, "ir": group_architecture(group), "view": f"group:{cid}", "group": group["id"]}
    if want in {"strategy", "workflow"} or want.startswith("strategy:") or key:
        sid = key
        if not sid and ":" in want:
            sid = want.split(":", 1)[-1]
        if not sid:
            return {"ok": False, "error": "請傳 id=策略 id", "tool": "archify_strategies"}
        return strategy_maps(sid, data)
    return {
        "ok": False,
        "error": "view 可用 overview／data_flow／lifecycle／group／strategy",
        "tool": "archify_strategies",
    }
