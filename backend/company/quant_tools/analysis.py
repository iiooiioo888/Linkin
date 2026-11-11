"""量化分析：多標的對比、搜尋、基本面、資金流、板塊、盯盤與基準比較。"""

from __future__ import annotations

import math
import re
from typing import Any

from . import data as _data
from .backtest import _dispatch_strategy
from .constants import _RANGE_MAP, STRATEGY_NAMES, SYMBOL_ALIASES
from .data import (
    _eastmoney_secid,
    _fail,
    _load_bars,
    _num,
    normalize_symbol,
)
from .indicators import _bars_series, _sma
from .strategies_advanced import _run_dual_ma


def market_watch(symbol: str, drop_pct: float = 3.0) -> dict[str, Any]:
    """簡易盯盤：漲跌幅、均線位置、雙均線訊號。"""
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, "6mo", "1d")
        closes = [float(b["c"]) for b in bars if b.get("c") is not None]
        dates = [str(b["t"]) for b in bars if b.get("c") is not None]
        if len(closes) < 25:
            return _fail("K 線不足，無法盯盤", tool="market_watch", symbol=code)
        last, prev = closes[-1], closes[-2]
        pct = (last / prev - 1.0) * 100 if prev else 0.0
        ma20 = _sma(closes, 20)[-1]
        dual = _run_dual_ma(closes, dates, 5, 20)
        alerts: list[str] = []
        threshold = abs(float(drop_pct) or 3.0)
        if pct <= -threshold:
            alerts.append(f"單日下跌 {pct:.2f}%（門檻 {threshold:g}%）")
        if pct >= threshold:
            alerts.append(f"單日上漲 {pct:.2f}%（門檻 {threshold:g}%）")
        if ma20:
            if last < ma20:
                alerts.append("收盤跌破 MA20")
            else:
                alerts.append("收盤站上 MA20")
        if dual["last_signal"] == "long":
            alerts.append("雙均線偏多")
        elif dual["last_signal"] == "cash":
            alerts.append("雙均線偏空／空倉")
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "as_of": dates[-1],
            "close": last,
            "pct_change": round(pct, 4),
            "ma20": round(ma20, 4) if ma20 is not None else None,
            "last_signal": dual["last_signal"],
            "alerts": alerts,
            "disclaimer": "預警僅反映技術條件，非進出場指令。",
        }
    except Exception as ext:
        return _fail(ext, tool="market_watch", query=symbol)


def _eastmoney_ulist(symbol: str) -> dict[str, Any]:
    secid = _eastmoney_secid(symbol)
    if not secid:
        raise RuntimeError("非 A 股代碼")
    data = _data._http_get_json(
        "https://push2.eastmoney.com/api/qt/ulist.np/get",
        {
            "fltt": "2",
            "secids": secid,
            "fields": "f12,f14,f2,f3,f9,f23,f20,f21,f37,f115,f116,f117",
        },
    )
    diff = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("diff") or []
    if not diff:
        raise RuntimeError("東方財富基本面為空")
    return diff[0]


def _eastmoney_clist(fs: str, fields: str, fid: str, limit: int) -> list[dict[str, Any]]:
    data = _data._http_get_json(
        "https://push2.eastmoney.com/api/qt/clist/get",
        {
            "pn": "1",
            "pz": str(max(1, min(int(limit), 40))),
            "po": "1",
            "np": "1",
            "fltt": "2",
            "invt": "2",
            "fid": fid,
            "fs": fs,
            "fields": fields,
        },
    )
    payload = data.get("data") if isinstance(data, dict) else None
    rows = (payload or {}).get("diff") if isinstance(payload, dict) else None
    return rows if isinstance(rows, list) else []


