"""OPC 監控中心聚合：護欄設定 + 審計 + 即時標籤（經 opc_service REST）。

前端不得直連 OPC UA；本模組只打 opc_service HTTP，寫入仍必須走 guard.py。
opc_service 不可達時降級為模擬快照（SIM_TAGS 初始值），不拋錯。
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Any

import httpx

from backend.services.dashboard import collect_opc_audit
from backend.services.task_manager import task_manager
from opc_service.client.nodes import short_tag_name
from opc_service.config import settings

logger = logging.getLogger(__name__)

OPC_SERVICE_URL = os.getenv("OPC_SERVICE_URL", "http://127.0.0.1:8001").rstrip("/")
LIVE_TIMEOUT = httpx.Timeout(2.0, connect=1.0)
_LOCAL_OPC_FALLBACKS = (
    "http://127.0.0.1:8001",
    "http://localhost:8001",
)


def _opc_service_candidates(base_url: str | None = None) -> list[str]:
    """本機開發時若環境變數仍為 Docker 主機名，自動嘗試 localhost。"""
    primary = (base_url or OPC_SERVICE_URL).rstrip("/")
    candidates = [primary]
    if "opc_service" in primary:
        for local in _LOCAL_OPC_FALLBACKS:
            if local not in candidates:
                candidates.append(local)
    elif primary not in _LOCAL_OPC_FALLBACKS:
        candidates.extend(_LOCAL_OPC_FALLBACKS)
    # 去重且保序
    seen: set[str] = set()
    ordered: list[str] = []
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered
WRITABLE_OPC = frozenset({"ValvePosition", "MotorSpeed"})

_ROOT = Path(__file__).resolve().parents[2]
_SIM_TAGS_PATH = _ROOT / "opc_service" / "simulator" / "tags.py"


def _load_sim_tags() -> list[dict[str, Any]]:
    spec = importlib.util.spec_from_file_location("opc_sim_tags", _SIM_TAGS_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 OPC 標籤定義：{_SIM_TAGS_PATH}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.SIM_TAGS)


def _catalog_names() -> frozenset[str]:
    return frozenset(tag["name"] for tag in _load_sim_tags())


def _guard_payload() -> dict[str, Any]:
    bounds = {
        key: {"min": lo, "max": hi} for key, (lo, hi) in settings.write_bounds.items()
    }
    return {
        "write_whitelist": sorted(settings.write_whitelist),
        "write_bounds": bounds,
        "require_approval": settings.require_approval,
        "sim_enabled": settings.sim_enabled,
        "opc_server": settings.opc_server_url,
    }


def _catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "name": tag["name"],
            "unit": tag.get("unit", ""),
            "desc": tag.get("desc", ""),
            "range": list(tag["range"]),
            "writable": tag["name"] in WRITABLE_OPC,
        }
        for tag in _load_sim_tags()
    ]


def _simulated_readings() -> list[dict[str, Any]]:
    """opc_service 離線或讀取失敗時，用模擬器初始值填充監控表格。"""
    return [
        {
            "tag_name": tag["name"],
            "value": tag["init"],
            "data_type": "Double",
            "quality": "Simulated",
            "source_timestamp": None,
        }
        for tag in _load_sim_tags()
    ]


def _catalog_key(row: dict[str, Any]) -> str | None:
    """將 browse/read 列映射到 SIM_TAGS 目錄名。"""
    tag_name = str(row.get("tag_name") or "")
    node_id = row.get("node_id")
    short = short_tag_name(tag_name, str(node_id) if node_id else None)
    names = _catalog_names()
    if short in names:
        return short
    for name in names:
        if tag_name == name or tag_name.endswith(name) or name in tag_name:
            return name
    return None


def _reading_from_row(row: dict[str, Any], catalog_name: str) -> dict[str, Any]:
    return {
        "tag_name": catalog_name,
        "value": row.get("value"),
        "data_type": row.get("data_type") or "Double",
        "quality": row.get("quality") or "Good",
        "source_timestamp": row.get("source_timestamp"),
    }


def _align_readings_to_catalog(
    readings: list[dict[str, Any]],
    browse: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """對齊 SIM_TAGS 目錄；缺值標籤以模擬初始值補齊。"""
    by_name: dict[str, dict[str, Any]] = {}

    for row in readings:
        key = _catalog_key(row)
        if not key or row.get("value") is None:
            continue
        prev = by_name.get(key)
        if prev is None or prev.get("value") is None:
            by_name[key] = _reading_from_row(row, key)

    for row in browse or []:
        key = _catalog_key(row)
        if not key or key in by_name or row.get("value") is None:
            continue
        by_name[key] = _reading_from_row(row, key)

    simulated = False
    aligned: list[dict[str, Any]] = []
    for tag in _load_sim_tags():
        name = tag["name"]
        if name in by_name:
            aligned.append(by_name[name])
        else:
            simulated = True
            aligned.append(
                {
                    "tag_name": name,
                    "value": tag["init"],
                    "data_type": "Double",
                    "quality": "Simulated",
                    "source_timestamp": None,
                }
            )
    return aligned, simulated



def _recent_opc_tasks(limit: int = 8) -> list[dict[str, Any]]:
    records = [
        rec
        for rec in task_manager.tasks.values()
        if rec.resolved_path == "opc" or rec.opc_state
    ]
    records.sort(key=lambda r: r.created_at, reverse=True)
    out: list[dict[str, Any]] = []
    for rec in records[:limit]:
        data = rec.to_dict()
        data.pop("events", None)
        data.pop("kanban", None)
        out.append(data)
    return out


def _fetch_opc_live_once(url: str) -> dict[str, Any]:
    with httpx.Client(timeout=LIVE_TIMEOUT) as client:
        health_resp = client.get(f"{url}/opc/health")
        health_resp.raise_for_status()
        health = health_resp.json()
        tags_resp = client.get(f"{url}/opc/tags")
        tags_payload = tags_resp.json() if tags_resp.is_success else {"tags": []}
        browse = tags_payload.get("tags") or []
        names = [t.get("tag_name") for t in browse if t.get("tag_name")]
        node_ids = [t.get("node_id") for t in browse if t.get("tag_name")]
        readings: list[dict[str, Any]] = []
        if names:
            read_resp = client.post(
                f"{url}/opc/read",
                json={"tag_names": names[:50], "node_ids": node_ids[:50]},
            )
            if read_resp.is_success:
                readings = read_resp.json().get("tags") or []

        aligned, gap_simulated = _align_readings_to_catalog(readings, browse)

        return {
            "reachable": True,
            "health": health if isinstance(health, dict) else {},
            "browse_tags": browse,
            "readings": aligned,
            "simulated": gap_simulated,
            "error": tags_payload.get("error"),
            "service_url": url,
        }


def fetch_opc_live(base_url: str | None = None) -> dict[str, Any]:
    """打 opc_service：health → tags → read。失敗回傳 reachable=false + 模擬讀數。"""
    empty: dict[str, Any] = {
        "reachable": False,
        "health": None,
        "browse_tags": [],
        "readings": _simulated_readings(),
        "simulated": True,
        "error": None,
        "service_url": (base_url or OPC_SERVICE_URL).rstrip("/"),
    }
    errors: list[str] = []
    for url in _opc_service_candidates(base_url):
        try:
            return _fetch_opc_live_once(url)
        except Exception as exc:
            msg = f"{url}: {exc}"
            errors.append(msg)
            logger.info("opc_service 即時資料不可達：%s", msg)
    empty["error"] = "; ".join(errors)[:300] if errors else None
    return empty


def collect_opc_monitor() -> dict[str, Any]:
    """監控中心 OPC 分頁的完整快照。"""
    live = fetch_opc_live()
    aligned, gap_simulated = _align_readings_to_catalog(
        live.get("readings") or [],
        live.get("browse_tags") or [],
    )
    live = {
        **live,
        "readings": aligned,
        "simulated": bool(live.get("simulated")) or gap_simulated,
    }
    return {
        "guard": _guard_payload(),
        "catalog": _catalog_payload(),
        "audit": collect_opc_audit(),
        "live": live,
        "recent_tasks": _recent_opc_tasks(),
        "service_url": OPC_SERVICE_URL,
    }
