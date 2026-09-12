"""Token 看板生成服務。"""
from __future__ import annotations

import glob
import os
from typing import Any

from backend.billing.token_dashboard.adapter import collect_linkin_usage, dashboard_stats
from backend.billing.token_dashboard.render import render_html


def generate_token_dashboard_html(user_id: str, *, days: int = 90, include_workbuddy: bool = False) -> str:
    data = collect_linkin_usage(user_id, days=days)
    if include_workbuddy:
        wb = _try_collect_workbuddy()
        if wb and (wb.get("sess") or []):
            data = _merge_dashboard_data(data, wb)
    return render_html(data)


def generate_token_dashboard_payload(
    user_id: str,
    *,
    days: int = 90,
    include_workbuddy: bool = False,
) -> dict[str, Any]:
    data = collect_linkin_usage(user_id, days=days)
    if include_workbuddy:
        wb = _try_collect_workbuddy()
        if wb and (wb.get("sess") or []):
            data = _merge_dashboard_data(data, wb)
    return {"data": data, "stats": dashboard_stats(data), "html": render_html(data)}


def _try_collect_workbuddy() -> dict[str, Any] | None:
    projects = os.path.join(os.path.expanduser("~"), ".workbuddy", "projects")
    if not os.path.isdir(projects):
        return None
    if not glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True):
        return None
    try:
        from importlib.util import spec_from_file_location
        from pathlib import Path

        script = Path(".agents/skills/token-dashboard/scripts/gen_dashboard.py")
        if not script.is_file():
            return None
        # 僅重用 WorkBuddy 掃描邏輯：執行成本高，僅在明確請求時由 include_workbuddy 觸發
        spec = spec_from_file_location("wb_gen", script)
        if spec is None or spec.loader is None:
            return None
        # WorkBuddy 路徑由 gen_dashboard 腳本處理；此處簡化為跳過（API 預設僅 Linkin DB）
        return None
    except Exception:
        return None


def _merge_dashboard_data(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    ws = list(merged.get("ws") or [])
    models = list(merged.get("models") or [])
    model_map = {m: i for i, m in enumerate(models)}
    ws_map = {w: i for i, w in enumerate(ws)}
    sess = list(merged.get("sess") or [])

    for s in secondary.get("sess") or []:
        wname = (secondary.get("ws") or [""])[int(s.get("w") or 0)] if secondary.get("ws") else "WorkBuddy"
        if wname not in ws_map:
            ws_map[wname] = len(ws)
            ws.append(wname)
        new_recs = []
        for rec in s.get("r") or []:
            mi = int(rec[1])
            mname = (secondary.get("models") or ["unknown"])[mi] if secondary.get("models") else "unknown"
            if mname not in model_map:
                model_map[mname] = len(models)
                models.append(mname)
            new_recs.append((rec[0], model_map[mname], rec[2], rec[3], rec[4], rec[5], rec[6]))
        sess.append(
            {
                "w": ws_map[wname],
                "id": s.get("id"),
                "t": s.get("t"),
                "st": s.get("st"),
                "r": new_recs,
            }
        )
    merged["ws"] = ws
    merged["models"] = models
    merged["sess"] = sess
    merged["source"] = "Linkin 計費庫 + WorkBuddy 日誌"
    return merged
