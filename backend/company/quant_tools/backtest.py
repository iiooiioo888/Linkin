"""回測派發與優化：策略 runner 派發、單策略回測、網格優化、Walk-Forward、熱力圖、訊號與排行。"""

from __future__ import annotations

import re
from typing import Any

from backend.company.quant_strategy_catalog import resolve_strategy

from .constants import _OPTIMIZE_GRIDS, _RANGE_MAP, STRATEGY_NAMES
from .data import _fail, _load_bars, normalize_symbol
from .indicators import _bars_series
from .strategies import (
    _run_bollinger,
    _run_breakout,
    _run_cci,
    _run_donchian,
    _run_ema_cross,
    _run_enhanced_volume,
    _run_kdj,
    _run_mean_reversion,
    _run_momentum,
    _run_rsi,
    _run_single_volume,
    _run_triple_ma,
    _run_turtle,
    _run_volume_price,
    _run_williams,
)
from .strategies_advanced import (
    _run_adx_trend,
    _run_atr_trail,
    _run_bollinger_squeeze,
    _run_composite,
    _run_dual_ma,
    _run_dual_thrust,
    _run_ema_volume,
    _run_envelope,
    _run_grid,
    _run_macd,
    _run_macd_rsi,
    _run_obv,
    _run_parabolic_sar,
    _run_pullback_ma,
    _run_supertrend,
    _run_vwap,
)


def _dispatch_strategy(
    name: str,
    closes: list[float],
    dates: list[str],
    short: int,
    long: int,
    period: int = 0,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    vols: list[float] | None = None,
    slippage_pct: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    trailing_stop_pct: float = 0.0,
    enable_t1: bool = False,
    enable_limit: bool = False,
    include_chart: bool = False,
) -> dict[str, Any]:
    risk = {
        "slippage_pct": slippage_pct,
        "stop_loss_pct": stop_loss_pct,
        "take_profit_pct": take_profit_pct,
        "trailing_stop_pct": trailing_stop_pct,
        "enable_t1": enable_t1,
        "enable_limit": enable_limit,
        "include_chart": include_chart,
    }
    hi = highs if highs is not None else closes
    lo = lows if lows is not None else closes
    vo = vols if vols is not None else [0.0] * len(closes)
    window = period if period and period > 0 else 0
    if name == "dual_ma":
        return _run_dual_ma(closes, dates, short, long, **risk)
    if name == "macd":
        return _run_macd(closes, dates, **risk)
    if name == "rsi":
        return _run_rsi(closes, dates, period=window or 14, **risk)
    if name == "bollinger":
        return _run_bollinger(closes, dates, period=window or 20, **risk)
    if name == "momentum":
        return _run_momentum(closes, dates, lookback=window or 20, **risk)
    if name == "mean_reversion":
        return _run_mean_reversion(closes, dates, period=window or 20, **risk)
    if name == "breakout":
        return _run_breakout(closes, dates, period=window or 20, **risk)
    if name == "kdj":
        return _run_kdj(closes, dates, period=window or 9, **risk)
    if name == "ema_cross":
        return _run_ema_cross(closes, dates, short, long, **risk)
    if name == "triple_ma":
        return _run_triple_ma(closes, dates, short, long, **risk)
    if name == "turtle":
        return _run_turtle(closes, dates, period=window or 20, **risk)
    if name == "donchian":
        return _run_donchian(closes, dates, period=window or 20, **risk)
    if name == "williams_r":
        return _run_williams(closes, dates, period=window or 14, **risk)
    if name == "cci":
        return _run_cci(closes, dates, hi, lo, period=window or 20, **risk)
    if name == "volume_price":
        return _run_volume_price(closes, dates, vo, period=window or 20, **risk)
    if name == "envelope":
        return _run_envelope(closes, dates, period=window or 20, **risk)
    if name == "obv":
        return _run_obv(closes, dates, vo, period=window or 20, **risk)
    if name == "bollinger_squeeze":
        return _run_bollinger_squeeze(closes, dates, period=window or 20, **risk)
    if name == "supertrend":
        return _run_supertrend(closes, dates, hi, lo, period=window or 10, **risk)
    if name == "adx_trend":
        return _run_adx_trend(closes, dates, hi, lo, period=window or 14, **risk)
    if name == "dual_thrust":
        return _run_dual_thrust(closes, dates, hi, lo, period=window or 4, **risk)
    if name == "grid":
        return _run_grid(closes, dates, period=window or 20, **risk)
    if name == "vwap":
        return _run_vwap(closes, dates, hi, lo, vo, period=window or 20, **risk)
    if name == "parabolic_sar":
        return _run_parabolic_sar(closes, dates, hi, lo, **risk)
    if name == "atr_trail":
        return _run_atr_trail(closes, dates, hi, lo, period=window or 20, **risk)
    if name == "ema_volume":
        return _run_ema_volume(closes, dates, vo, short=short, long=long, **risk)
    if name == "macd_rsi":
        return _run_macd_rsi(closes, dates, **risk)
    if name == "pullback_ma":
        return _run_pullback_ma(closes, dates, short=short, long=long, **risk)
    if name == "composite":
        return _run_composite(closes, dates, short, long, **risk)
    if name == "single_volume":
        return _run_single_volume(closes, dates, vo, short=short, long=long, period=window, **risk)
    if name == "enhanced_volume":
        return _run_enhanced_volume(closes, dates, vo, short=short, long=long, period=window, **risk)
    raise ValueError(f"不支援策略 {name}")


