"""OPC 感知节点 — 从 OPC 服务读取传感器数据（P2：边缘-云分层）。

分层策略：
  - edge：优先使用本地边缘缓存（TTL 内复用，零延迟）
  - cloud：始终 HTTP 拉取 OPC 微服务
  - auto（默认）：边缘缓存命中则复用，否则云拉取并更新缓存
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

from opc_service.prompts import DEFAULT_SENSE_TAGS

logger = logging.getLogger(__name__)

OPC_SERVICE_URL = os.getenv("OPC_SERVICE_URL", "http://localhost:8001")
OPC_TIER = os.getenv("EVOL_OPC_TIER", "auto").lower()  # auto | edge | cloud
OPC_EDGE_TTL = float(os.getenv("EVOL_OPC_EDGE_TTL", "5"))  # 边缘缓存秒数
_EDGE_CACHE_PATH = Path(os.getenv(
    "EVOL_OPC_EDGE_CACHE",
    str(Path(__file__).resolve().parent / "data" / "edge_cache.json"),
))


def _load_edge_cache() -> dict[str, Any]:
    if not _EDGE_CACHE_PATH.exists():
        return {}
    try:
        with open(_EDGE_CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_edge_cache(readings: dict[str, dict]) -> None:
    _EDGE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updated_at": time.time(),
        "readings": readings,
    }
    with open(_EDGE_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


def _edge_readings_fresh() -> dict[str, dict] | None:
    cache = _load_edge_cache()
    updated = float(cache.get("updated_at", 0))
    if time.time() - updated > OPC_EDGE_TTL:
        return None
    readings = cache.get("readings")
    return readings if isinstance(readings, dict) and readings else None


async def _read_opc_tags(tag_names: list[str]) -> dict[str, dict]:
    """通过 HTTP 调用 OPC 服务读取标签值。"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{OPC_SERVICE_URL}/opc/read",
                json={"tag_names": tag_names},
            )
            resp.raise_for_status()
            data = resp.json()
            return {
                tag["tag_name"]: {
                    "value": tag["value"],
                    "data_type": tag.get("data_type", ""),
                    "quality": tag.get("quality", "Good"),
                }
                for tag in data.get("tags", [])
            }
    except Exception as exc:
        logger.warning("OPC 读取失败：%s", exc)
        return {}


async def sense_opc(state: dict) -> dict[str, Any]:
    """节点 S1：从 OPC 服务读取传感器数据（边缘-云分层）。"""
    tier = OPC_TIER
    source = "cloud"

    if tier in ("auto", "edge"):
        cached = _edge_readings_fresh()
        if cached:
            source = "edge"
            return {
                "opc_readings": cached,
                "opc_anomaly_detected": False,
                "opc_actions": [],
                "opc_source": source,
            }
        if tier == "edge":
            logger.warning("边缘缓存未命中且 EVOL_OPC_TIER=edge，返回空读数")
            return {
                "opc_readings": {},
                "opc_anomaly_detected": False,
                "opc_actions": [],
                "opc_source": "edge_miss",
            }

    readings = await _read_opc_tags(DEFAULT_SENSE_TAGS)
    if readings:
        _save_edge_cache(readings)

    return {
        "opc_readings": readings,
        "opc_anomaly_detected": False,
        "opc_actions": [],
        "opc_source": source,
    }
