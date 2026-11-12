"""RAHO 文字標籤：車道／層級／方向／種類標籤常數與取用函式。"""

from __future__ import annotations

from .layers import LANE_COMMAND, LANE_INSPECT, LANE_KERNEL, LAYER_META, RahoLayer

LANE_LABELS: dict[str, str] = {
    LANE_KERNEL: "環境核心",
    LANE_COMMAND: "席位",
    LANE_INSPECT: "獨立審查",
}


LAYER_LABELS: dict[int, str] = {layer: meta["full"] for layer, meta in LAYER_META.items()}
LAYER_SHORT: dict[int, str] = {layer: meta["short"] for layer, meta in LAYER_META.items()}


DIRECTION_LABELS: dict[str, str] = {
    "up": "質詢上拋",
    "down": "任務下達",
    "inspect": "獨立審查",
    "inject": "環境注入",
}
DIRECTION_GLYPH: dict[str, str] = {
    "up": "↑",
    "down": "↓",
    "inspect": "⇄",
    "inject": "⇢",
}


KIND_LABELS: dict[str, str] = {
    "mandate": "需求下達",
    "user_grill": "用戶審計",
    "mgp": "戰前質詢",
    "escalate": "向上呈報",
    "resolve": "解除阻塞",
    "timeout": "決策逾時",
    "user_decide": "用戶裁決",
    "inspect": "憲兵審查",
    "submit": "提交驗收",
    "campaign": "戰役下達",
    "rework": "退回重做",
    "l0": "環境注入",
    "memory": "記憶回放",
    "knowledge": "知識引用",
}


def layer_label(layer: int | RahoLayer | None, *, short: bool = False) -> str:
    try:
        key = int(layer) if layer is not None else 2
    except (TypeError, ValueError):
        key = 2
    table = LAYER_SHORT if short else LAYER_LABELS
    return table.get(key, f"L{key}")


def kind_label(kind: str | None) -> str:
    key = str(kind or "").strip()
    return KIND_LABELS.get(key, key or "質詢")


def direction_label(direction: str | None) -> str:
    key = str(direction or "").strip()
    return DIRECTION_LABELS.get(key, key or "質詢")


def lane_label(lane: str | None) -> str:
    key = str(lane or "").strip()
    return LANE_LABELS.get(key, key or "席位")
