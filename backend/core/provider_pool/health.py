"""模型池健康：熔斷狀態、主動探活、reset 與池健康快照。"""

from __future__ import annotations

import os
from typing import Any

from . import catalog
from .catalog import parse_models_payload
from .constants import logger
from .helpers import (
    _model_in_pool,
    _now_iso,
    clamp_model,
    classify_provider,
    models_endpoint,
    pool_failover_slow_s,
)

# ── 模型池呼叫健康 / Failover（P1）────────────────────────────
POOL_FAILURE_THRESHOLD = int(os.getenv("EVOL_LLM_POOL_FAIL_THRESHOLD", "2"))
POOL_OPEN_DURATION_S = float(os.getenv("EVOL_LLM_POOL_OPEN_SEC", "60"))
_pool_health: dict[str, dict[str, Any]] = {}
_last_probe: dict[str, Any] = {
    "at": "",
    "ok": False,
    "latency_ms": 0,
    "reason": "",
    "mode": "catalog",
    "opened": [],
    "healed": [],
    "error": "",
    "enabled": True,
}


def _health_entry(model: str) -> dict[str, Any]:
    if model not in _pool_health:
        _pool_health[model] = {
            "failures": 0,
            "successes": 0,
            "open_until": 0.0,
            "last_error": "",
            "last_latency_ms": 0,
            "probe_open": False,
        }
    return _pool_health[model]


def pool_probe_enabled() -> bool:
    return os.getenv("EVOL_LLM_POOL_PROBE", "true").lower() not in {"0", "false", "no"}


def pool_probe_timeout_s() -> float:
    try:
        return max(0.5, float(os.getenv("EVOL_LLM_POOL_PROBE_TIMEOUT", "3")))
    except (TypeError, ValueError):
        return 3.0


def pool_probe_ping_enabled() -> bool:
    """是否對主模型發輕量 ping（較貴；預設關閉，只做 GET /models）。"""
    return os.getenv("EVOL_LLM_POOL_PROBE_PING", "false").lower() in {"1", "true", "yes"}


def pool_probe_snapshot() -> dict[str, Any]:
    snap = dict(_last_probe)
    snap.update(
        {
            "enabled": pool_probe_enabled(),
            "timeout_s": pool_probe_timeout_s(),
            "ping_enabled": pool_probe_ping_enabled(),
        }
    )
    return snap


def force_open_pool_model(model: str, error: str = "", *, from_probe: bool = True) -> None:
    """主動熔斷：不等待連續失敗閾值。"""
    import time

    entry = _health_entry(model)
    entry["failures"] = max(int(entry.get("failures") or 0), POOL_FAILURE_THRESHOLD)
    entry["open_until"] = time.monotonic() + POOL_OPEN_DURATION_S
    entry["probe_open"] = bool(from_probe)
    if error:
        entry["last_error"] = error[:200]
    logger.warning("模型池主動熔斷 %s：%s", model, error or "probe")


def heal_pool_model(model: str, *, only_probe: bool = True) -> bool:
    """恢復模型；預設只解除探活造成的熔斷，不覆蓋真實呼叫失敗。"""
    entry = _health_entry(model)
    if only_probe and not entry.get("probe_open"):
        return False
    entry["failures"] = 0
    entry["open_until"] = 0.0
    entry["probe_open"] = False
    entry["last_error"] = ""
    entry["successes"] = int(entry.get("successes") or 0) + 1
    return True


def record_pool_call(
    model: str,
    failed: bool,
    duration_s: float = 0.0,
    error: str = "",
) -> None:
    """記錄單次 LLM 呼叫結果，連續失敗達閾值則暫時熔斷該模型。"""
    import time

    entry = _health_entry(model)
    now = time.monotonic()
    entry["last_latency_ms"] = int(duration_s * 1000)
    slow = duration_s >= pool_failover_slow_s()
    if failed or slow:
        entry["failures"] = int(entry.get("failures") or 0) + 1
        entry["probe_open"] = False
        if error:
            entry["last_error"] = error[:200]
        if entry["failures"] >= POOL_FAILURE_THRESHOLD:
            entry["open_until"] = now + POOL_OPEN_DURATION_S
            logger.warning(
                "模型池熔斷 %s（連續失敗 %d 次，%.0fs 內跳過）",
                model,
                entry["failures"],
                POOL_OPEN_DURATION_S,
            )
    else:
        entry["successes"] = int(entry.get("successes") or 0) + 1
        entry["failures"] = max(0, int(entry.get("failures") or 0) - 1)
        if entry["failures"] == 0:
            entry["open_until"] = 0.0
            entry["last_error"] = ""
            entry["probe_open"] = False


def is_pool_model_open(model: str) -> bool:
    import time

    entry = _health_entry(model)
    return time.monotonic() < float(entry.get("open_until") or 0.0)


