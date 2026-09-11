"""成本 / 速度感知路由（P1）。

依任務複雜度與管線環節，從 cost_speed 配置選擇最合適的模型：
  - 簡單問題 → 便宜快速模型（如 qwen-turbo）
  - 複雜推理 → 深度模型（如 deepseek-v4-pro）
  - 複雜任務 → 公司運行時路徑

配置檔：backend/config/cost_speed.json（可透過 EVOL_COST_SPEED_PATH 覆寫，支援熱重載）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from backend.core.provider_pool import clamp_model

logger = logging.getLogger(__name__)

TaskComplexity = Literal["simple", "medium", "complex"]
RoutePath = Literal["simple", "company"]

_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "cost_speed.json"

# 各複雜度的輸出長度上限（字符數）兜底值
_DEFAULT_MAX_OUTPUT_CHARS: dict[str, int] = {
    "simple": 800,
    "medium": 2000,
    "complex": 4000,
}

_config_cache: dict[str, Any] | None = None
_config_mtime: float = 0.0

_COMPLEX_KEYWORDS_RE: re.Pattern[str] | None = None


def _config_path() -> Path:
    raw = os.getenv("EVOL_COST_SPEED_PATH", "").strip()
    return Path(raw) if raw else _DEFAULT_CONFIG_PATH


def _load_raw_config() -> dict[str, Any]:
    global _config_cache, _config_mtime
    path = _config_path()
    if not path.exists():
        logger.warning("cost_speed 配置不存在：%s，使用內建預設", path)
        return _builtin_defaults()
    mtime = path.stat().st_mtime
    if _config_cache is not None and mtime == _config_mtime:
        return _config_cache
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            raise ValueError("配置根節點必須為物件")
        _config_cache = loaded
        _config_mtime = mtime
        logger.info("已載入 cost_speed 配置：%s", path)
        return _config_cache
    except Exception as exc:
        logger.warning("載入 cost_speed 配置失敗（使用內建預設）：%s", exc)
        return _builtin_defaults()


def _builtin_defaults() -> dict[str, Any]:
    return {
        "enabled": True,
        "complexity": {
            "simple": {"max_query_length": 80, "path": "simple", "max_output_chars": 800},
            "medium": {"max_query_length": 200, "path": "simple", "max_output_chars": 2000},
            "complex": {
                "min_query_length": 200,
                "path": "company",
                "keywords": [],
                "max_output_chars": 4000,
            },
        },
        "stage_models": {
            "simple": {"generate": "qwen3.8-flash", "evaluate": "qwen3.8-flash", "reflect": "deepseek-v4-flash-0731"},
            "medium": {"generate": "qwen3.7-plus", "evaluate": "qwen3.8-flash", "reflect": "deepseek-v4-flash-0731"},
            "complex": {
                "generate": "qwen3.8-max",
                "evaluate": "qwen3.7-plus",
                "reflect": "qwen3.8-max",
            },
        },
        "models": {},
    }


def reload_cost_speed() -> dict[str, Any]:
    """熱重載配置（修改 JSON 後無需重啟進程）。"""
    global _config_cache, _config_mtime
    _config_cache = None
    _config_mtime = 0.0
    _reset_keyword_pattern()
    return cost_speed_status()


def _reset_keyword_pattern() -> None:
    global _COMPLEX_KEYWORDS_RE
    _COMPLEX_KEYWORDS_RE = None


def cost_speed_enabled() -> bool:
    if os.getenv("EVOL_COST_SPEED_ENABLED", "").lower() in {"0", "false", "no"}:
        return False
    cfg = _load_raw_config()
    return bool(cfg.get("enabled", True))


def _complex_keywords_pattern() -> re.Pattern[str] | None:
    global _COMPLEX_KEYWORDS_RE
    if _COMPLEX_KEYWORDS_RE is not None:
        return _COMPLEX_KEYWORDS_RE
    keywords = (
        _load_raw_config()
        .get("complexity", {})
        .get("complex", {})
        .get("keywords", [])
    )
    if not keywords:
        return None
    escaped = [re.escape(str(k)) for k in keywords if str(k).strip()]
    if not escaped:
        return None
    _COMPLEX_KEYWORDS_RE = re.compile("|".join(escaped), re.IGNORECASE)
    return _COMPLEX_KEYWORDS_RE


def classify_task_complexity(query: str) -> TaskComplexity:
    """依查詢長度與關鍵詞分類任務複雜度。"""
    text = (query or "").strip()
    cfg = _load_raw_config().get("complexity", {})
    complex_cfg = cfg.get("complex", {})
    simple_cfg = cfg.get("simple", {})

    min_complex_len = int(complex_cfg.get("min_query_length") or 200)
    max_simple_len = int(simple_cfg.get("max_query_length") or 80)

    pattern = _complex_keywords_pattern()
    if pattern and pattern.search(text):
        return "complex"
    if len(text) >= min_complex_len:
        return "complex"
    if len(text) <= max_simple_len:
        return "simple"
    return "medium"


def resolve_path_for_complexity(complexity: TaskComplexity) -> RoutePath:
    """依複雜度決定走 simple 生成或 company 運行時。"""
    cfg = _load_raw_config().get("complexity", {}).get(complexity, {})
    path = str(cfg.get("path") or ("company" if complexity == "complex" else "simple"))
    return "company" if path == "company" else "simple"


def max_output_chars_for_complexity(complexity: TaskComplexity) -> int:
    """依複雜度解析輸出長度上限（字符數），供長度守門節點使用。"""
    cfg = _load_raw_config().get("complexity", {}).get(complexity, {})
    fallback = _DEFAULT_MAX_OUTPUT_CHARS.get(complexity, 4000)
    try:
        value = int(cfg.get("max_output_chars") or 0)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def resolve_cost_speed_model(
    complexity: TaskComplexity,
    stage: str,
    fallback: str,
) -> str:
    """依複雜度與環節解析模型，不在池內時回退 fallback。"""
    if not cost_speed_enabled():
        return fallback
    stage_models = _load_raw_config().get("stage_models", {})
    by_complexity = stage_models.get(complexity, {})
    if not isinstance(by_complexity, dict):
        return fallback
    preferred = str(by_complexity.get(stage) or "").strip()
    if not preferred:
        return fallback
    clamped = clamp_model(preferred)
    if clamped != preferred:
        logger.debug(
            "cost_speed 模型 %s 不在可用池，改用 %s（complexity=%s stage=%s）",
            preferred,
            clamped,
            complexity,
            stage,
        )
    return clamped


def model_profiles() -> dict[str, dict[str, Any]]:
    """模型成本 / 速度評分表（供監控面板）。"""
    raw = _load_raw_config().get("models", {})
    if not isinstance(raw, dict):
        return {}
    return {str(k): dict(v) if isinstance(v, dict) else {} for k, v in raw.items()}


def cost_speed_status() -> dict[str, Any]:
    """監控用狀態快照。"""
    cfg = _load_raw_config()
    path = _config_path()
    samples = {
        "simple": classify_task_complexity("什麼是 Python？"),
        "medium": classify_task_complexity("請解釋 Python 裝飾器的工作原理並舉例"),
        "complex": classify_task_complexity("請設計並實現一個完整的微服務系統架構"),
    }
    routing_preview = {
        level: {
            "path": resolve_path_for_complexity(level),  # type: ignore[arg-type]
            "generate_model": resolve_cost_speed_model(
                level,  # type: ignore[arg-type]
                "generate",
                "—",
            ),
        }
        for level in ("simple", "medium", "complex")
    }
    return {
        "enabled": cost_speed_enabled(),
        "config_path": str(path),
        "config_exists": path.exists(),
        "samples": samples,
        "routing_preview": routing_preview,
        "model_profiles": model_profiles(),
        "stage_models": cfg.get("stage_models", {}),
    }
