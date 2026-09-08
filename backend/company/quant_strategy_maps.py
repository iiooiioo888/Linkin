"""stock-quant 策略庫 → Archify IR（確定性，不經 LLM）。

對齊 tt-a1i/archify 的 architecture / workflow / data-flow / lifecycle，
把策略庫總覽、分類拓撲與單策略工作流編成 typed JSON IR，前端 SVG 渲染。
"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_catalog import (
    CATALOG_CATEGORIES,
    market_strategy_catalog,
    resolve_strategy,
)

ARCHIFY_SOURCE = "https://github.com/tt-a1i/archify"
CATALOG_SOURCE = "https://github.com/iiooiioo888/stock-quant"

_CATEGORY_FLOW: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ma": (
        ("bars", "K 線", "data"),
        ("fast", "短均線", "service"),
        ("slow", "長均線", "service"),
        ("cross", "金叉／死叉", "service"),
        ("pos", "持倉", "api"),
        ("risk", "止損／T+1", "api"),
        ("stats", "績效", "frontend"),
    ),
    "momentum": (
        ("bars", "K 線", "data"),
        ("osc", "震盪指標", "service"),
        ("zone", "超買／超賣", "service"),
        ("signal", "進出場訊號", "api"),
        ("risk", "風控", "api"),
        ("stats", "績效", "frontend"),
    ),
    "mean_reversion": (
        ("bars", "K 線", "data"),
        ("band", "通道／Z-score", "service"),
        ("dev", "偏離判定", "service"),
        ("entry", "回歸入場", "api"),
        ("exit", "回歸出場", "api"),
        ("stats", "績效", "frontend"),
    ),
    "volatility": (
        ("bars", "高低收", "data"),
        ("atr", "ATR／波動", "service"),
        ("regime", "擴張或收縮", "service"),
        ("trail", "追蹤止損", "api"),
        ("stats", "績效", "frontend"),
    ),
    "trend": (
        ("bars", "K 線", "data"),
        ("filter", "趨勢濾網", "service"),
        ("break", "突破入場", "api"),
        ("trail", "移動止損", "api"),
        ("stats", "績效", "frontend"),
    ),
    "pattern": (
        ("bars", "K 線", "data"),
        ("shape", "形態識別", "service"),
        ("confirm", "量價確認", "service"),
        ("entry", "形態入場", "api"),
        ("invalidate", "失效出場", "api"),
        ("stats", "績效", "frontend"),
    ),
    "breakout": (
        ("bars", "K 線", "data"),
        ("range", "區間高點", "service"),
        ("break", "突破", "service"),
        ("retest", "回測確認", "api"),
        ("risk", "風控", "api"),
        ("stats", "績效", "frontend"),
    ),
    "composite": (
        ("members", "子策略訊號", "data"),
        ("vote", "投票／加權", "service"),
        ("consensus", "共識閾值", "service"),
        ("pos", "持倉", "api"),
        ("stats", "績效", "frontend"),
    ),
    "ml": (
        ("feat", "特徵工程", "data"),
        ("model", "模型（規劃）", "external"),
        ("signal", "訊號（未接通）", "service"),
        ("gate", "不可回測", "api"),
    ),
}

_CATEGORY_EDGES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ma": (
        ("bars", "fast", "SMA/EMA"),
        ("bars", "slow", "SMA/EMA"),
        ("fast", "cross", "比較"),
        ("slow", "cross", "比較"),
        ("cross", "pos", "多／空"),
        ("pos", "risk", "出場"),
        ("risk", "stats", "權益"),
    ),
    "momentum": (
        ("bars", "osc", "計算"),
        ("osc", "zone", "閾值"),
        ("zone", "signal", "訊號"),
        ("signal", "risk", "過濾"),
        ("risk", "stats", "權益"),
    ),
    "mean_reversion": (
        ("bars", "band", "統計"),
        ("band", "dev", "偏離"),
        ("dev", "entry", "進場"),
        ("entry", "exit", "回歸"),
        ("exit", "stats", "權益"),
    ),
    "volatility": (
        ("bars", "atr", "波幅"),
        ("atr", "regime", "體制"),
        ("regime", "trail", "止損"),
        ("trail", "stats", "權益"),
    ),
    "trend": (
        ("bars", "filter", "方向"),
        ("filter", "break", "入場"),
        ("break", "trail", "移動止損"),
        ("trail", "stats", "權益"),
    ),
    "pattern": (
        ("bars", "shape", "K 線"),
        ("shape", "confirm", "確認"),
        ("confirm", "entry", "入場"),
        ("entry", "invalidate", "失效"),
        ("invalidate", "stats", "權益"),
    ),
    "breakout": (
        ("bars", "range", "N 日高"),
        ("range", "break", "穿越"),
        ("break", "retest", "回測"),
        ("retest", "risk", "風控"),
        ("risk", "stats", "權益"),
    ),
    "composite": (
        ("members", "vote", "計票"),
        ("vote", "consensus", "≥2"),
        ("consensus", "pos", "進場"),
        ("pos", "stats", "權益"),
    ),
    "ml": (
        ("feat", "model", "推論"),
        ("model", "signal", "輸出"),
        ("signal", "gate", "規劃"),
    ),
}

_ENGINE_OVERRIDE: dict[str, tuple[tuple[str, str, str], tuple[tuple[str, str, str], ...]]] = {
    "dual_ma": (
        (
            ("bars", "K 線", "data"),
            ("sma5", "SMA 短", "service"),
            ("sma20", "SMA 長", "service"),
            ("cross", "金叉／死叉", "service"),
            ("pos", "持倉", "api"),
            ("risk", "止損／T+1", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "sma5", "5"),
            ("bars", "sma20", "20"),
            ("sma5", "cross", ""),
            ("sma20", "cross", ""),
            ("cross", "pos", "多／空"),
            ("pos", "risk", ""),
            ("risk", "stats", ""),
        ),
    ),
    "macd": (
        (
            ("bars", "K 線", "data"),
            ("dif", "DIF", "service"),
            ("dea", "DEA", "service"),
            ("hist", "柱狀圖", "service"),
            ("cross", "金叉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "dif", "EMA"),
            ("dif", "dea", "信號線"),
            ("dif", "hist", ""),
            ("dea", "hist", ""),
            ("hist", "cross", "翻正"),
            ("cross", "stats", ""),
        ),
    ),
    "rsi": (
        (
            ("bars", "K 線", "data"),
            ("rsi", "RSI", "service"),
            ("os", "超賣 <30", "service"),
            ("ob", "超買 >70", "service"),
            ("pos", "持倉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "rsi", "14"),
            ("rsi", "os", ""),
            ("rsi", "ob", ""),
            ("os", "pos", "做多"),
            ("ob", "pos", "平倉"),
            ("pos", "stats", ""),
        ),
    ),
    "composite": (
        (
            ("dual", "雙均線票", "data"),
            ("rsi", "RSI 票", "data"),
            ("macd", "MACD 票", "data"),
            ("vote", "多數決 ≥2", "service"),
            ("pos", "持倉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("dual", "vote", ""),
            ("rsi", "vote", ""),
            ("macd", "vote", ""),
            ("vote", "pos", "共識"),
            ("pos", "stats", ""),
        ),
    ),
    "single_volume": (
        (
            ("bars", "K 線／成交量", "data"),
            ("vma5", "5 日均量", "service"),
            ("vma20", "20 日均量", "service"),
            ("std", "量能標準差", "service"),
            ("streak", "連續陰陽線", "service"),
            ("sig", "普通訊號", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "vma5", ""),
            ("bars", "vma20", ""),
            ("vma20", "std", "動態閾值"),
            ("bars", "streak", ""),
            ("vma5", "sig", "放量"),
            ("std", "sig", ""),
            ("streak", "sig", "確認"),
            ("sig", "stats", ""),
        ),
    ),
    "enhanced_volume": (
        (
            ("vol", "成交量分析", "data"),
            ("rsi", "RSI", "service"),
            ("bb", "布林帶", "service"),
            ("kdj", "KDJ", "service"),
            ("ord", "普通訊號", "service"),
            ("enh", "增強訊號 ≥2", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("vol", "ord", "均量／連續K"),
            ("rsi", "enh", "過濾"),
            ("bb", "enh", "過濾"),
            ("kdj", "enh", "過濾"),
            ("ord", "enh", "升級"),
            ("enh", "stats", "降假訊號"),
        ),
    ),
}


def _ir(
    title: str,
    kind: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    lanes: list[dict[str, str]] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "title": title,
        "type": kind,
        "locale": "zh-TW",
        "source": "archify",
        "inspired_by": ARCHIFY_SOURCE,
        "visual_preset": "signal-flow",
    }
    if extra_meta:
        meta.update(extra_meta)
    payload: dict[str, Any] = {"meta": meta, "nodes": nodes, "edges": edges}
    if lanes:
        payload["lanes"] = lanes
    return payload


def _node(
    nid: str,
    label: str,
    role: str,
    *,
    status: str = "",
    lane: str = "",
    detail: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": nid, "label": label, "role": role}
    if status:
        row["status"] = status
    if lane:
        row["lane"] = lane
    if detail:
        row["detail"] = detail
    return row


def _edge(src: str, dst: str, label: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"from": src, "to": dst}
    if label:
        row["label"] = label
    return row


def _listing() -> dict[str, Any]:
    return market_strategy_catalog(listing=True)


def _unique_wired(group: dict[str, Any]) -> list[dict[str, Any]]:
    """分類裡可回測的正規引擎（略過別名，避免同一引擎畫兩次）。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in group.get("items") or []:
        if item.get("status") != "wired":
            continue
        engine = str(item.get("engine") or item.get("id") or "")
        if not engine or engine in seen:
            continue
        if str(item.get("id") or "") != engine:
            continue
        seen.add(engine)
        out.append(item)
    return out


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


def _find_item(catalog: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    key = (strategy_id or "").strip().lower()
    if not key:
        return None
    for group in catalog.get("groups") or []:
        for item in group.get("items") or []:
            if str(item.get("id", "")).lower() == key:
                return item
            if str(item.get("engine") or "").lower() == key:
                return item
    engine = resolve_strategy(key)
    if engine:
        for group in catalog.get("groups") or []:
            for item in group.get("items") or []:
                if str(item.get("id", "")).lower() == engine:
                    return item
    return None


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
    except Exception as exc:  # noqa: BLE001
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
