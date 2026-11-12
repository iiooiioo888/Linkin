"""加密貨幣報價：CoinPaprika 主源、CoinGecko／Binance 備援。"""

from __future__ import annotations

from typing import Any

from ..constants import COINGECKO_IDS, CRYPTO_IDS
from . import _compat
from .util import _fail, _num


def crypto_quote(symbol: str = "BTC") -> dict[str, Any]:
    try:
        query = (symbol or "BTC").strip()
        coin_id = CRYPTO_IDS.get(query.upper())
        if not coin_id:
            if "-" in query:
                coin_id = query.lower()
            else:
                found = _compat.http_get_json(
                    "https://api.coinpaprika.com/v1/search",
                    {"q": query, "c": "currencies", "limit": 1},
                )
                currencies = found.get("currencies") if isinstance(found, dict) else None
                if currencies:
                    coin_id = currencies[0].get("id")
        if not coin_id:
            return _fail(f"找不到加密貨幣 {query}", tool="crypto_quote")
        data = _compat.http_get_json(f"https://api.coinpaprika.com/v1/tickers/{coin_id}")
        quotes = (data.get("quotes") or {}).get("USD") if isinstance(data, dict) else None
        if isinstance(quotes, dict):
            return {
                "ok": True,
                "source": "coinpaprika",
                "id": data.get("id"),
                "symbol": data.get("symbol"),
                "name": data.get("name"),
                "price_usd": quotes.get("price"),
                "pct_change_24h": quotes.get("percent_change_24h"),
                "volume_24h_usd": quotes.get("volume_24h"),
                "market_cap_usd": quotes.get("market_cap"),
                "as_of": data.get("last_updated"),
                "disclaimer": "公開數據僅供研究，非投資建議。",
            }
        gecko_id = COINGECKO_IDS.get(query.upper())
        if gecko_id:
            return _crypto_from_coingecko(query, gecko_id)
        return _crypto_from_binance(query)
    except Exception as exc:
        gecko_id = COINGECKO_IDS.get((symbol or "BTC").strip().upper())
        if gecko_id:
            try:
                return _crypto_from_coingecko(symbol, gecko_id)
            except Exception:
                pass
        try:
            return _crypto_from_binance(symbol)
        except Exception:
            pass
        return _fail(exc, tool="crypto_quote", query=symbol)

def _crypto_from_binance(query: str) -> dict[str, Any]:
    pair = f"{(query or 'BTC').strip().upper()}USDT"
    data = _compat.http_get_json("https://api.binance.com/api/v3/ticker/24hr", {"symbol": pair})
    price = _num((data or {}).get("lastPrice")) if isinstance(data, dict) else None
    if price is None:
        raise RuntimeError("Binance 報價為空")
    return {
        "ok": True,
        "source": "binance",
        "id": pair,
        "symbol": pair.replace("USDT", ""),
        "name": pair,
        "price_usd": price,
        "pct_change_24h": _num(data.get("priceChangePercent")),
        "volume_24h_usd": _num(data.get("quoteVolume")),
        "disclaimer": "交易所公開 ticker，僅現貨 USDT 對。",
    }

def _crypto_from_coingecko(query: str, gecko_id: str) -> dict[str, Any]:
    data = _compat.http_get_json(
        "https://api.coingecko.com/api/v3/simple/price",
        {
            "ids": gecko_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
            "include_market_cap": "true",
        },
    )
    row = data.get(gecko_id) if isinstance(data, dict) else None
    if not isinstance(row, dict) or row.get("usd") is None:
        raise RuntimeError("CoinGecko 報價為空")
    return {
        "ok": True,
        "source": "coingecko",
        "id": gecko_id,
        "symbol": (query or "").upper(),
        "name": gecko_id,
        "price_usd": row.get("usd"),
        "pct_change_24h": row.get("usd_24h_change"),
        "volume_24h_usd": row.get("usd_24h_vol"),
        "market_cap_usd": row.get("usd_market_cap"),
        "disclaimer": "公開數據僅供研究，非投資建議。",
    }
