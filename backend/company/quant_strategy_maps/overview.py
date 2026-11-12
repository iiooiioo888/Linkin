"""策略庫總覽圖：架構／資料流／通用生命週期 IR。"""

from __future__ import annotations

from typing import Any

from .ir import _edge, _ir, _listing, _node, _unique_wired


def overview_architecture(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    data = catalog or _listing()
    nodes = [
        _node("feeds", "行情源", "external", status="hub", detail="Yahoo／東財／Frankfurter"),
        _node(
            "catalog",
            f"策略庫 {data.get('catalog_count', 0)}",
            "data",
            status="hub",
            detail="stock-quant 目錄",
        ),
    ]
    edges = [_edge("feeds", "catalog", "K 線")]
    planned_n = 0
    for group in data.get("groups") or []:
        gid = f"cat_{group['id']}"
        nodes.append(
            _node(
                gid,
                f"【{group['name']}】",
                "service",
                status="wired" if group.get("wired") else "catalog",
                detail=f"{group.get('wired', 0)}/{group.get('total', 0)}",
            )
        )
        edges.append(_edge("catalog", gid, ""))
        for item in _unique_wired(group):
            engine = str(item["engine"] or item["id"])
            nodes.append(
                _node(
                    engine,
                    item.get("name") or engine,
                    "api",
                    status="wired",
                    detail=engine,
                )
            )
            edges.append(_edge(gid, engine, "wired"))
            edges.append(_edge(engine, "backtest", ""))
        catalog_only = int(group.get("total") or 0) - len(_unique_wired(group))
        if catalog_only > 0:
            planned_n += catalog_only
            edges.append(_edge(gid, "planned", "規劃"))
    nodes.extend(
        [
            _node("backtest", "market_backtest", "api", status="hub"),
            _node("planned", f"{planned_n} 規劃項" if planned_n else "規劃項", "external", status="catalog"),
            _node("desk", "量化研究桌", "frontend", status="hub", detail="角色 tool_call"),
        ]
    )
    edges.extend(
        [
            _edge("backtest", "desk", "引用"),
        ]
    )
    return _ir("全部策略", "architecture", nodes, edges, extra_meta={"view": "overview"})


def overview_data_flow(catalog: dict[str, Any] | None = None) -> dict[str, Any]:
    data = catalog or _listing()
    nodes = [
        _node("yahoo", "Yahoo", "external", lane="source"),
        _node("eastmoney", "東方財富", "external", lane="source"),
        _node("frankfurter", "Frankfurter", "external", lane="source"),
        _node("coinpaprika", "CoinPaprika", "external", lane="source"),
        _node("kline", "market_kline", "data", lane="ingest"),
        _node("catalog", "market_strategy_catalog", "service", lane="select"),
        _node("engine", f"{data.get('engine_count', 29)} 引擎", "service", lane="select"),
        _node("backtest", "market_backtest", "api", lane="run"),
        _node("compare", "market_compare", "api", lane="run"),
        _node("walk", "market_walkforward", "api", lane="run"),
        _node("desk", "量化分析師", "frontend", lane="consume"),
    ]
    edges = [
        _edge("yahoo", "kline", "美股／A 股"),
        _edge("eastmoney", "kline", "A 股備援"),
        _edge("frankfurter", "kline", "外匯"),
        _edge("coinpaprika", "kline", "加密"),
        _edge("kline", "catalog", "標的"),
        _edge("catalog", "engine", "wired id"),
        _edge("engine", "backtest", "strategy"),
        _edge("engine", "compare", "全引擎"),
        _edge("engine", "walk", "樣本外"),
        _edge("backtest", "desk", "績效"),
        _edge("compare", "desk", "夏普排序"),
        _edge("walk", "desk", "穩健性"),
    ]
    lanes = [
        {"id": "source", "label": "行情源"},
        {"id": "ingest", "label": "K 線"},
        {"id": "select", "label": "選策略"},
        {"id": "run", "label": "回測"},
        {"id": "consume", "label": "角色"},
    ]
    return _ir("行情 → 策略 → 角色", "data-flow", nodes, edges, lanes=lanes, extra_meta={"view": "data_flow"})


def generic_lifecycle() -> dict[str, Any]:
    nodes = [
        _node("idle", "待命", "data", status="hub"),
        _node("fetch", "拉 K 線", "external"),
        _node("resolve", "解析策略 id", "service"),
        _node("compute", "計算指標", "service"),
        _node("signal", "產生訊號", "api"),
        _node("enter", "進場", "api", status="wired"),
        _node("skip", "觀望", "external", status="catalog"),
        _node("hold", "持倉", "api", status="wired"),
        _node("exit", "出場／止損", "api"),
        _node("stats", "績效摘要", "frontend", status="hub"),
        _node("fail", "無法回測", "external", status="catalog"),
    ]
    edges = [
        _edge("idle", "fetch", "market_kline"),
        _edge("fetch", "resolve", "symbol"),
        _edge("resolve", "compute", "wired"),
        _edge("resolve", "fail", "catalog"),
        _edge("compute", "signal", ""),
        _edge("signal", "enter", "long"),
        _edge("signal", "skip", "flat"),
        _edge("enter", "hold", ""),
        _edge("hold", "exit", "止損／死叉"),
        _edge("exit", "stats", ""),
        _edge("skip", "stats", ""),
    ]
    return _ir("回測生命週期", "lifecycle", nodes, edges, extra_meta={"view": "lifecycle"})
