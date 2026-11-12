"""績效打包與圖表取樣（自 backend.company.quant_tools.strategies 抽出）。

績效打包與圖表取樣（equity／hold／close 序列）。
"""

from __future__ import annotations

from typing import Any

from ..indicators import _calmar, _max_drawdown, _sharpe, _sortino


def _chart_points(dates: list[str], values: list[float], n: int = 96) -> list[dict[str, Any]]:
    if not values:
        return []
    length = min(len(values), len(dates) if dates else len(values))
    if length <= 0:
        return []
    if length <= n:
        idxs = list(range(length))
    else:
        step = (length - 1) / (n - 1)
        idxs = sorted({min(length - 1, round(i * step)) for i in range(n)})
        if idxs[-1] != length - 1:
            idxs.append(length - 1)
    points: list[dict[str, Any]] = []
    for i in idxs:
        stamp = dates[i] if i < len(dates) else str(i)
        points.append({"t": str(stamp), "v": round(float(values[i]), 6)})
    return points


def _pack_backtest(
    equity: list[float],
    trades: list[dict[str, Any]],
    signal: str,
    extra: dict[str, Any] | None = None,
    dates: list[str] | None = None,
    closes: list[float] | None = None,
    include_chart: bool = False,
) -> dict[str, Any]:
    wins = [t for t in trades if t.get("side") == "sell" and float(t.get("ret") or 0) > 0]
    sells = [t for t in trades if t.get("side") == "sell"]
    total_ret = equity[-1] / equity[0] - 1.0 if equity else 0.0
    payload = {
        "total_return": round(total_ret, 6),
        "max_drawdown": _max_drawdown(equity),
        "sharpe": _sharpe(equity),
        "sortino": _sortino(equity),
        "calmar": _calmar(equity),
        "trades": len(sells),
        "win_rate": round(len(wins) / len(sells), 4) if sells else None,
        "last_signal": signal,
        "recent_trades": trades[-8:],
        "equity_end": round(equity[-1], 6) if equity else 1.0,
    }
    if extra:
        payload.update(extra)
    if include_chart and equity:
        stamps = dates or [str(i) for i in range(len(equity))]
        hold: list[float] = []
        if closes and closes[0]:
            hold = [price / closes[0] for price in closes[: len(equity)]]
        payload["chart"] = {
            "equity": _chart_points(stamps, equity),
            "hold": _chart_points(stamps, hold) if hold else [],
            "close": _chart_points(stamps, closes[: len(equity)] if closes else []),
        }
    return payload