def _eastmoney_datacenter(report_name: str, page_size: int = 15, extra: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {
        "reportName": report_name,
        "columns": "ALL",
        "pageNumber": "1",
        "pageSize": str(max(1, min(int(page_size), 40))),
        "source": "WEB",
        "client": "WEB",
        "sortColumns": "TRADE_DATE",
        "sortTypes": "-1",
    }
    if extra:
        params.update(extra)
    data = _data._http_get_json("https://datacenter-web.eastmoney.com/api/data/v1/get", params)
    result = data.get("result") if isinstance(data, dict) else None
    rows = (result or {}).get("data") if isinstance(result, dict) else None
    return rows if isinstance(rows, list) else []


def market_compare(symbol: str, range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法對比", tool="market_compare", symbol=code)
        ranking: list[dict[str, Any]] = []
        for name in STRATEGY_NAMES:
            stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
            ranking.append(
                {
                    "strategy": name,
                    "name": STRATEGY_NAMES[name],
                    "total_return": stats.get("total_return"),
                    "max_drawdown": stats.get("max_drawdown"),
                    "sharpe": stats.get("sharpe"),
                    "trades": stats.get("trades"),
                    "win_rate": stats.get("win_rate"),
                    "last_signal": stats.get("last_signal"),
                }
            )
        ranking.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999), -(row.get("total_return") or 0)))
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "bars": len(closes),
            "ranking": ranking,
            "best": ranking[0] if ranking else None,
            "disclaimer": "對比不含滑點／稅費，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_compare", query=symbol)


