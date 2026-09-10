"""量化策略資金流視覺化 — 瀑布／狀態機／時間軸（確定性，不經 LLM）。

三種維度：
1. 瀑布流向圖（桑基風格 Mermaid）— 資金當下分布
2. 循環狀態機 — 一筆資金從進場到出場的生命週期
3. 時間軸數值表 — 依回測成交序列模擬現金／持倉／權益變化
"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_maps import _find_item, _listing

# 依策略分類的預設資金流參數（可被 query 覆寫）
_CATEGORY_PROFILES: dict[str, dict[str, Any]] = {
    "ma": {
        "cash_buffer_pct": 20,
        "margin_pct": 70,
        "reserve_pct": 10,
        "position_pct": 80,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": True,
        "long_pct": 70,
        "short_pct": 0,
    },
    "momentum": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "mean_reversion": {
        "cash_buffer_pct": 30,
        "margin_pct": 55,
        "reserve_pct": 15,
        "position_pct": 70,
        "stop_loss_pct": 4.0,
        "daily_loss_limit_pct": 1.5,
        "short_enabled": False,
        "intraday": False,
        "rebalance": True,
        "long_pct": 55,
        "short_pct": 0,
    },
    "volatility": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 0.0,
        "trailing_stop_pct": 8.0,
        "daily_loss_limit_pct": 2.5,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "trend": {
        "cash_buffer_pct": 20,
        "margin_pct": 65,
        "reserve_pct": 15,
        "position_pct": 80,
        "stop_loss_pct": 8.0,
        "daily_loss_limit_pct": 3.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 65,
        "short_pct": 0,
    },
    "breakout": {
        "cash_buffer_pct": 25,
        "margin_pct": 60,
        "reserve_pct": 15,
        "position_pct": 75,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": True,
        "rebalance": False,
        "long_pct": 60,
        "short_pct": 0,
    },
    "composite": {
        "cash_buffer_pct": 25,
        "margin_pct": 55,
        "reserve_pct": 20,
        "position_pct": 75,
        "stop_loss_pct": 6.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": True,
        "intraday": False,
        "rebalance": True,
        "long_pct": 40,
        "short_pct": 20,
    },
    "pattern": {
        "cash_buffer_pct": 30,
        "margin_pct": 55,
        "reserve_pct": 15,
        "position_pct": 70,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 55,
        "short_pct": 0,
    },
    "ml": {
        "cash_buffer_pct": 40,
        "margin_pct": 40,
        "reserve_pct": 20,
        "position_pct": 60,
        "stop_loss_pct": 5.0,
        "daily_loss_limit_pct": 2.0,
        "short_enabled": False,
        "intraday": False,
        "rebalance": False,
        "long_pct": 40,
        "short_pct": 0,
    },
}

_DEFAULT_PROFILE: dict[str, Any] = {
    "cash_buffer_pct": 25,
    "margin_pct": 60,
    "reserve_pct": 15,
    "position_pct": 75,
    "stop_loss_pct": 6.0,
    "trailing_stop_pct": 0.0,
    "daily_loss_limit_pct": 2.0,
    "short_enabled": False,
    "intraday": False,
    "rebalance": False,
    "long_pct": 40,
    "short_pct": 20,
}


def _fmt_wan(value: float) -> str:
    """格式化成萬元級距（整數萬或含小數）。"""
    wan = value / 10_000.0
    if abs(wan - round(wan)) < 0.05:
        return f"{round(wan):,.0f} 萬"
    return f"{wan:,.1f} 萬"


def _merge_profile(category: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base = dict(_DEFAULT_PROFILE)
    base.update(_CATEGORY_PROFILES.get(category, {}))
    if overrides:
        for key, val in overrides.items():
            if val is not None and val != "":
                base[key] = val
    # 保證比例加總合理
    total_alloc = base["cash_buffer_pct"] + base["margin_pct"] + base["reserve_pct"]
    if total_alloc != 100:
        scale = 100.0 / total_alloc if total_alloc else 1.0
        base["cash_buffer_pct"] = round(base["cash_buffer_pct"] * scale)
        base["margin_pct"] = round(base["margin_pct"] * scale)
        base["reserve_pct"] = 100 - base["cash_buffer_pct"] - base["margin_pct"]
    if not base.get("short_enabled"):
        base["short_pct"] = 0
        base["long_pct"] = base.get("margin_pct", 60)
    return base


def _waterfall_mermaid(
    *,
    strategy_name: str,
    symbol: str,
    profile: dict[str, Any],
) -> str:
    cash = profile["cash_buffer_pct"]
    margin = profile["margin_pct"]
    reserve = profile["reserve_pct"]
    long_pct = profile.get("long_pct", margin)
    short_pct = profile.get("short_pct", 0)
    stop = profile.get("stop_loss_pct") or profile.get("trailing_stop_pct") or 6.0
    stop_label = (
        f"移動止損 -{profile['trailing_stop_pct']:.0f}%"
        if profile.get("trailing_stop_pct")
        else f"停損 -{stop:.0f}%"
    )
    short_block = ""
    if profile.get("short_enabled") and short_pct > 0:
        short_block = f"""
    Margin --> Short[空頭持倉<br>市值 {short_pct}%]
    Short --> |價格下跌| FloatingPL[浮動未實現損益]"""
    else:
        short_block = ""

    return f"""graph TD
    Total["總權益資金 100%<br>{strategy_name} · {symbol}"] --> Cash["現金緩衝 {cash}%"]
    Total --> Margin["保證金占用 {margin}%"]
    Total --> Reserve["停損/避險準備金 {reserve}%"]

    Margin --> Long["多頭持倉<br>市值 {long_pct}%"]{short_block}

    Long --> |價格波動| FloatingPL[浮動未實現損益]
    FloatingPL --> |平倉獲利| RealizedGain[已實現盈餘 → 回流現金]
    FloatingPL --> |平倉虧損| RealizedLoss[已實現虧損 → 扣減總權益]

    Reserve --> |極端波動觸發| CutLoss["強制減倉 {stop_label}<br>釋放保證金"]
    CutLoss --> Cash

    style Total fill:#2C3E50,color:#fff
    style Cash fill:#27AE60,color:#fff
    style Margin fill:#F39C12,color:#fff
    style Reserve fill:#E74C3C,color:#fff
    style FloatingPL fill:#8E44AD,color:#fff"""


