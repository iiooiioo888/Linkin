"""從後端單一資料源匯出監控中心前端降級快照。

輸出 `frontend/src/generated/monitor-fallback.json`，供 GitHub Pages
與後端不可達時共用同一份角色／Hub／OPC 目錄，避免前後端各維護一套。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.hub.catalog import (
    CN_CHAIN,
    DEFAULT_CHAIN,
    DEFAULT_LATENCY_MS,
    FORBIDDEN_MODEL_RE,
    HUB_CATALOG,
    INTEL,
    PRICE_PER_1M,
    PROVIDER_OF,
    RACE_PAIR,
)
from backend.services.agent_monitor import build_idle_roster

OUT_DIR = ROOT / "frontend" / "src" / "generated"
OUT_JSON = OUT_DIR / "monitor-fallback.json"

WRITABLE_OPC = frozenset({"ValvePosition", "MotorSpeed"})


def _hub_models() -> list[dict]:
    models: list[dict] = []
    for model_id in sorted(HUB_CATALOG):
        latency = DEFAULT_LATENCY_MS.get(model_id, 400.0)
        price_in, price_out = PRICE_PER_1M.get(model_id, (0.0, 0.0))
        models.append(
            {
                "id": model_id,
                "provider": PROVIDER_OF[model_id],
                "intelligence": INTEL[model_id],
                "latency_ewma_ms": latency,
                "ttfb_ms": round(latency * 0.2),
                "price_in_per_1m": price_in,
                "price_out_per_1m": price_out,
                "consecutive_fail": 0,
                "circuit": {"state": "CLOSED", "fail_ratio": 0, "window_calls": 0},
            }
        )
    return models


def _opc_catalog() -> list[dict]:
    import importlib.util

    tags_path = ROOT / "opc_service" / "simulator" / "tags.py"
    spec = importlib.util.spec_from_file_location("opc_sim_tags", tags_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 OPC 標籤定義：{tags_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sim_tags = mod.SIM_TAGS

    catalog: list[dict] = []
    for tag in sim_tags:
        low, high = tag["range"]
        catalog.append(
            {
                "name": tag["name"],
                "unit": tag.get("unit", ""),
                "desc": tag.get("desc", ""),
                "range": [low, high],
                "writable": tag["name"] in WRITABLE_OPC,
            }
        )
    return catalog


def export_snapshot() -> dict:
    return {
        "version": 1,
        "generated_from": "backend",
        "agents": build_idle_roster(),
        "hub_models": _hub_models(),
        "hub_routing": {
            "default_chain": list(DEFAULT_CHAIN),
            "cn_chain": list(CN_CHAIN),
            "race_pair": list(RACE_PAIR),
            "forbidden_vendor": "anthropic",
            "forbidden_pattern": FORBIDDEN_MODEL_RE.pattern,
        },
        "opc_catalog": _opc_catalog(),
    }


def main() -> None:
    payload = export_snapshot()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(text + "\n", encoding="utf-8")
    print(
        f"exported monitor fallback: {len(payload['agents'])} agents, "
        f"{len(payload['hub_models'])} hub models, "
        f"{len(payload['opc_catalog'])} opc tags -> {OUT_JSON.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
