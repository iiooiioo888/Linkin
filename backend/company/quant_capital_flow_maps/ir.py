"""strategy_capital_flow IR 組裝：瀑布／狀態機／時間軸三種視覺化輸出。"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_maps import _find_item, _listing

from .diagrams import _state_machine_mermaid, _waterfall_mermaid
from .profiles import _merge_profile
from .timeline import _demo_timeline, _fmt_wan, _timeline_from_trades


def strategy_capital_flow(
    strategy_id: str,
    symbol: str = "600519",
    initial_capital: float = 1_000_000.0,
    *,
    stop_loss_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    position_pct: float | None = None,
    enable_t1: bool = False,
) -> dict[str, Any]:
    """產生策略專屬三種資金流視覺化。"""
    catalog = _listing()
    item = _find_item(catalog, strategy_id)
    if item is None:
        return {
            "ok": False,
            "error": f"未知策略 {strategy_id}。先呼叫 market_strategy_catalog。",
            "tool": "strategy_capital_flow",
        }

    category = str(item.get("category") or "ma")
    overrides: dict[str, Any] = {}
    if stop_loss_pct is not None:
        overrides["stop_loss_pct"] = float(stop_loss_pct)
    if trailing_stop_pct is not None:
        overrides["trailing_stop_pct"] = float(trailing_stop_pct)
    if position_pct is not None:
        overrides["position_pct"] = float(position_pct)
    profile = _merge_profile(category, overrides)

    code = (symbol or "600519").strip() or "600519"
    strategy_name = str(item.get("name") or item.get("id") or strategy_id)
    engine = str(item.get("engine") or item.get("id") or "")

    backtest: dict[str, Any] | None = None
    timeline: list[dict[str, str]]
    if item.get("status") == "wired" and engine:
        from backend.company.quant_tools import market_backtest

        risk_kw: dict[str, Any] = {"include_chart": False}
        if stop_loss_pct is not None:
            risk_kw["stop_loss_pct"] = float(stop_loss_pct)
        if trailing_stop_pct is not None:
            risk_kw["trailing_stop_pct"] = float(trailing_stop_pct)
        if enable_t1:
            risk_kw["enable_t1"] = True
        try:
            backtest = market_backtest(code, strategy=engine, **risk_kw)
        except Exception as exc:
            backtest = {"ok": False, "error": str(exc)[:300]}

    if backtest and backtest.get("ok"):
        trades = list(backtest.get("recent_trades") or [])
        # recent_trades 只有末 8 筆，補跑含完整 trades 需改引擎；先用可得資料
        all_trades = trades
        equity_end = backtest.get("equity_end")
        if all_trades:
            timeline = _timeline_from_trades(
                trades=all_trades,
                initial_capital=float(initial_capital),
                symbol=code,
                profile=profile,
                equity_end=float(equity_end) if equity_end is not None else None,
            )
        else:
            timeline = _demo_timeline(
                initial_capital=float(initial_capital),
                symbol=code,
                strategy_name=strategy_name,
                profile=profile,
            )
    else:
        timeline = _demo_timeline(
            initial_capital=float(initial_capital),
            symbol=code,
            strategy_name=strategy_name,
            profile=profile,
        )

    scene_hints = [
        {"scene": "向投資人說明資金有沒有亂用", "chart": "waterfall", "title": "瀑布流向圖"},
        {"scene": "向交易員說明下單後錢去哪", "chart": "state_machine", "title": "循環狀態機"},
        {"scene": "向風控主管說明每日損益細節", "chart": "timeline", "title": "時間軸數值表"},
    ]
    if profile.get("rebalance"):
        scene_hints.append(
            {
                "scene": "策略含加碼/減碼或再平衡",
                "chart": "state_machine+timeline",
                "title": "狀態機 + 時間軸合併",
            }
        )

    return {
        "ok": True,
        "strategy": item["id"],
        "engine": engine or None,
        "name": strategy_name,
        "symbol": code,
        "category": category,
        "initial_capital": float(initial_capital),
        "initial_capital_fmt": _fmt_wan(float(initial_capital)),
        "profile": profile,
        "waterfall_mermaid": _waterfall_mermaid(
            strategy_name=strategy_name, symbol=code, profile=profile
        ),
        "state_machine_mermaid": _state_machine_mermaid(strategy_name=strategy_name, profile=profile),
        "timeline": timeline,
        "scene_hints": scene_hints,
        "backtest_summary": (
            {
                "total_return": backtest.get("total_return"),
                "max_drawdown": backtest.get("max_drawdown"),
                "trades": backtest.get("trades"),
                "last_signal": backtest.get("last_signal"),
            }
            if backtest and backtest.get("ok")
            else None
        ),
        "disclaimer": "時間軸依回測末段成交或示範路徑模擬；非實盤交割紀錄。保證金比例為簡化示意。",
        "hint": "實驗室策略庫可切換三種資金流視圖；角色可 GET /lab/quant/capital-flow。",
    }
