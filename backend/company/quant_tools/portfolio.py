"""多標的組合：相關係數、權重配置、組合夏普與 market_portfolio。"""

from __future__ import annotations

import math
import re
from typing import Any

from .constants import _RANGE_MAP
from .data import _fail, _load_bars, normalize_symbol
from .indicators import _max_drawdown, _sharpe, _sortino

_PORTFOLIO_METHODS = {
    "equal_weight",
    "risk_parity",
    "vol_target",
    "kelly",
    "mvo",
    "max_div",
    "anti_corr",
    "regime",
    "frontier",
    "dynamic",
    "degradation",
}


def _corr_pair(left: list[float], right: list[float]) -> float:
    n = min(len(left), len(right))
    if n < 3:
        return 0.0
    ma = sum(left[:n]) / n
    mb = sum(right[:n]) / n
    cov = sum((left[i] - ma) * (right[i] - mb) for i in range(n)) / n
    sa = math.sqrt(sum((item - ma) ** 2 for item in left[:n]) / n)
    sb = math.sqrt(sum((item - mb) ** 2 for item in right[:n]) / n)
    if sa == 0 or sb == 0:
        return 0.0
    return cov / (sa * sb)


def _normalize_weights(raw: list[float]) -> list[float]:
    clipped = [max(0.0, float(item)) for item in raw]
    total = sum(clipped)
    if total <= 0:
        return [1.0 / len(raw)] * len(raw) if raw else []
    return [item / total for item in clipped]


def _portfolio_weights(mode: str, rets_by_leg: list[list[float]], vols: list[float]) -> list[float]:
    n = len(rets_by_leg)
    equal = [1.0 / n] * n
    if mode in {"equal_weight", "frontier"}:
        return equal
    if mode in {"risk_parity", "vol_target"}:
        inv = [1.0 / v for v in vols]
        return _normalize_weights(inv)
    means = [sum(row) / len(row) if row else 0.0 for row in rets_by_leg]
    vars_ = []
    for row, mean in zip(rets_by_leg, means):
        var = sum((item - mean) ** 2 for item in row) / len(row) if row else 1e-9
        vars_.append(max(var, 1e-12))
    if mode == "kelly":
        return _normalize_weights([means[i] / vars_[i] for i in range(n)])
    if mode == "mvo":
        best = equal
        best_score = -999.0
        steps = 5 if n <= 3 else 3
        if n == 2:
            for k in range(steps + 1):
                w0 = k / steps
                cand = [w0, 1.0 - w0]
                score = _portfolio_sharpe(cand, rets_by_leg)
                if score > best_score:
                    best_score = score
                    best = cand
            return best
        return _normalize_weights([max(m, 0.0) / v for m, v in zip(means, vars_)])
    if mode in {"max_div", "anti_corr"}:
        scores = []
        for i in range(n):
            corrs = [_corr_pair(rets_by_leg[i], rets_by_leg[j]) for j in range(n) if j != i]
            avg = sum(corrs) / len(corrs) if corrs else 0.0
            scores.append(max(0.01, 1.0 - avg))
        return _normalize_weights(scores)
    if mode == "regime":
        recent = [sum(row[-20:]) for row in rets_by_leg]
        if sum(recent) > 0:
            return _normalize_weights([max(item, 0.0) for item in recent])
        return equal
    if mode == "dynamic":
        window = [sum(row[-20:]) / max(len(row[-20:]), 1) for row in rets_by_leg]
        return _normalize_weights([max(item, 0.0) for item in window])
    if mode == "degradation":
        weights = list(equal)
        for i, row in enumerate(rets_by_leg):
            if sum(row[-20:]) < 0:
                weights[i] *= 0.5
        return _normalize_weights(weights)
    return equal


def _portfolio_sharpe(weights: list[float], rets_by_leg: list[list[float]]) -> float:
    if not rets_by_leg or not rets_by_leg[0]:
        return -999.0
    port = []
    for i in range(len(rets_by_leg[0])):
        port.append(sum(weights[j] * rets_by_leg[j][i] for j in range(len(weights))))
    mean = sum(port) / len(port)
    var = sum((item - mean) ** 2 for item in port) / len(port)
    std = math.sqrt(var) if var > 0 else 0.0
    if std == 0:
        return 0.0
    return (mean / std) * math.sqrt(252)


