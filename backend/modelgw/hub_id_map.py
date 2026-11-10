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
    nested = data.get("map")
    payload: dict[str, Any] = nested if isinstance(nested, dict) else data
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
    nested = data.get("map")
    payload: dict[str, Any] = nested if isinstance(nested, dict) else data
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


# G-MAP1：覆蓋率閘（擋「Hub 已統一準入」宣稱；不填生產 map 值）
#
# 文件化 sunset／deprecated 結構（可與 map 同檔）：
# {
#   "map": { "hub-id": "registry-id" | "" | "TBD" },
#   "sunset": {
#     "hub-id": {"status": "deprecated"|"sunset", "note": "..."}
#   }
# }
# 鍵亦可放在 top-level ``deprecated``（等價於 sunset）。
# 空／TBD 鍵若未列入 sunset／deprecated → 不得宣稱統一。

_SUNSET_STATUSES = frozenset({"deprecated", "sunset", "retired", "unsupported_long_term"})


def _load_raw_document() -> dict[str, Any]:
    """載入原始 JSON／env 文件（含 sunset 元資料；供覆蓋率閘）。"""
    raw = (os.getenv("MODELGW_HUB_ID_MAP") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    path = (os.getenv("MODELGW_HUB_ID_MAP_PATH") or "").strip() or str(_DEFAULT_PATH)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_hub_id_sunset(*, force: bool = False) -> dict[str, dict[str, Any]]:
    """回傳 hub_id → sunset／deprecated 元資料（僅 status 合法者）。

    ``force`` 保留與 ``load_hub_id_map`` 對稱；本函每次重讀文件（覆蓋率閘用）。
    """
    _ = force
    data = _load_raw_document()
    out: dict[str, dict[str, Any]] = {}
    for key in ("sunset", "deprecated"):
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        for hub_id, meta in block.items():
            hid = str(hub_id).strip()
            if not hid or hid.startswith("_"):
                continue
            if isinstance(meta, str):
                status = meta.strip().lower()
                entry: dict[str, Any] = {"status": status}
            elif isinstance(meta, dict):
                status = str(meta.get("status") or "").strip().lower()
                entry = dict(meta)
                entry["status"] = status
            else:
                continue
            if status in _SUNSET_STATUSES:
                out[hid] = entry
    return out


def hub_id_map_coverage() -> dict[str, Any]:
    """回報靜態 map 覆蓋率：filled／empty／total／keys。

    - filled：有有效 Registry id
    - empty：表內空／TBD／null（未映射）
    - passthrough 鍵不在此表（非 Hub 靜態鍵）
    """
    mapping = load_hub_id_map()
    filled: list[str] = []
    empty: list[str] = []
    for key, val in mapping.items():
        if val:
            filled.append(key)
        else:
            empty.append(key)
    total = len(mapping)
    filled_n = len(filled)
    return {
        "total": total,
        "filled": filled_n,
        "empty": len(empty),
        "filled_keys": sorted(filled),
        "empty_keys": sorted(empty),
        "coverage_ratio": (filled_n / total) if total else 1.0,
    }


def hub_unified_claim_allowed() -> bool:
    """是否允許宣稱「Hub 呼叫面已統一準入」（G-MAP1）。

    條件（二選一或混合）：
    1. 覆蓋率 100%（每個表鍵皆有真實 Registry id）；或
    2. 每個空鍵皆在 sunset／deprecated 文件結構中明示長期下架

    生產 ``hub_id_map.json`` 靜態 9 全空且無 sunset → **False**（擋宣稱）。
    """
    cov = hub_id_map_coverage()
    if cov["total"] == 0:
        return False
    if cov["empty"] == 0:
        return True
    sunset = load_hub_id_sunset()
    for key in cov["empty_keys"]:
        if key not in sunset:
            return False
    return True
