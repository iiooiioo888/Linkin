"""量化分析：標的搜尋、盤面篩選與基本面快照。"""

from __future__ import annotations

import re
from typing import Any

from .. import data as _data
from ..constants import SYMBOL_ALIASES
from ..data import _fail, normalize_symbol
from .eastmoney import _eastmoney_clist, _eastmoney_ulist


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