def market_backtest(
    symbol: str,
    strategy: str = "dual_ma",
    range: str = "1y",
    short: int = 5,
    long: int = 20,
    period: int = 0,
    slippage_pct: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    trailing_stop_pct: float = 0.0,
    enable_t1: bool = False,
    enable_limit: bool = False,
    include_chart: bool = False,
) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        requested = (strategy or "dual_ma").strip().lower()
        name = resolve_strategy(requested)
        if not name:
            return _fail(
                f"不支援策略 {strategy}。先呼叫 market_strategy_catalog；可回測引擎：{' / '.join(STRATEGY_NAMES)}",
                tool="market_backtest",
                query=symbol,
            )
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 30:
            return _fail("K 線不足 30 根，無法回測", tool="market_backtest", symbol=code, count=len(closes))
        short_n = max(2, min(int(short), 60))
        long_n = max(short_n + 1, min(int(long), 200))
        stats = _dispatch_strategy(
            name,
            closes,
            dates,
            short_n,
            long_n,
            period=int(period or 0),
            highs=highs,
            lows=lows,
            vols=vols,
            slippage_pct=float(slippage_pct or 0),
            stop_loss_pct=float(stop_loss_pct or 0),
            take_profit_pct=float(take_profit_pct or 0),
            trailing_stop_pct=float(trailing_stop_pct or 0),
            enable_t1=bool(enable_t1),
            enable_limit=bool(enable_limit),
            include_chart=bool(include_chart),
        )
        params: dict[str, Any]
        if name in {
            "dual_ma",
            "ema_cross",
            "triple_ma",
            "composite",
            "ema_volume",
            "pullback_ma",
            "single_volume",
            "enhanced_volume",
        }:
            params = {"short": short_n, "long": long_n}
        elif name in {"macd", "macd_rsi"}:
            params = {"fast": 12, "slow": 26, "signal": 9}
        else:
            params = {"strategy": name, "period": int(period or 0) or None}
        if slippage_pct or stop_loss_pct or take_profit_pct or trailing_stop_pct or enable_t1 or enable_limit:
            params.update(
                {
                    "slippage_pct": float(slippage_pct or 0),
                    "stop_loss_pct": float(stop_loss_pct or 0),
                    "take_profit_pct": float(take_profit_pct or 0),
                    "trailing_stop_pct": float(trailing_stop_pct or 0),
                    "enable_t1": bool(enable_t1),
                    "enable_limit": bool(enable_limit),
                }
            )
        return {
            "ok": True,
            "symbol": code,
            "query": symbol,
            "source": source,
            "strategy": name,
            "requested_strategy": requested,
            "params": params,
            "bars": len(closes),
            **stats,
            "disclaimer": "回測可含滑點／止損，不含稅費，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_backtest", query=symbol)