def market_search(keyword: str) -> dict[str, Any]:
    try:
        query = (keyword or "").strip()
        if not query:
            return _fail("keyword 不可為空", tool="market_search")
        hits: list[dict[str, Any]] = []
        alias = SYMBOL_ALIASES.get(query) or SYMBOL_ALIASES.get(query.replace(" ", ""))
        if alias:
            hits.append({"symbol": alias, "name": query, "source": "alias"})
        if re.fullmatch(r"\d{6}", query):
            hits.append({"symbol": normalize_symbol(query), "name": query, "source": "code"})
        try:
            data = _data._http_get_json(
                "https://query1.finance.yahoo.com/v1/finance/search",
                {"q": query, "quotesCount": 8, "newsCount": 0},
            )
            for item in data.get("quotes") or []:
                symbol = item.get("symbol")
                if not symbol:
                    continue
                hits.append(
                    {
                        "symbol": symbol,
                        "name": item.get("shortname") or item.get("longname") or symbol,
                        "type": item.get("quoteType"),
                        "source": "yahoo",
                    }
                )
        except Exception:
            pass
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for item in hits:
            key = str(item.get("symbol"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return {"ok": True, "query": query, "hits": unique[:10], "disclaimer": "公開數據僅供研究，非投資建議。"}
    except Exception as exc:
        return _fail(exc, tool="market_search", query=keyword)


def market_screener(sort: str = "pct", limit: int = 15) -> dict[str, Any]:
    try:
        fid = {"pct": "f3", "pe": "f9", "mv": "f20"}.get((sort or "pct").strip().lower(), "f3")
        rows = _eastmoney_clist(
            "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "f12,f14,f2,f3,f6,f9,f20,f23",
            fid,
            limit,
        )
        items = [
            {
                "code": row.get("f12"),
                "name": row.get("f14"),
                "close": row.get("f2"),
                "pct": row.get("f3"),
                "pe": row.get("f9"),
                "pb": row.get("f23"),
                "market_cap": row.get("f20"),
            }
            for row in rows
            if row.get("f12")
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "sort": sort,
            "items": items,
            "disclaimer": "A 股盤面快照，非投資建議。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_screener")


def market_fundamentals(symbol: str) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        row = _eastmoney_ulist(code)
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": "eastmoney",
            "code": row.get("f12"),
            "name": row.get("f14"),
            "close": row.get("f2"),
            "pct": row.get("f3"),
            "pe": row.get("f9") or row.get("f115"),
            "pb": row.get("f23"),
            "roe": row.get("f37"),
            "market_cap": row.get("f20") or row.get("f116"),
            "circ_cap": row.get("f21") or row.get("f117"),
            "disclaimer": "基本面快照，口徑可能與財報不一致。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_fundamentals", query=symbol)


def market_capital_flow(symbol: str, days: int = 15) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        secid = _eastmoney_secid(code)
        if not secid:
            return _fail("僅支援 A 股資金流", tool="market_capital_flow", symbol=code)
        limit = max(5, min(int(days or 15), 40))
        data = _data._http_get_json(
            "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
            {
                "lmt": str(limit),
                "klt": "101",
                "secid": secid,
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            },
        )
        klines = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("klines") or []
        flows: list[dict[str, Any]] = []
        for row in klines[-limit:]:
            parts = str(row).split(",")
            if len(parts) < 2:
                continue
            flows.append(
                {
                    "t": parts[0],
                    "main_net": _num(parts[1]),
                    "small_net": _num(parts[2]) if len(parts) > 2 else None,
                    "mid_net": _num(parts[3]) if len(parts) > 3 else None,
                    "large_net": _num(parts[4]) if len(parts) > 4 else None,
                    "super_net": _num(parts[5]) if len(parts) > 5 else None,
                }
            )
        return {
            "ok": True,
            "symbol": code,
            "source": "eastmoney",
            "flows": flows,
            "latest": flows[-1] if flows else None,
            "disclaimer": "主力淨額單位依東財口徑，僅供研究。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_capital_flow", query=symbol)


def market_north_flow(days: int = 15) -> dict[str, Any]:
    try:
        limit = max(5, min(int(days or 15), 40))
        rows = _eastmoney_datacenter("RPT_MUTUAL_DEAL_HISTORY", limit)
        daily: list[dict[str, Any]] = []
        for row in rows[:limit]:
            daily.append(
                {
                    "t": row.get("TRADE_DATE") or row.get("trade_date"),
                    "north_net": row.get("NORTH_NET_INFLOW") or row.get("NET_DEAL_AMT") or row.get("FUND_INFLOW"),
                    "buy": row.get("BUY_AMT") or row.get("BUY_VALUE"),
                    "sell": row.get("SELL_AMT") or row.get("SELL_VALUE"),
                }
            )
        return {
            "ok": True,
            "source": "eastmoney",
            "daily": daily,
            "latest": daily[0] if daily else None,
            "disclaimer": "滬深港通北向匯總，非即時成交。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_north_flow")


def market_dragon_tiger(limit: int = 15) -> dict[str, Any]:
    try:
        size = max(5, min(int(limit or 15), 30))
        rows = _eastmoney_datacenter(
            "RPT_DAILYBILLBOARD_DETAILSNEW",
            size,
            extra={"sortColumns": "TRADE_DATE,SECURITY_CODE", "sortTypes": "-1,-1"},
        )
        if not rows:
            rows = _eastmoney_datacenter("RPT_DAILYBILLBOARD_DETAILS", size)
        items = [
            {
                "code": row.get("SECURITY_CODE"),
                "name": row.get("SECURITY_NAME_ABBR") or row.get("SECURITY_NAME"),
                "t": row.get("TRADE_DATE"),
                "pct": row.get("CHANGE_RATE"),
                "net": row.get("BILLBOARD_NET_AMT") or row.get("NET_AMT"),
                "explain": row.get("EXPLAIN") or row.get("REASON"),
            }
            for row in rows[:size]
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "items": items,
            "disclaimer": "龍虎榜公開數據，非進出場指令。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_dragon_tiger")


def market_sectors(kind: str = "industry", limit: int = 15) -> dict[str, Any]:
    try:
        label = (kind or "industry").strip().lower()
        fs = "m:90+t:3" if label in {"concept", "概念"} else "m:90+t:2"
        rows = _eastmoney_clist(fs, "f12,f14,f2,f3,f62", "f3", limit)
        items = [
            {
                "code": row.get("f12"),
                "name": row.get("f14"),
                "close": row.get("f2"),
                "pct": row.get("f3"),
                "main_net": row.get("f62"),
            }
            for row in rows
            if row.get("f14")
        ]
        return {
            "ok": True,
            "source": "eastmoney",
            "kind": "concept" if fs.endswith("t:3") else "industry",
            "items": items,
            "disclaimer": "板塊漲跌快照，非投資建議。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_sectors")


def market_flow(days: int = 15) -> dict[str, Any]:
    try:
        limit = max(5, min(int(days or 15), 40))
        data = _data._http_get_json(
            "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get",
            {
                "lmt": str(limit),
                "klt": "101",
                "secid": "1.000001",
                "fields1": "f1,f2,f3,f7",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65",
            },
        )
        klines = ((data.get("data") or {}) if isinstance(data, dict) else {}).get("klines") or []
        flows: list[dict[str, Any]] = []
        for row in klines[-limit:]:
            parts = str(row).split(",")
            if len(parts) < 2:
                continue
            flows.append({"t": parts[0], "main_net": _num(parts[1]), "super_net": _num(parts[5]) if len(parts) > 5 else None})
        return {
            "ok": True,
            "source": "eastmoney",
            "benchmark": "000001.SS",
            "flows": flows,
            "latest": flows[-1] if flows else None,
            "disclaimer": "上證指數資金流向，口徑依東財。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_flow")


def market_benchmark(symbol: str, range: str = "1y", benchmark: str = "000300") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bench = normalize_symbol(benchmark or "000300")
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        bench_bars, bench_src = _load_bars(bench, _RANGE_MAP.get(range, "1y"), "1d")
        a = {str(b["t"]): float(b["c"]) for b in bars if b.get("c") is not None}
        b = {str(row["t"]): float(row["c"]) for row in bench_bars if row.get("c") is not None}
        days = sorted(set(a) & set(b))
        if len(days) < 20:
            return _fail("與基準共同交易日不足", tool="market_benchmark")
        eq_a = [1.0]
        eq_b = [1.0]
        excess: list[float] = []
        rets_a: list[float] = []
        rets_b: list[float] = []
        prev_day: str | None = None
        for day in days:
            if prev_day is None:
                prev_day = day
                continue
            ra = a[day] / a[prev_day] - 1.0
            rb = b[day] / b[prev_day] - 1.0
            eq_a.append(eq_a[-1] * (1.0 + ra))
            eq_b.append(eq_b[-1] * (1.0 + rb))
            excess.append(ra - rb)
            rets_a.append(ra)
            rets_b.append(rb)
            prev_day = day
        n_obs = len(rets_a) or 1
        mean_e = sum(excess) / n_obs
        var_b = sum(item * item for item in rets_b) / n_obs
        mean_b = sum(rets_b) / n_obs
        mean_a = sum(rets_a) / n_obs
        cov = sum((ra - mean_a) * (rb - mean_b) for ra, rb in zip(rets_a, rets_b)) / n_obs
        beta = cov / var_b if var_b else None
        alpha = (mean_a - (beta or 0) * mean_b) * 252 if beta is not None else None
        te = math.sqrt(sum((item - mean_e) ** 2 for item in excess) / len(excess)) if excess else 0.0
        return {
            "ok": True,
            "symbol": code,
            "benchmark": bench,
            "sources": [source, bench_src],
            "bars": len(days),
            "total_return": round(eq_a[-1] - 1.0, 6),
            "benchmark_return": round(eq_b[-1] - 1.0, 6),
            "excess_return": round(eq_a[-1] / eq_b[-1] - 1.0, 6) if eq_b[-1] else None,
            "alpha": round(alpha, 6) if alpha is not None else None,
            "beta": round(beta, 4) if beta is not None else None,
            "tracking_error": round(te * math.sqrt(252), 6),
            "disclaimer": "基準對比不含股息再投資差異，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_benchmark", query=symbol)


def market_returns(symbols: str, range: str = "1y") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()]
        if len(parts) < 2:
            return _fail("請提供至少兩個標的", tool="market_returns")
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        for raw in parts[:8]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                closes = [float(b["c"]) for b in bars if b.get("c") is not None]
                if len(closes) < 5:
                    errors.append(f"{code}: K 線不足")
                    continue
                ret = closes[-1] / closes[0] - 1.0
                rows.append(
                    {
                        "symbol": code,
                        "source": source,
                        "start": closes[0],
                        "end": closes[-1],
                        "total_return": round(ret, 6),
                        "bars": len(closes),
                    }
                )
            except Exception as exc:
                errors.append(f"{raw}: {exc}")
        rows.sort(key=lambda item: -(item.get("total_return") or 0))
        return {
            "ok": True,
            "ranking": rows,
            "best": rows[0] if rows else None,
            "errors": errors,
            "disclaimer": "區間收益不含股息，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_returns", query=symbols)
