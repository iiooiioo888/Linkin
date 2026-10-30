"""Hub 靜態目錄 ID ↔ Registry model_id 顯式映射（P4/#133 Q3）。

載體優先序：
1. 環境變數 ``MODELGW_HUB_ID_MAP``（JSON 物件：hub_id → registry_id｜""｜null｜"TBD"）
2. 同目錄 ``hub_id_map.json`` 的 ``map`` 欄

規則（locked）：
- 僅經本表；無映射／空／TBD／UNSUPPORTED → ``UNSUPPORTED_MODEL`` 形狀
- **禁止**別名猜測
- 不在表鍵內的 ID → 原樣交給 admit（Registry 自決）
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_PATH = Path(__file__).resolve().parent / "hub_id_map.json"
_UNMAPPED_TOKENS = {"", "tbd", "unsupported", "unsupported_model", "null", "none"}

_cached: dict[str, str | None] | None = None


def reset_hub_id_map_cache() -> None:
    """測試用：清快取，下次重新載入。"""
    global _cached
    _cached = None


def _normalize_value(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.lower() in _UNMAPPED_TOKENS:
        return None
    return text


def _load_from_env() -> dict[str, str | None] | None:
    raw = (os.getenv("MODELGW_HUB_ID_MAP") or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("MODELGW_HUB_ID_MAP JSON 無效：%s", exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("MODELGW_HUB_ID_MAP 須為物件")
        return {}
    # 允許 {"map": {...}} 或直接 {...}
    payload = data.get("map") if "map" in data and isinstance(data.get("map"), dict) else data
    out: dict[str, str | None] = {}
    for key, val in payload.items():
        if str(key).startswith("_"):
            continue
        out[str(key).strip()] = _normalize_value(val)
    return out


def _load_from_file() -> dict[str, str | None]:
    path = (os.getenv("MODELGW_HUB_ID_MAP_PATH") or "").strip() or str(_DEFAULT_PATH)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning("Hub ID map 不存在：%s（空表）", path)
        return {}
    except Exception as exc:
        logger.warning("Hub ID map 載入失敗（%s）：%s", path, exc)
        return {}
    if not isinstance(data, dict):
        return {}
    payload = data.get("map") if isinstance(data.get("map"), dict) else data
    out: dict[str, str | None] = {}
    for key, val in payload.items():
        if str(key).startswith("_"):
            continue
        out[str(key).strip()] = _normalize_value(val)
    return out


def load_hub_id_map(*, force: bool = False) -> dict[str, str | None]:
    """回傳 hub_id → registry_id｜None（None＝顯式未映射）。"""
    global _cached
    if _cached is not None and not force:
        return _cached
    env_map = _load_from_env()
    _cached = env_map if env_map is not None else _load_from_file()
    return _cached


def resolve_hub_model_id(model_id: str) -> tuple[str | None, bool]:
    """解析呼叫端 model_id。

    Returns:
        ``(admit_model_id, unmapped)``
        - 不在映射表鍵內 → ``(原 id, False)``（交 Registry admit）
        - 在表內且有有效 registry id → ``(registry_id, False)``
        - 在表內但空／TBD／null → ``(None, True)``（UNSUPPORTED 形狀）
    """
    mid = (model_id or "").strip()
    if not mid:
        return None, False
    mapping = load_hub_id_map()
    if mid not in mapping:
        return mid, False
    registry_id = mapping[mid]
    if not registry_id:
        return None, True
    return registry_id, False
