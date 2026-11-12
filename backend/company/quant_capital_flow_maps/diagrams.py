"""資金流圖 Mermaid 建構：瀑布流向圖與循環狀態機（確定性）。"""

from __future__ import annotations

from typing import Any


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
