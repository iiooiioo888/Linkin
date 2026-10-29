"""ModelGW 進程內單例與掛載模式（WIRE）。

環境變數（文件化，預設安全關閉）：

- ``MODELGW_WIRE_MODE``：``off``（預設）｜``shadow``｜``enforce``
  - off：不介入 ``call_llm``；HTTP 面仍可做 admit／健康檢查
  - shadow：``call_llm`` 前準入並記日誌，**不阻擋**上游
  - enforce：``call_llm`` 前硬閘；PROVISIONING／拒絕依庫層 http_hint 拋出
- ``MODELGW_REGISTRY_SEED``：JSON seed 路徑（預設 ``seeds/demo_registry.json``）
- ``MODELGW_RETRY_AFTER``：PROVISIONING 回應的 Retry-After 秒數（預設 30）

不讀 HUB_CATALOG、不 import hub.circuit。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from backend.modelgw.registry import InMemoryRegistry, load_json_seed
from backend.modelgw.service import ModelGWService

logger = logging.getLogger(__name__)

_DEFAULT_SEED = Path(__file__).resolve().parent / "seeds" / "demo_registry.json"
_service: ModelGWService | None = None

_TRUE = {"1", "true", "yes", "on"}
_ENFORCE = _TRUE | {"enforce", "hard"}
_SHADOW = {"shadow", "observe", "log", "dry-run", "dryrun"}


def wire_mode() -> str:
    """回傳 off｜shadow｜enforce。"""
    raw = (os.getenv("MODELGW_WIRE_MODE") or "off").strip().lower()
    if raw in _ENFORCE:
        return "enforce"
    if raw in _SHADOW:
        return "shadow"
    return "off"


def retry_after_seconds() -> str:
    raw = (os.getenv("MODELGW_RETRY_AFTER") or "30").strip()
    try:
        n = max(1, int(raw))
    except ValueError:
        n = 30
    return str(n)


def _load_seed_records():
    path = (os.getenv("MODELGW_REGISTRY_SEED") or "").strip() or str(_DEFAULT_SEED)
    try:
        return load_json_seed(path)
    except FileNotFoundError:
        logger.warning("ModelGW seed 不存在：%s（空 Registry）", path)
        return []
    except Exception as exc:  # noqa: BLE001 — 啟動時降級為空表
        logger.warning("ModelGW seed 載入失敗（%s）：%s", path, exc)
        return []


def get_service() -> ModelGWService:
    """懶載入單例；測試可用 ``reset_service`` 替換。"""
    global _service
    if _service is None:
        _service = ModelGWService(registry=InMemoryRegistry(seed=_load_seed_records()))
    return _service


def reset_service(service: ModelGWService | None = None) -> None:
    """測試用：清空或注入單例。"""
    global _service
    _service = service


def precheck_model(model_id: str | None) -> None:
    """給 ``call_llm`` 用的可降級準入閘。

    - off：直接返回
    - shadow：準入失敗只記 log
    - enforce：拋 ModelGWError（由呼叫端／HTTP 層映射）
    """
    if not model_id or not str(model_id).strip():
        return
    mode = wire_mode()
    if mode == "off":
        return
    from backend.modelgw.errors import ModelGWError

    try:
        get_service().admit_or_raise(str(model_id).strip())
    except ModelGWError as exc:
        if mode == "shadow":
            logger.info(
                "MODELGW shadow admit blocked-would-be code=%s model=%s detail=%s",
                exc.code,
                model_id,
                exc.detail,
            )
            return
        raise
