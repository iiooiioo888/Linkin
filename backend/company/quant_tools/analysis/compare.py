"""量化分析：多策略對比、基準比較與多標的區間收益排行。"""

from __future__ import annotations

import math
import re
from typing import Any

from ..backtest import _dispatch_strategy
from ..constants import _RANGE_MAP, STRATEGY_NAMES
from ..data import _fail, _load_bars, normalize_symbol
from ..indicators import _bars_series


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
