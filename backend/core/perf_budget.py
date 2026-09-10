"""效能預算（TODO §7.2／C-PERF-001）。

預設 P95 上限（可配置）：

| 動作 | 預設 P95 |
| --- | --- |
| L0 `/refresh` | 3s |
| 插件啟用／停用 API | 2s |
| 編譯管線（stub） | 5s |
| 審計（不含 LLM） | 1s |

實作以 stub 時鐘／假資料驗證上限邏輯；不依賴真實 I/O。
超限回傳可觀測錯誤碼 ``ERR_PERF_BUDGET_EXCEEDED``，不靜默吞掉。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

ERR_PERF_BUDGET_EXCEEDED = "ERR_PERF_BUDGET_EXCEEDED"

# 預設 P95（秒）— 寫死對齊 TODO §7.2
DEFAULT_P95_SECONDS: dict[str, float] = {
    "l0_refresh": 3.0,
    "plugin_toggle": 2.0,
    "compile_pipeline_stub": 5.0,
    "audit_no_llm": 1.0,
}


@dataclass(frozen=True)
class PerfBudget:
    """單一動作的 P95 上限（秒）。"""

    action: str
    p95_seconds: float

    def exceeded(self, elapsed_seconds: float) -> bool:
        return float(elapsed_seconds) > float(self.p95_seconds)


@dataclass(frozen=True)
class PerfCheckResult:
    ok: bool
    action: str
    elapsed_seconds: float
    budget_seconds: float
    error_code: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "elapsed_seconds": self.elapsed_seconds,
            "budget_seconds": self.budget_seconds,
            "error_code": self.error_code,
        }


def resolve_budget(
    action: str,
    *,
    overrides: Mapping[str, float] | None = None,
) -> PerfBudget:
    """解析動作預算；未知動作回退到最嚴的 1s，避免無上限。"""
    table = dict(DEFAULT_P95_SECONDS)
    if overrides:
        for key, value in overrides.items():
            if value is not None and float(value) > 0:
                table[str(key)] = float(value)
    seconds = table.get(action, 1.0)
    return PerfBudget(action=action, p95_seconds=float(seconds))


def check_elapsed(
    action: str,
    elapsed_seconds: float,
    *,
    overrides: Mapping[str, float] | None = None,
) -> PerfCheckResult:
    """檢查耗時是否超過 P95 預算（C-PERF-001）。"""
    budget = resolve_budget(action, overrides=overrides)
    elapsed = float(elapsed_seconds)
    if budget.exceeded(elapsed):
        return PerfCheckResult(
            ok=False,
            action=action,
            elapsed_seconds=elapsed,
            budget_seconds=budget.p95_seconds,
            error_code=ERR_PERF_BUDGET_EXCEEDED,
        )
    return PerfCheckResult(
        ok=True,
        action=action,
        elapsed_seconds=elapsed,
        budget_seconds=budget.p95_seconds,
    )


def assert_within_budget(
    action: str,
    elapsed_seconds: float,
    *,
    overrides: Mapping[str, float] | None = None,
) -> PerfCheckResult:
    """同 ``check_elapsed``；超限時拋 ``TimeoutError``（錯誤碼在 ``args[1]``）。"""
    result = check_elapsed(action, elapsed_seconds, overrides=overrides)
    if not result.ok:
        raise TimeoutError(
            f"{ERR_PERF_BUDGET_EXCEEDED}: {action} took {result.elapsed_seconds}s "
            f"> P95 {result.budget_seconds}s",
            ERR_PERF_BUDGET_EXCEEDED,
        )
    return result
