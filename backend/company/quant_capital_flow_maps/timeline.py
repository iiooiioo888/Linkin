"""資金流時間軸數值表：依回測成交或示範路徑模擬現金／持倉／權益。"""

from __future__ import annotations

from typing import Any


def _fmt_wan(value: float) -> str:
    """格式化成萬元級距（整數萬或含小數）。"""
    wan = value / 10_000.0
    if abs(wan - round(wan)) < 0.05:
        return f"{round(wan):,.0f} 萬"
    return f"{wan:,.1f} 萬"

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
