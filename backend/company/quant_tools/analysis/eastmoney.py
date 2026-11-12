"""量化分析：東方財富資料端點（基本面／資金流／北向／龍虎榜／板塊／大盤流）。

對外函式：market_capital_flow／market_north_flow／market_dragon_tiger／
market_sectors／market_flow；_eastmoney_* 為本模組內部 helpers。
HTTP 一律經 data 套件模組屬性 _data._http_get_json，
維持 backend.company.quant_tools.data._http_get_json 的 monkeypatch 語意。
"""

from __future__ import annotations

from typing import Any

from .. import data as _data
from ..data import _eastmoney_secid, _fail, _num, normalize_symbol


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
