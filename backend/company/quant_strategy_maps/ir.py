"""策略圖 IR 共用建構：IR／節點／邊 helper、策略庫列舉與分類資料表。"""

from __future__ import annotations

from typing import Any

from backend.company.quant_strategy_catalog import market_strategy_catalog, resolve_strategy

ARCHIFY_SOURCE = "https://github.com/tt-a1i/archify"
CATALOG_SOURCE = "https://github.com/iiooiioo888/stock-quant"

_CATEGORY_FLOW: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ma": (
        ("bars", "K 線", "data"),
        ("fast", "短均線", "service"),
        ("slow", "長均線", "service"),
        ("cross", "金叉／死叉", "service"),
        ("pos", "持倉", "api"),
        ("risk", "止損／T+1", "api"),
        ("stats", "績效", "frontend"),
    ),
    "momentum": (
        ("bars", "K 線", "data"),
        ("osc", "震盪指標", "service"),
        ("zone", "超買／超賣", "service"),
        ("signal", "進出場訊號", "api"),
        ("risk", "風控", "api"),
        ("stats", "績效", "frontend"),
    ),
    "mean_reversion": (
        ("bars", "K 線", "data"),
        ("band", "通道／Z-score", "service"),
        ("dev", "偏離判定", "service"),
        ("entry", "回歸入場", "api"),
        ("exit", "回歸出場", "api"),
        ("stats", "績效", "frontend"),
    ),
    "volatility": (
        ("bars", "高低收", "data"),
        ("atr", "ATR／波動", "service"),
        ("regime", "擴張或收縮", "service"),
        ("trail", "追蹤止損", "api"),
        ("stats", "績效", "frontend"),
    ),
    "trend": (
        ("bars", "K 線", "data"),
        ("filter", "趨勢濾網", "service"),
        ("break", "突破入場", "api"),
        ("trail", "移動止損", "api"),
        ("stats", "績效", "frontend"),
    ),
    "pattern": (
        ("bars", "K 線", "data"),
        ("shape", "形態識別", "service"),
        ("confirm", "量價確認", "service"),
        ("entry", "形態入場", "api"),
        ("invalidate", "失效出場", "api"),
        ("stats", "績效", "frontend"),
    ),
    "breakout": (
        ("bars", "K 線", "data"),
        ("range", "區間高點", "service"),
        ("break", "突破", "service"),
        ("retest", "回測確認", "api"),
        ("risk", "風控", "api"),
        ("stats", "績效", "frontend"),
    ),
    "composite": (
        ("members", "子策略訊號", "data"),
        ("vote", "投票／加權", "service"),
        ("consensus", "共識閾值", "service"),
        ("pos", "持倉", "api"),
        ("stats", "績效", "frontend"),
    ),
    "ml": (
        ("feat", "特徵工程", "data"),
        ("model", "模型（規劃）", "external"),
        ("signal", "訊號（未接通）", "service"),
        ("gate", "不可回測", "api"),
    ),
}

_CATEGORY_EDGES: dict[str, tuple[tuple[str, str, str], ...]] = {
    "ma": (
        ("bars", "fast", "SMA/EMA"),
        ("bars", "slow", "SMA/EMA"),
        ("fast", "cross", "比較"),
        ("slow", "cross", "比較"),
        ("cross", "pos", "多／空"),
        ("pos", "risk", "出場"),
        ("risk", "stats", "權益"),
    ),
    "momentum": (
        ("bars", "osc", "計算"),
        ("osc", "zone", "閾值"),
        ("zone", "signal", "訊號"),
        ("signal", "risk", "過濾"),
        ("risk", "stats", "權益"),
    ),
    "mean_reversion": (
        ("bars", "band", "統計"),
        ("band", "dev", "偏離"),
        ("dev", "entry", "進場"),
        ("entry", "exit", "回歸"),
        ("exit", "stats", "權益"),
    ),
    "volatility": (
        ("bars", "atr", "波幅"),
        ("atr", "regime", "體制"),
        ("regime", "trail", "止損"),
        ("trail", "stats", "權益"),
    ),
    "trend": (
        ("bars", "filter", "方向"),
        ("filter", "break", "入場"),
        ("break", "trail", "移動止損"),
        ("trail", "stats", "權益"),
    ),
    "pattern": (
        ("bars", "shape", "K 線"),
        ("shape", "confirm", "確認"),
        ("confirm", "entry", "入場"),
        ("entry", "invalidate", "失效"),
        ("invalidate", "stats", "權益"),
    ),
    "breakout": (
        ("bars", "range", "N 日高"),
        ("range", "break", "穿越"),
        ("break", "retest", "回測"),
        ("retest", "risk", "風控"),
        ("risk", "stats", "權益"),
    ),
    "composite": (
        ("members", "vote", "計票"),
        ("vote", "consensus", "≥2"),
        ("consensus", "pos", "進場"),
        ("pos", "stats", "權益"),
    ),
    "ml": (
        ("feat", "model", "推論"),
        ("model", "signal", "輸出"),
        ("signal", "gate", "規劃"),
    ),
}