def _score_stats(stats: dict[str, Any]) -> float:
    sharpe = stats.get("sharpe")
    if sharpe is None:
        return -999.0
    return float(sharpe)


def market_optimize(symbol: str, strategy: str = "dual_ma", range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        name = resolve_strategy(strategy or "dual_ma")
        if not name:
            return _fail(f"不支援策略 {strategy}。先呼叫 market_strategy_catalog。", tool="market_optimize")
        grid = _OPTIMIZE_GRIDS.get(name)
        if not grid:
            allowed = " / ".join(_OPTIMIZE_GRIDS)
            return _fail(f"策略 {strategy} 無網格，可用 {allowed}", tool="market_optimize")
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法優化", tool="market_optimize", symbol=code)
        trials: list[dict[str, Any]] = []
        for params in grid:
            stats = _dispatch_strategy(
                name,
                closes,
                dates,
                int(params.get("short") or 5),
                int(params.get("long") or 20),
                period=int(params.get("period") or 0),
                highs=highs,
                lows=lows,
                vols=vols,
            )
            trials.append(
                {
                    "params": params,
                    "sharpe": stats.get("sharpe"),
                    "total_return": stats.get("total_return"),
                    "max_drawdown": stats.get("max_drawdown"),
                    "trades": stats.get("trades"),
                }
            )
        trials.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999)))
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": name,
            "method": "grid",
            "trials": trials[:12],
            "best": trials[0] if trials else None,
            "disclaimer": "網格搜尋不含前視偏差校正，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_optimize", query=symbol)


def market_walkforward(symbol: str, strategy: str = "dual_ma", range: str = "2y", windows: int = 4) -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        name = resolve_strategy(strategy or "dual_ma")
        if not name:
            return _fail(f"不支援策略 {strategy}", tool="market_walkforward")
        folds = max(2, min(int(windows or 4), 6))
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "2y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 80:
            return _fail("K 線不足 80 根，無法 Walk-Forward", tool="market_walkforward", count=len(closes))
        step = max(20, len(closes) // (folds + 1))
        rows: list[dict[str, Any]] = []
        for i, _fold in enumerate([None] * folds):
            train_end = min(len(closes) - 15, step * (i + 2))
            test_end = min(len(closes), train_end + step)
            if test_end - train_end < 10:
                continue
            train_c, test_c = closes[:train_end], closes[train_end:test_end]
            train_d, test_d = dates[:train_end], dates[train_end:test_end]
            train_h, test_h = highs[:train_end], highs[train_end:test_end]
            train_l, test_l = lows[:train_end], lows[train_end:test_end]
            train_v, test_v = vols[:train_end], vols[train_end:test_end]
            grid = _OPTIMIZE_GRIDS.get(name) or [{"short": 5, "long": 20}]
            best_params = grid[0]
            best_score = -999.0
            for params in grid:
                stats = _dispatch_strategy(
                    name,
                    train_c,
                    train_d,
                    int(params.get("short") or 5),
                    int(params.get("long") or 20),
                    period=int(params.get("period") or 0),
                    highs=train_h,
                    lows=train_l,
                    vols=train_v,
                )
                score = _score_stats(stats)
                if score > best_score:
                    best_score = score
                    best_params = params
            oos = _dispatch_strategy(
                name,
                test_c,
                test_d,
                int(best_params.get("short") or 5),
                int(best_params.get("long") or 20),
                period=int(best_params.get("period") or 0),
                highs=test_h,
                lows=test_l,
                vols=test_v,
            )
            rows.append(
                {
                    "fold": i + 1,
                    "train_end": train_d[-1] if train_d else None,
                    "test_end": test_d[-1] if test_d else None,
                    "params": best_params,
                    "in_sample_sharpe": round(best_score, 4) if best_score > -900 else None,
                    "oos_sharpe": oos.get("sharpe"),
                    "oos_return": oos.get("total_return"),
                    "oos_drawdown": oos.get("max_drawdown"),
                }
            )
        oos_sharpes = [row["oos_sharpe"] for row in rows if row.get("oos_sharpe") is not None]
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": name,
            "windows": rows,
            "mean_oos_sharpe": round(sum(oos_sharpes) / len(oos_sharpes), 4) if oos_sharpes else None,
            "disclaimer": "Walk-Forward 樣本外績效仍可能過擬合，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_walkforward", query=symbol)


