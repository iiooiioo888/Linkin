"""外匯匯率：Frankfurter 主源、fawazahmed0 備援。"""

from __future__ import annotations

import re
from typing import Any

from . import _compat
from .util import _fail


def fx_rate(base: str = "USD", quote: str = "CNY", date: str = "") -> dict[str, Any]:
    try:
        from_ccy = (base or "USD").strip().upper()
        to_ccy = (quote or "CNY").strip().upper()
        path = date.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}", (date or "").strip()) else "latest"
        try:
            data = _compat.http_get_json(
                f"https://api.frankfurter.app/{path}",
                {"from": from_ccy, "to": to_ccy},
            )
            rates = data.get("rates") if isinstance(data, dict) else None
            if isinstance(rates, dict) and to_ccy in rates:
                return {
                    "ok": True,
                    "source": "frankfurter",
                    "base": data.get("base", from_ccy),
                    "quote": to_ccy,
                    "rate": rates[to_ccy],
                    "as_of": data.get("date"),
                    "disclaimer": "歐洲央行參考匯率，每日更新一次，非即時。",
                }
        except Exception as frank_err:
            last = str(frank_err)[:200]
        else:
            last = "Frankfurter 無此幣對"
        data = _compat.http_get_json(
            f"https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/{from_ccy.lower()}.json"
        )
        bucket = data.get(from_ccy.lower()) if isinstance(data, dict) else None
        rate = bucket.get(to_ccy.lower()) if isinstance(bucket, dict) else None
        if rate is None:
            return _fail(last, tool="fx_rate", base=from_ccy, quote=to_ccy)
        return {
            "ok": True,
            "source": "currency_api",
            "base": from_ccy,
            "quote": to_ccy,
            "rate": rate,
            "as_of": data.get("date") if isinstance(data, dict) else None,
            "disclaimer": "社區匯率備援（fawazahmed0），每日更新，非即時。",
        }
    except Exception as exc:
        return _fail(exc, tool="fx_rate", base=base, quote=quote)