_ENGINE_OVERRIDE: dict[str, tuple[tuple[str, str, str], tuple[tuple[str, str, str], ...]]] = {
    "dual_ma": (
        (
            ("bars", "K 線", "data"),
            ("sma5", "SMA 短", "service"),
            ("sma20", "SMA 長", "service"),
            ("cross", "金叉／死叉", "service"),
            ("pos", "持倉", "api"),
            ("risk", "止損／T+1", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "sma5", "5"),
            ("bars", "sma20", "20"),
            ("sma5", "cross", ""),
            ("sma20", "cross", ""),
            ("cross", "pos", "多／空"),
            ("pos", "risk", ""),
            ("risk", "stats", ""),
        ),
    ),
    "macd": (
        (
            ("bars", "K 線", "data"),
            ("dif", "DIF", "service"),
            ("dea", "DEA", "service"),
            ("hist", "柱狀圖", "service"),
            ("cross", "金叉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "dif", "EMA"),
            ("dif", "dea", "信號線"),
            ("dif", "hist", ""),
            ("dea", "hist", ""),
            ("hist", "cross", "翻正"),
            ("cross", "stats", ""),
        ),
    ),
    "rsi": (
        (
            ("bars", "K 線", "data"),
            ("rsi", "RSI", "service"),
            ("os", "超賣 <30", "service"),
            ("ob", "超買 >70", "service"),
            ("pos", "持倉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "rsi", "14"),
            ("rsi", "os", ""),
            ("rsi", "ob", ""),
            ("os", "pos", "做多"),
            ("ob", "pos", "平倉"),
            ("pos", "stats", ""),
        ),
    ),
    "composite": (
        (
            ("dual", "雙均線票", "data"),
            ("rsi", "RSI 票", "data"),
            ("macd", "MACD 票", "data"),
            ("vote", "多數決 ≥2", "service"),
            ("pos", "持倉", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("dual", "vote", ""),
            ("rsi", "vote", ""),
            ("macd", "vote", ""),
            ("vote", "pos", "共識"),
            ("pos", "stats", ""),
        ),
    ),
    "single_volume": (
        (
            ("bars", "K 線／成交量", "data"),
            ("vma5", "5 日均量", "service"),
            ("vma20", "20 日均量", "service"),
            ("std", "量能標準差", "service"),
            ("streak", "連續陰陽線", "service"),
            ("sig", "普通訊號", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("bars", "vma5", ""),
            ("bars", "vma20", ""),
            ("vma20", "std", "動態閾值"),
            ("bars", "streak", ""),
            ("vma5", "sig", "放量"),
            ("std", "sig", ""),
            ("streak", "sig", "確認"),
            ("sig", "stats", ""),
        ),
    ),
    "enhanced_volume": (
        (
            ("vol", "成交量分析", "data"),
            ("rsi", "RSI", "service"),
            ("bb", "布林帶", "service"),
            ("kdj", "KDJ", "service"),
            ("ord", "普通訊號", "service"),
            ("enh", "增強訊號 ≥2", "api"),
            ("stats", "績效", "frontend"),
        ),
        (
            ("vol", "ord", "均量／連續K"),
            ("rsi", "enh", "過濾"),
            ("bb", "enh", "過濾"),
            ("kdj", "enh", "過濾"),
            ("ord", "enh", "升級"),
            ("enh", "stats", "降假訊號"),
        ),
    ),
}


def _ir(
    title: str,
    kind: str,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    lanes: list[dict[str, str]] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "title": title,
        "type": kind,
        "locale": "zh-TW",
        "source": "archify",
        "inspired_by": ARCHIFY_SOURCE,
        "visual_preset": "signal-flow",
    }
    if extra_meta:
        meta.update(extra_meta)
    payload: dict[str, Any] = {"meta": meta, "nodes": nodes, "edges": edges}
    if lanes:
        payload["lanes"] = lanes
    return payload


def _node(
    nid: str,
    label: str,
    role: str,
    *,
    status: str = "",
    lane: str = "",
    detail: str = "",
) -> dict[str, Any]:
    row: dict[str, Any] = {"id": nid, "label": label, "role": role}
    if status:
        row["status"] = status
    if lane:
        row["lane"] = lane
    if detail:
        row["detail"] = detail
    return row


def _edge(src: str, dst: str, label: str = "") -> dict[str, Any]:
    row: dict[str, Any] = {"from": src, "to": dst}
    if label:
        row["label"] = label
    return row


def _listing() -> dict[str, Any]:
    return market_strategy_catalog(listing=True)


def _unique_wired(group: dict[str, Any]) -> list[dict[str, Any]]:
    """分類裡可回測的正規引擎（略過別名，避免同一引擎畫兩次）。"""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in group.get("items") or []:
        if item.get("status") != "wired":
            continue
        engine = str(item.get("engine") or item.get("id") or "")
        if not engine or engine in seen:
            continue
        if str(item.get("id") or "") != engine:
            continue
        seen.add(engine)
        out.append(item)
    return out


def _find_item(catalog: dict[str, Any], strategy_id: str) -> dict[str, Any] | None:
    key = (strategy_id or "").strip().lower()
    if not key:
        return None
    for group in catalog.get("groups") or []:
        for item in group.get("items") or []:
            if str(item.get("id", "")).lower() == key:
                return item
            if str(item.get("engine") or "").lower() == key:
                return item
    engine = resolve_strategy(key)
    if engine:
        for group in catalog.get("groups") or []:
            for item in group.get("items") or []:
                if str(item.get("id", "")).lower() == engine:
                    return item
    return None