def market_heatmap(symbol: str, range: str = "1y") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 40:
            return _fail("K 線不足，無法繪熱力圖", tool="market_heatmap")
        shorts = [3, 5, 8, 10]
        longs = [15, 20, 30, 40]
        cells: list[dict[str, Any]] = []
        for short in shorts:
            for long in longs:
                if short >= long:
                    continue
                stats = _dispatch_strategy(
                    "dual_ma", closes, dates, short, long, highs=highs, lows=lows, vols=vols
                )
                cells.append(
                    {
                        "short": short,
                        "long": long,
                        "sharpe": stats.get("sharpe"),
                        "total_return": stats.get("total_return"),
                    }
                )
        cells.sort(key=lambda row: (row.get("sharpe") is None, -(row.get("sharpe") or -999)))
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "strategy": "dual_ma",
            "cells": cells,
            "best": cells[0] if cells else None,
            "disclaimer": "參數敏感度熱力圖，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_heatmap", query=symbol)


def market_signals(symbol: str, range: str = "6mo") -> dict[str, Any]:
    try:
        code = normalize_symbol(symbol)
        bars, source = _load_bars(code, _RANGE_MAP.get(range, "6mo"), "1d")
        closes, dates, highs, lows, vols = _bars_series(bars)
        if len(closes) < 30:
            return _fail("K 線不足，無法產生訊號", tool="market_signals")
        items: list[dict[str, Any]] = []
        long_votes = 0
        for name, label in STRATEGY_NAMES.items():
            stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
            signal = stats.get("last_signal")
            if signal == "long":
                long_votes += 1
            items.append({"strategy": name, "name": label, "signal": signal, "sharpe": stats.get("sharpe")})
        consensus = "long" if long_votes >= max(3, len(STRATEGY_NAMES) // 3) else "cash"
        return {
            "ok": True,
            "symbol": code,
            "source": source,
            "as_of": dates[-1] if dates else None,
            "close": closes[-1],
            "consensus": consensus,
            "long_votes": long_votes,
            "strategies": items,
            "disclaimer": "訊號僅反映技術條件，非進出場指令。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_signals", query=symbol)


def market_leaderboard(symbols: str = "600519,000001,AAPL", range: str = "1y") -> dict[str, Any]:
    try:
        parts = [item.strip() for item in re.split(r"[,，\s]+", symbols or "") if item.strip()] or [
            "600519",
            "000001",
        ]
        scores: dict[str, list[float]] = {name: [] for name in STRATEGY_NAMES}
        used: list[str] = []
        errors: list[str] = []
        for raw in parts[:6]:
            try:
                code = normalize_symbol(raw)
                bars, source = _load_bars(code, _RANGE_MAP.get(range, "1y"), "1d")
                closes, dates, highs, lows, vols = _bars_series(bars)
                if len(closes) < 40:
                    errors.append(f"{code}: K 線不足")
                    continue
                used.append(code)
                for name in STRATEGY_NAMES:
                    stats = _dispatch_strategy(name, closes, dates, 5, 20, highs=highs, lows=lows, vols=vols)
                    if stats.get("sharpe") is not None:
                        scores[name].append(float(stats["sharpe"]))
            except Exception as exc:
                errors.append(f"{raw}: {exc}")
        ranking = []
        for name, values in scores.items():
            if not values:
                continue
            ranking.append(
                {
                    "strategy": name,
                    "name": STRATEGY_NAMES[name],
                    "mean_sharpe": round(sum(values) / len(values), 4),
                    "samples": len(values),
                }
            )
        ranking.sort(key=lambda row: -row["mean_sharpe"])
        return {
            "ok": True,
            "symbols": used,
            "ranking": ranking,
            "best": ranking[0] if ranking else None,
            "errors": errors,
            "disclaimer": "跨標的平均夏普，樣本外未必持續，禁止當作收益保證。",
        }
    except Exception as exc:
        return _fail(exc, tool="market_leaderboard", query=symbols)
