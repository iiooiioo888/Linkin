"""L0 三核管線（TODO §4.3／§4.4；契約 C-L0-001／C-L0-002／C-L0-003）。

在既有 ``l0.py`` 之上提供**可開關、可旁路、可觀測**的三核編排（視圖層，
不修改 ``l0.py`` 對外介面）：

- **C-L0-001**：預設串行 ``記憶整理 → 知識圖譜 → 態勢偏置``；任一核可旁路，
  旁路時下游拿**降級輸入**（空片段／空子圖／單位偏置）並寫入**路由原因碼**。
- **C-L0-002**：所有注入片段出管線前必經 :func:`redact` 脱敏
  （密鑰／憑證／未授權 PII 不得寫入注入片段）。
- **C-L0-003**：壓力指標**預設等權**歸一化（權重表可配置），並實際驅動
  **注入強度**（壓力越高、注入片段越少）——禁止死數字。

測試隔離：三核皆為可注入 callable，預設實作失敗時自動降級，不需真實 Chroma／LLM。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class CoreKind(str, Enum):
    MEMORY = "memory"   # 記憶整理
    GRAPH = "graph"     # 知識圖譜
    BIAS = "bias"       # 態勢偏置


# 管線順序（寫死，§4.3）：記憶整理 → 知識圖譜 → 態勢偏置
PIPELINE_ORDER: tuple[CoreKind, ...] = (CoreKind.MEMORY, CoreKind.GRAPH, CoreKind.BIAS)

# 路由原因碼（寫死，前後端共用）
REASON_OK = "ok"
REASON_CORE_DISABLED = "core_disabled"        # 核被開關旁路
REASON_CORE_FAILED = "core_failed"            # 核執行失敗 → 降級輸入
REASON_REDACTED = "redacted"                  # 片段命中脱敏規則被遮罩
REASON_PRESSURE_TRIMMED = "pressure_trimmed"  # 壓力驅動截斷注入

# 各核注入片段上限（strength=1.0 時）
_CORE_CAP: dict[CoreKind, int] = {
    CoreKind.MEMORY: 6,
    CoreKind.GRAPH: 4,
    CoreKind.BIAS: 2,
}


# ── C-L0-002：注入前脱敏 ──────────────────────────────────────
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"sk-[A-Za-z0-9_\-]{12,}",                    # OpenAI 風格金鑰
        r"AKIA[0-9A-Z]{16}",                          # AWS Access Key
        r"Bearer\s+[A-Za-z0-9_\-\.]{8,}",             # Bearer token
        r"(?:api[_-]?key|apikey)\s*[:=]\s*\S+",       # api_key=...
        r"(?:password|passwd|pwd)\s*[:=]\s*\S+",      # password=...
        r"(?:secret|token)\s*[:=]\s*\S+",             # secret=/token=...
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----",        # PEM 私鑰頭
    )
)
_PII_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",  # email
        r"(?<!\d)(?:09\d{8}|1[3-9]\d{9})(?!\d)",            # 手機（台灣／大陸）
    )
)
_MASK = "〔已遮罩〕"


def redact(text: str) -> tuple[str, bool]:
    """回傳 (脱敏後文字, 是否命中規則)。注入片段必經此函式。"""
    out = text or ""
    hit = False
    for pattern in (*_SECRET_PATTERNS, *_PII_PATTERNS):
        new = pattern.sub(_MASK, out)
        if new != out:
            hit = True
            out = new
    return out, hit


# ── C-L0-003：壓力等權歸一化 → 注入強度 ───────────────────────
# 壓力來源（§4.4）：佇列深度、錯誤率、預算緊張度、外部信號、外掛錯誤率
PRESSURE_SOURCES: tuple[str, ...] = (
    "queue_depth",
    "error_rate",
    "budget_strain",
    "external_signal",
    "plugin_error_rate",
)


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def default_pressure_weights() -> dict[str, float]:
    """預設**等權**（§4.4 寫死）；呼叫方可覆寫，歸一化由 compute_pressure 保證。"""
    return {name: 1.0 for name in PRESSURE_SOURCES}


def compute_pressure(
    sources: dict[str, float],
    weights: dict[str, float] | None = None,
) -> float:
    """加權歸一化壓力 ∈ [0,1]；未知來源忽略，權重全零視為等權。"""
    weights = dict(weights or default_pressure_weights())
    total_w = sum(max(0.0, float(weights.get(name, 0.0))) for name in PRESSURE_SOURCES)
    if total_w <= 0:
        weights = default_pressure_weights()
        total_w = float(len(PRESSURE_SOURCES))
    acc = sum(
        _clamp01(sources.get(name, 0.0)) * max(0.0, float(weights.get(name, 0.0)))
        for name in PRESSURE_SOURCES
    )
    return _clamp01(acc / total_w)


def injection_strength(pressure: float) -> float:
    """壓力 → 注入強度 ∈ [0.25, 1.0]（線性衰減；壓力 1 時保留 25% 下限）。"""
    return round(1.0 - 0.75 * _clamp01(pressure), 4)


# ── C-L0-001：三核管線 ────────────────────────────────────────
CoreFn = Callable[..., list[str]]


@dataclass(frozen=True)
class CoreResult:
    core: CoreKind
    fragments: tuple[str, ...] = ()
    bypassed: bool = False
    reason_code: str = REASON_OK


@dataclass(frozen=True)
class L0PipelineResult:
    cores: tuple[CoreResult, ...]
    fragments: tuple[str, ...]          # 已脱敏、已按壓力截斷的最終注入片段
    pressure: float
    strength: float
    snapshot_id: str = ""
    reason_codes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cores": [
                {
                    "core": c.core.value,
                    "fragments": list(c.fragments),
                    "bypassed": c.bypassed,
                    "reason_code": c.reason_code,
                }
                for c in self.cores
            ],
            "fragments": list(self.fragments),
            "pressure": self.pressure,
            "strength": self.strength,
            "snapshot_id": self.snapshot_id,
            "reason_codes": list(self.reason_codes),
        }


def _default_memory_core(query: str, **_kw: Any) -> list[str]:
    from backend.company.raho.l0 import traces_from_trees

    return [t.summary for t in traces_from_trees(query) if t.summary]


def _default_graph_core(query: str, **_kw: Any) -> list[str]:
    from backend.company.raho.l0 import match_knowledge

    return [k.content for k in match_knowledge(query) if k.content]


def _default_bias_core(query: str, **_kw: Any) -> list[str]:
    from backend.environment.global_monitor import snapshot as radar_snapshot

    bias = radar_snapshot().bias_instructions
    return [bias] if bias else []


_DEFAULT_CORES: dict[CoreKind, CoreFn] = {
    CoreKind.MEMORY: _default_memory_core,
    CoreKind.GRAPH: _default_graph_core,
    CoreKind.BIAS: _default_bias_core,
}


@dataclass
class L0Pipeline:
    """三核管線。``enabled`` 可單獨關閉任一核（旁路＋降級輸入＋原因碼）。"""

    cores: dict[CoreKind, CoreFn] = field(default_factory=lambda: dict(_DEFAULT_CORES))
    enabled: dict[CoreKind, bool] = field(
        default_factory=lambda: {kind: True for kind in PIPELINE_ORDER}
    )

    def run(
        self,
        query: str,
        *,
        pressure: float = 0.0,
        snapshot_id: str = "",
    ) -> L0PipelineResult:
        strength = injection_strength(pressure)
        results: list[CoreResult] = []
        reason_codes: list[str] = []
        upstream: dict[str, Any] = {"query": query, "pressure": pressure}
        final: list[str] = []

        for kind in PIPELINE_ORDER:
            cap = max(1, int(round(_CORE_CAP[kind] * strength)))
            if not self.enabled.get(kind, True):
                # 旁路：下游拿降級輸入（空片段），原因碼可觀測
                results.append(CoreResult(kind, (), bypassed=True, reason_code=REASON_CORE_DISABLED))
                reason_codes.append(f"{kind.value}:{REASON_CORE_DISABLED}")
                upstream[kind.value] = []
                continue
            try:
                raw = self.cores[kind](**upstream) or []
            except Exception:  # noqa: BLE001 - 核失敗不得拖垮注入，降級＋原因碼
                results.append(CoreResult(kind, (), bypassed=True, reason_code=REASON_CORE_FAILED))
                reason_codes.append(f"{kind.value}:{REASON_CORE_FAILED}")
                upstream[kind.value] = []
                continue
            cleaned: list[str] = []
            hit_redact = False
            for fragment in raw:
                text, hit = redact(str(fragment))
                hit_redact = hit_redact or hit
                if text.strip():
                    cleaned.append(text)
            if hit_redact:
                reason_codes.append(f"{kind.value}:{REASON_REDACTED}")
            if len(cleaned) > cap:
                cleaned = cleaned[:cap]
                reason_codes.append(f"{kind.value}:{REASON_PRESSURE_TRIMMED}")
            results.append(CoreResult(kind, tuple(cleaned)))
            upstream[kind.value] = cleaned
            final.extend(cleaned)

        return L0PipelineResult(
            cores=tuple(results),
            fragments=tuple(final),
            pressure=_clamp01(pressure),
            strength=strength,
            snapshot_id=snapshot_id,
            reason_codes=tuple(reason_codes),
        )


__all__ = [
    "CoreKind",
    "CoreResult",
    "L0Pipeline",
    "L0PipelineResult",
    "PIPELINE_ORDER",
    "PRESSURE_SOURCES",
    "REASON_CORE_DISABLED",
    "REASON_CORE_FAILED",
    "REASON_OK",
    "REASON_PRESSURE_TRIMMED",
    "REASON_REDACTED",
    "compute_pressure",
    "default_pressure_weights",
    "injection_strength",
    "redact",
]