def _state_machine_mermaid(*, strategy_name: str, profile: dict[str, Any]) -> str:
    stop = profile.get("stop_loss_pct") or profile.get("trailing_stop_pct") or 6.0
    stop_line = (
        f"觸及移動止損 -{profile['trailing_stop_pct']:.0f}%"
        if profile.get("trailing_stop_pct")
        else f"觸及停損線 -{stop:.0f}%"
    )
    rebalance = ""
    if profile.get("rebalance"):
        rebalance = """
    現金帳戶 --> 再平衡調整 : 每日收盤計算權重
    再平衡調整 --> 現金帳戶 : 超配部位賣出 / 低配部位買入"""
    intraday_note = "盤中價格波動<br>（浮動損益即時增減）" if profile.get("intraday") else "持倉期間價格波動<br>（浮動損益尚未入帳）"
    t1_note = "（T+1 次日可賣）" if not profile.get("intraday") else ""

    return f"""stateDiagram-v2
    [*] --> 現金帳戶

    現金帳戶 --> 下單預凍結 : 訊號觸發買進<br>{strategy_name}
    下單預凍結 --> 持倉市值 : 成交（資金換成標的）
    持倉市值 --> 持倉市值 : {intraday_note}

    持倉市值 --> 現金帳戶 : 平倉獲利（資金回流 + 利潤）
    持倉市值 --> 現金帳戶 : 平倉虧損（資金回流 - 虧損）{t1_note}

    持倉市值 --> 強制平倉 : {stop_line}
    強制平倉 --> 現金帳戶 : 殘餘資金退回

    下單預凍結 --> 現金帳戶 : 委託取消（資金解凍）{rebalance}"""


