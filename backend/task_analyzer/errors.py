"""任務分析器錯誤碼（LINKIN-TA-001～008）。

目錄在載入時封存：代碼不可覆寫、不可另作他義、不可再登記。
本模組只定義錯誤碼，不裁決缺口、約束或預算。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType


class ErrorCodeReuseError(Exception):
    """錯誤碼已占用或目錄已封存，拒絕復用。"""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        message = f"錯誤碼 {code} 不可復用"
        if detail:
            message = f"{message}：{detail}"
        super().__init__(message)


class TaskAnalyzerError(Exception):
    """帶錯誤碼的分析器錯誤。``event`` 為本次審計事件，不寫資料庫。"""

    def __init__(self, spec: ErrorSpec, event: object | None = None) -> None:
        if not isinstance(spec, ErrorSpec):
            raise TypeError("spec 必須是 ErrorSpec")
        self.spec = spec
        self.code = spec.code
        self.description = spec.description
        self.trigger = spec.trigger
        self.recovery = spec.recovery
        self.event = event
        super().__init__(f"{spec.code}：{spec.description}")


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """單一代碼的穩定說明。``reusable`` 恆為 False。"""

    code: str
    description: str
    trigger: str
    recovery: str

    @property
    def reusable(self) -> bool:
        return False


TA_001 = "LINKIN-TA-001"
TA_002 = "LINKIN-TA-002"
TA_003 = "LINKIN-TA-003"
TA_004 = "LINKIN-TA-004"
TA_005 = "LINKIN-TA-005"
TA_006 = "LINKIN-TA-006"
TA_007 = "LINKIN-TA-007"
TA_008 = "LINKIN-TA-008"

_SPECS: tuple[ErrorSpec, ...] = (
    ErrorSpec(
        code=TA_001,
        description="任務識別無效，無法建立分析會話。",
        trigger="建立會話時任務識別缺失、不是字串，或去除空白後為空。",
        recovery="改用穩定且非空的任務識別，重新建立分析會話。",
    ),
    ErrorSpec(
        code=TA_002,
        description="解析階段失敗，未能形成可繼續發現的任務結構。",
        trigger="會話處於 PARSING，呼叫方以本碼標記解析失敗。",
        recovery="修正原始輸入後另開會話，自 RECEIVED 重新進入 PARSING。",
    ),
    ErrorSpec(
        code=TA_003,
        description="發現階段失敗，未能補齊後續判斷所需的上下文。",
        trigger="會話處於 DISCOVERING，呼叫方以本碼標記發現失敗。",
        recovery="補齊可發現的上下文後，自解析完成之處重新進入 DISCOVERING。",
    ),
    ErrorSpec(
        code=TA_004,
        description="缺口或追問無效，本輪無法形成可往下核對的內容。",
        trigger="會話處於 GAP_IDENTIFIED 或 ASKING，呼叫方以本碼標記缺口或追問無效。",
        recovery="寫明具體缺口或答覆，回到 GAP_IDENTIFIED 後再開下一輪 ASKING。",
    ),
    ErrorSpec(
        code=TA_005,
        description="約束檢查未通過，不能進入預算估算。",
        trigger="會話處於 CONSTRAINT_CHECKED，呼叫方以本碼標記約束未滿足。",
        recovery="調整約束或輸入並重新檢查；通過後才進入 BUDGET_ESTIMATING。",
    ),
    ErrorSpec(
        code=TA_006,
        description="預算估算失敗，得不出可決策的估算結果。",
        trigger="會話處於 BUDGET_ESTIMATING，呼叫方以本碼標記估算失敗。",
        recovery="補上可估算的預算輸入後，重新進入 BUDGET_ESTIMATING。",
    ),
    ErrorSpec(
        code=TA_007,
        description="非法狀態轉移。",
        trigger="要求的目標狀態不在目前狀態的允許後繼之中，或對終態再次轉移。",
        recovery="改走目前狀態允許的下一狀態；已進入終態時另開新的分析會話。",
    ),
    ErrorSpec(
        code=TA_008,
        description="分析階段逾時，會話進入 TIMEOUT。",
        trigger=(
            "PARSING 停留滿 30 秒、ASKING 單輪停留滿 24 小時，"
            "或 DISCOVERING／BUDGET_ESTIMATING 停留滿呼叫方傳入的秒數。"
        ),
        recovery="縮短該階段耗時，或提高 DISCOVERING／BUDGET 的逾時秒數後，另開分析會話。",
    ),
)


def _seal(specs: tuple[ErrorSpec, ...]) -> Mapping[str, ErrorSpec]:
    found: dict[str, ErrorSpec] = {}
    expected = tuple(f"LINKIN-TA-{index:03d}" for index in range(1, 9))
    for spec in specs:
        if spec.code in found:
            raise ErrorCodeReuseError(spec.code, "目錄內出現重複代碼")
        found[spec.code] = spec
    if tuple(found) != expected:
        raise ErrorCodeReuseError(
            ",".join(found),
            "錯誤碼必須恰好為 LINKIN-TA-001 到 LINKIN-TA-008",
        )
    return MappingProxyType(found)


CATALOG: Mapping[str, ErrorSpec] = _seal(_SPECS)


def get_spec(code: str) -> ErrorSpec:
    """依代碼取回封存規格。未知代碼拋 KeyError。"""
    try:
        return CATALOG[code]
    except KeyError:
        raise KeyError(f"未知錯誤碼：{code}") from None


def register_error_code(
    code: str,
    description: str,
    trigger: str,
    recovery: str,
) -> ErrorSpec:
    """拒絕任何再登記。參數保留規格形狀，但目錄已封存，呼叫必失敗。"""
    if code in CATALOG:
        raise ErrorCodeReuseError(code, "既有代碼禁止覆寫")
    raise ErrorCodeReuseError(code, "目錄已封存，禁止新增代碼")


__all__ = [
    "CATALOG",
    "TA_001",
    "TA_002",
    "TA_003",
    "TA_004",
    "TA_005",
    "TA_006",
    "TA_007",
    "TA_008",
    "ErrorCodeReuseError",
    "ErrorSpec",
    "TaskAnalyzerError",
    "get_spec",
    "register_error_code",
]