def pool_health_snapshot() -> dict[str, dict[str, Any]]:
    import time

    now = time.monotonic()
    out: dict[str, dict[str, Any]] = {}
    for model, entry in _pool_health.items():
        open_until = float(entry.get("open_until") or 0.0)
        out[model] = {
            "failures": int(entry.get("failures") or 0),
            "successes": int(entry.get("successes") or 0),
            "open": now < open_until,
            "open_for_sec": max(0.0, open_until - now) if now < open_until else 0.0,
            "last_error": entry.get("last_error") or "",
            "last_latency_ms": int(entry.get("last_latency_ms") or 0),
            "probe_open": bool(entry.get("probe_open")),
        }
    return out


def reset_pool_health() -> None:
    """測試用：清空進程內健康狀態。"""
    _pool_health.clear()
    _last_probe.update(
        {
            "at": "",
            "ok": False,
            "latency_ms": 0,
            "reason": "",
            "mode": "catalog",
            "opened": [],
            "healed": [],
            "error": "",
            "enabled": pool_probe_enabled(),
        }
    )


def probe_pool_health(
    *,
    reason: str = "schedule",
    ping_fn: Any | None = None,
) -> dict[str, Any]:
    """主動探活：預設 GET /models；可選對主模型發輕量 ping。

    - 端點不可用 → 主動熔斷目前主模型，讓 Failover 提前切備援
    - 目錄有回應但缺某模型 → 熔斷該模型
    - 探活成功 → 只解除 probe_open 熔斷（不覆蓋真實呼叫失敗）
    """
    import time

    from backend.core.llm_config import get_runtime_config

    if not pool_probe_enabled():
        _last_probe.update(
            {
                "at": _now_iso(),
                "ok": False,
                "latency_ms": 0,
                "reason": reason,
                "mode": "disabled",
                "opened": [],
                "healed": [],
                "error": "probe disabled",
                "enabled": False,
            }
        )
        return pool_probe_snapshot()

    runtime = get_runtime_config()
    api_base = str(runtime.get("api_base") or "")
    api_key = str(runtime.get("api_key") or "")
    primary = clamp_model(str(runtime.get("model") or ""), cfg=runtime)
    allowed = [str(x) for x in (runtime.get("allowed_models") or []) if str(x).strip()]
    kind = str(runtime.get("provider_kind") or classify_provider(api_base, primary))
    url = models_endpoint(api_base, kind)
    opened: list[str] = []
    healed: list[str] = []
    mode = "catalog"
    error = ""
    ok = False
    latency_ms = 0

    t0 = time.monotonic()
    catalog_ids: list[str] = []
    if url:
        try:
            payload = catalog._http_get_json(url, api_key, timeout=pool_probe_timeout_s())
            catalog_ids = [row["id"] for row in parse_models_payload(payload)]
            latency_ms = int((time.monotonic() - t0) * 1000)
            ok = True
        except Exception as exc:
            latency_ms = int((time.monotonic() - t0) * 1000)
            error = f"endpoint:{exc}"[:300]
            force_open_pool_model(primary, error, from_probe=True)
            opened.append(primary)
            logger.warning("模型池探活失敗（%s）：%s", url, error)
    else:
        error = "no models endpoint"
        latency_ms = int((time.monotonic() - t0) * 1000)

    if ok and catalog_ids:
        for model in allowed or [primary]:
            if _model_in_pool(model, catalog_ids):
                if heal_pool_model(model, only_probe=True):
                    healed.append(model)
            else:
                # 目錄明確不含此模型 → 提前熔斷，避免用戶請求才失敗
                force_open_pool_model(model, "probe: missing from catalog", from_probe=True)
                opened.append(model)

    if ok and pool_probe_ping_enabled() and ping_fn is not None:
        mode = "catalog+ping"
        # 含已熔斷模型：主動 ping 才能恢復；仍限制前 2 個控制成本
        targets: list[str] = []
        for model in [primary, *allowed]:
            if model and model not in targets:
                targets.append(model)
            if len(targets) >= 2:
                break
        for model in targets:
            if model in opened:
                continue
            pt0 = time.monotonic()
            try:
                ping_fn(
                    prompt="ping",
                    system=None,
                    model=model,
                    max_retries=1,
                    timeout=pool_probe_timeout_s(),
                    max_tokens=8,
                )
                record_pool_call(model, False, time.monotonic() - pt0)
                # ping 成功可視為真實可用，解除任何熔斷
                heal_pool_model(model, only_probe=False)
                if model not in healed:
                    healed.append(model)
            except Exception as exc:
                force_open_pool_model(model, f"probe ping:{exc}", from_probe=True)
                opened.append(model)

    # 去重保序
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    _last_probe.update(
        {
            "at": _now_iso(),
            "ok": ok,
            "latency_ms": latency_ms,
            "reason": reason,
            "mode": mode,
            "opened": _uniq(opened),
            "healed": _uniq(healed),
            "error": error,
            "enabled": True,
        }
    )
    return pool_probe_snapshot()