def market_portfolio(symbols: str, range: str = "1y", method: str = "equal_weight") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()]
        if len(parts) < 2:
            return _fail("請提供至少兩個標的，逗號分隔", tool="market_portfolio")
        mode = (method or "equal_weight").strip().lower()
        aliases = {
            "equal": "equal_weight",
            "ew": "equal_weight",
            "等權": "equal_weight",
            "rp": "risk_parity",
            "riskparity": "risk_parity",
            "vol": "vol_target",
            "volatility": "vol_target",
            "vt": "vol_target",
            "max_diversification": "max_div",
            "anti-correlation": "anti_corr",
            "regime-switch": "regime",
            "markowitz": "mvo",
        }
        mode = aliases.get(mode, mode)
        if mode not in _PORTFOLIO_METHODS:
            allowed = " / ".join(sorted(_PORTFOLIO_METHODS))
            return _fail(f"method 僅支援 {allowed}", tool="market_portfolio")
        legs: list[tuple[str, str, dict[str, float]]] = []
        errors: list[str] = []
        for raw in parts[:8]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                series = {str(b["t"]): float(b["c"]) for b in bars if b.get("c") is not None and b.get("t")}
                if series:
                    legs.append((code, source, series))
            except Exception as exc:
                errors.append(f"{raw}: {exc}")
        if len(legs) < 2:
            return _fail("有效標的不足兩個：" + "；".join(errors), tool="market_portfolio")
        common = set.intersection(*[set(item[2].keys()) for item in legs])
        dates = sorted(common)
        if len(dates) < 20:
            return _fail("共同交易日不足 20 根", tool="market_portfolio", dates=len(dates))
        rets_by_leg: list[list[float]] = []
        for _code, _src, series in legs:
            row: list[float] = []
            for i, day in enumerate(dates):
                if i == 0:
                    continue
                prev, cur = series[dates[i - 1]], series[day]
                row.append((cur / prev - 1.0) if prev else 0.0)
            rets_by_leg.append(row)
        vols = []
        for row in rets_by_leg:
            mean = sum(row) / len(row) if row else 0.0
            var = sum((item - mean) ** 2 for item in row) / len(row) if row else 0.0
            vols.append(math.sqrt(var) if var > 0 else 1e-9)
        weights = _portfolio_weights(mode, rets_by_leg, vols)
        frontier = None
        if mode == "frontier" and len(legs) >= 2:
            frontier = []
            # 參數名 range 會遮蔽內建 range()，此處用固定步長
            for k in (0, 1, 2, 3, 4):
                w0 = k / 4.0
                cand = [w0, 1.0 - w0] + [0.0] * (len(legs) - 2)
                if len(legs) > 2:
                    rest = (1.0 - w0) / (len(legs) - 1)
                    cand = [w0] + [rest] * (len(legs) - 1)
                frontier.append(
                    {
                        "weight_0": round(cand[0], 4),
                        "sharpe": round(_portfolio_sharpe(cand, rets_by_leg), 4),
                    }
                )
        target_vol = 0.12 / math.sqrt(252) if mode == "vol_target" else None
        equity = [1.0]
        port_rets: list[float] = []
        for i, _ret in enumerate(rets_by_leg[0]):
            avg = sum(weights[j] * rets_by_leg[j][i] for j, _leg in enumerate(legs))
            port_rets.append(avg)
        if target_vol is not None and port_rets:
            mean = sum(port_rets) / len(port_rets)
            var = sum((item - mean) ** 2 for item in port_rets) / len(port_rets)
            realized = math.sqrt(var) if var > 0 else target_vol
            scale = min(3.0, target_vol / realized) if realized else 1.0
            port_rets = [item * scale for item in port_rets]
            weights = [w * scale for w in weights]
        for avg in port_rets:
            equity.append(equity[-1] * (1.0 + avg))
        total_ret = equity[-1] / equity[0] - 1.0
        return {
            "ok": True,
            "method": mode,
            "weights": {code: round(weights[i], 4) for i, (code, _src, _series) in enumerate(legs)},
            "symbols": [item[0] for item in legs],
            "sources": list({item[1] for item in legs}),
            "bars": len(dates),
            "total_return": round(total_ret, 6),
            "max_drawdown": _max_drawdown(equity),
            "sharpe": _sharpe(equity),
            "sortino": _sortino(equity),
            "frontier": frontier,
            "errors": errors,
            "disclaimer": "組合不含再平衡成本，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_portfolio", query=symbols)