def _timeline_from_trades(
    *,
    trades: list[dict[str, Any]],
    initial_capital: float,
    symbol: str,
    profile: dict[str, Any],
    equity_end: float | None = None,
) -> list[dict[str, str]]:
    """依回測成交序列模擬資金時間軸。"""
    cap = float(initial_capital)
    pos_pct = float(profile.get("position_pct", 75)) / 100.0
    cash = cap
    position = 0.0
    margin = 0.0
    rows: list[dict[str, str]] = [
        {
            "time": "T0 開盤前",
            "event": "初始資金",
            "cash": _fmt_wan(cash),
            "position": _fmt_wan(position),
            "margin": _fmt_wan(margin),
            "equity": _fmt_wan(cap),
            "note": "全部是現金",
        }
    ]
    idx = 1
    pending_buy: dict[str, Any] | None = None

    for trade in trades:
        side = str(trade.get("side") or "")
        t = str(trade.get("t") or f"T{idx}")
        price = float(trade.get("price") or 0)

        if side == "buy":
            deploy = cash * pos_pct
            cash -= deploy
            position = deploy
            margin = deploy * 0.5  # A 股現股簡化：占用約 50% 名義
            pending_buy = trade
            rows.append(
                {
                    "time": f"T{idx} {t}",
                    "event": f"買進 {symbol} @{price:.2f}",
                    "cash": _fmt_wan(cash),
                    "position": _fmt_wan(position),
                    "margin": _fmt_wan(margin),
                    "equity": _fmt_wan(cash + position),
                    "note": "現金流出 → 轉為持倉",
                }
            )
            idx += 1
        elif side == "sell" and pending_buy:
            ret = float(trade.get("ret") or 0)
            pnl = position * ret
            cash += position + pnl
            reason = str(trade.get("reason") or "signal")
            reason_zh = {
                "signal": "訊號平倉",
                "stop": "停損平倉",
                "take_profit": "止盈平倉",
                "trailing": "移動止損",
            }.get(reason, reason)
            event = f"賣出 {symbol}（{reason_zh}）"
            note = f"{'獲利' if pnl >= 0 else '虧損'} {_fmt_wan(abs(pnl))} 回流現金"
            position = 0.0
            margin = 0.0
            pending_buy = None
            rows.append(
                {
                    "time": f"T{idx} {t}",
                    "event": event,
                    "cash": _fmt_wan(cash),
                    "position": _fmt_wan(position),
                    "margin": _fmt_wan(margin),
                    "equity": _fmt_wan(cash),
                    "note": note,
                }
            )
            idx += 1

    # 若仍持倉，插入一筆浮動損益列
    if position > 0 and equity_end is not None:
        equity_now = cap * float(equity_end)
        float_pnl = equity_now - (cash + position)
        rows.append(
            {
                "time": f"T{idx} 持倉中",
                "event": f"{symbol} 未平倉",
                "cash": _fmt_wan(cash),
                "position": _fmt_wan(position + float_pnl),
                "margin": _fmt_wan(margin),
                "equity": _fmt_wan(equity_now),
                "note": f"浮動{'獲利' if float_pnl >= 0 else '虧損'} {_fmt_wan(abs(float_pnl))}（尚未入帳）",
            }
        )
        idx += 1

    # 風控檢查列
    final_equity = cap * float(equity_end) if equity_end is not None else cash + position
    daily_ret = (final_equity / cap - 1.0) * 100.0 if cap else 0.0
    limit = float(profile.get("daily_loss_limit_pct", 2.0))
    triggered = daily_ret <= -limit
    rows.append(
        {
            "time": f"T{idx} 風控檢查",
            "event": "日虧損檢查",
            "cash": _fmt_wan(cash),
            "position": _fmt_wan(position),
            "margin": _fmt_wan(margin),
            "equity": _fmt_wan(final_equity),
            "note": (
                f"日虧損 {daily_ret:+.1f}% 觸及 -{limit:.0f}% 停損線，明日減倉"
                if triggered
                else f"日虧損 {daily_ret:+.1f}%（>-{limit:.0f}% 停損線），未觸發減倉"
            ),
        }
    )
    return rows


def _demo_timeline(
    *,
    initial_capital: float,
    symbol: str,
    strategy_name: str,
    profile: dict[str, Any],
) -> list[dict[str, str]]:
    """無回測成交時的示範時間軸（對齊使用者提供的台股多空範例結構）。"""
    cap = float(initial_capital)
    long_deploy = cap * 0.5
    short_margin = cap * 0.2
    rows = [
        {
            "time": "T0 開盤前",
            "event": "初始資金",
            "cash": _fmt_wan(cap),
            "position": "0",
            "margin": "0",
            "equity": _fmt_wan(cap),
            "note": "全部是現金",
        },
        {
            "time": "T1 09:00",
            "event": f"買進 {symbol}（策略 {strategy_name}）",
            "cash": _fmt_wan(cap - long_deploy),
            "position": _fmt_wan(long_deploy),
            "margin": _fmt_wan(long_deploy * 0.5),
            "equity": _fmt_wan(cap),
            "note": "現金流出 → 轉為持倉",
        },
        {
            "time": "T2 10:30",
            "event": f"{symbol} 上漲 +2%",
            "cash": _fmt_wan(cap - long_deploy),
            "position": _fmt_wan(long_deploy * 1.02),
            "margin": _fmt_wan(long_deploy * 0.5),
            "equity": _fmt_wan(cap + long_deploy * 0.02),
            "note": f"浮動獲利 {_fmt_wan(long_deploy * 0.02)}（尚未入帳）",
        },
    ]
    if profile.get("short_enabled"):
        rows.append(
            {
                "time": "T3 11:00",
                "event": "放空對沖腿（保證金）",
                "cash": _fmt_wan(cap - long_deploy - short_margin),
                "position": _fmt_wan(long_deploy * 1.02) + " (多)",
                "margin": _fmt_wan(long_deploy * 0.5 + short_margin),
                "equity": _fmt_wan(cap + long_deploy * 0.02),
                "note": f"現金再流出 {_fmt_wan(short_margin)} 當保證金",
            }
        )
    final = cap * 1.005
    rows.append(
        {
            "time": "T5 收盤後",
            "event": "平倉結算",
            "cash": _fmt_wan(final),
            "position": "0",
            "margin": "0",
            "equity": _fmt_wan(final),
            "note": f"策略回合結束，淨{'獲利' if final >= cap else '虧損'} {_fmt_wan(abs(final - cap))}",
        }
    )
    daily_ret = (final / cap - 1.0) * 100.0
    limit = float(profile.get("daily_loss_limit_pct", 2.0))
    rows.append(
        {
            "time": "T6 風控檢查",
            "event": "日虧損檢查",
            "cash": _fmt_wan(final),
            "position": "0",
            "margin": "0",
            "equity": _fmt_wan(final),
            "note": f"日虧損 {daily_ret:+.1f}%（>-{limit:.0f}% 停損線），未觸發減倉",
        }
    )
    return rows


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
