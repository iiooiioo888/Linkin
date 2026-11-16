"""統一執行路徑解析（Task API、SSE、LangGraph route_by_complexity 共用）。

執行時的優先序：
  1. 管理員關鍵詞鎖定（force_company_keywords）→ company，reason=admin_lock
  2. 用戶本次明示 simple / company → 直接採用，reason=user_explicit
  3. 租戶默認 → 採用，reason=user_default（入口仍可切）
  4. 沒有默認 → simple，reason=fallback

系統建議沿用原 auto 規則，只當預選與理由，不自動執行：
  1. 工業關鍵詞 → company（任務經理分析；預設模板 industrial_ops 席位）
  2. 靈境複雜任務 → company
  3. cost_speed 分類與 path 配置 → company | simple
  4. 關鍵詞／長度規則 → company | simple
``strategy="auto"`` 僅保留給圖與舊內部呼叫，已棄用，不得作為 API 默認。
"""

from __future__ import annotations

import logging
import re
import warnings
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

_COMPANY_KEYWORDS = re.compile(
    r"(开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|"
    r"多步|架構|架构|重构|遷移|迁移|deploy|develop|build|implement|design|"
    r"create|refactor|migrate|project|system|application|"
    r"故事|小說|小说|撰寫|撰写|長文|长文|\d+\s*字)",
    re.IGNORECASE,
)

_OPC_KEYWORDS = re.compile(
    r"(感測|传感|溫度|温度|壓力|压力|流量|閥門|阀门|閥|阀|馬達|马达|電機|电机|"
    r"設備|设备|製程|制程|工業|工业|產線|产线|opc|sensor|temperature|pressure|"
    r"flow|valve|motor|equipment|industrial|plc)",
    re.IGNORECASE,
)

_COMPLEX_QUERY_LENGTH = 200


def _complex_query_length() -> int:
    try:
        from backend.core.routing_feedback import adaptive_length_threshold

        return adaptive_length_threshold(_COMPLEX_QUERY_LENGTH)
    except Exception:
        return _COMPLEX_QUERY_LENGTH


def is_complex_task(query: str, *, use_routing_feedback: bool = True) -> bool:
    """規則判斷任務是否複雜（需要公司運行時）。"""
    threshold = (
        _complex_query_length()
        if use_routing_feedback
        else _COMPLEX_QUERY_LENGTH
    )
    if len(query) >= threshold:
        return True
    return bool(_COMPANY_KEYWORDS.search(query))


def needs_opc_context(query: str) -> bool:
    """判斷任務是否要注入 OPC 讀數，並預設改用工業運維席。"""
    return bool(_OPC_KEYWORDS.search(query or ""))


def resolve_company_template(query: str, template: str | None = None) -> str:
    """預設 quick_task 遇上工業查詢時改為工業運維席。

    分析仍由任務經理做。呼叫端已指定其他模板時保留。
    """
    requested = (template or "quick_task").strip() or "quick_task"
    if requested == "quick_task" and needs_opc_context(query or ""):
        return "industrial_ops"
    return requested


ExecutionPath = Literal["simple", "company", "opc"]
PathName = Literal["simple", "company"]
DecisionSource = Literal["user_explicit", "user_default", "admin_lock", "fallback"]
EXTERNAL_STRATEGIES = ("simple", "company", "user_default", "suggest_only")

_AUTO_DEPRECATION = (
    "execution_strategy='auto' 已棄用，不得作為 API 默認；只保留給內部圖相容。"
)
_auto_warned = False


class PathSuggestion:
    """建議或已決定的路徑。與路徑字串相等，方便舊呼叫比對。"""

    __slots__ = ("locked", "reason", "suggested")

    def __init__(self, suggested: PathName, reason: str, locked: bool = False) -> None:
        if suggested not in ("simple", "company"):
            raise ValueError(f"非法路徑：{suggested}")
        self.suggested: PathName = suggested
        self.reason = reason
        self.locked = bool(locked)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, PathSuggestion):
            return (
                self.suggested == other.suggested
                and self.reason == other.reason
                and self.locked == other.locked
            )
        if isinstance(other, str):
            return self.suggested == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.suggested, self.reason, self.locked))

    def __str__(self) -> str:
        return self.suggested

    def __repr__(self) -> str:
        return (
            f"PathSuggestion(suggested={self.suggested!r}, reason={self.reason!r}, "
            f"locked={self.locked!r})"
        )

    def as_dict(self) -> dict[str, object]:
        return {"suggested": self.suggested, "reason": self.reason, "locked": self.locked}


class ChoiceRequiredError(Exception):
    """缺少執行策略，而且租戶沒有默認。"""


class ChoiceForbiddenError(Exception):
    """租戶不允許使用者自選路徑。"""


@dataclass(frozen=True)
class TaskPathDecision:
    """POST /tasks 的決定。``created`` 為假時只回建議、不建任務。"""

    suggested: PathName
    reason: str
    locked: bool
    decision_source: DecisionSource | None
    using_default: bool
    can_switch: bool
    created: bool = True


_REASON_TEXT = {
    "user_explicit": "這次由你指定路徑",
    "user_default": "沿用已儲存的默認路徑，送出前仍可改",
    "admin_lock": "管理員鎖定：查詢命中強制公司關鍵詞，不能改走簡單生成",
    "fallback": "沒有可用默認，改走簡單生成",
    "opc_keyword": "內容像工業查詢，建議交給公司分析",
    "company_keyword": "內容像多步建置，建議交給公司分析",
    "length_over_threshold": "內容較長，建議交給公司分析",
    "linkin_complex": "靈境任務較完整，建議交給公司分析",
    "cost_speed": "依成本速度配置，建議公司分析",
    "rule_company": "規則判斷建議公司分析",
    "simple": "看起來一次生成就夠",
}


def reason_text(code: str) -> str:
    return _REASON_TEXT.get(code, code)


def keywords_force_company(query: str, keywords: tuple[str, ...] | list[str]) -> bool:
    text = (query or "").lower()
    for raw in keywords:
        token = str(raw or "").strip().lower()
        if token and token in text:
            return True
    return False


def _warn_auto_deprecated() -> None:
    global _auto_warned
    if _auto_warned:
        return
    _auto_warned = True
    warnings.warn(_AUTO_DEPRECATION, DeprecationWarning, stacklevel=3)
    logger.warning(_AUTO_DEPRECATION)


def suggest_execution_path(
    query: str,
    *,
    task_complexity: str | None = None,
    config: object | None = None,
) -> PathSuggestion:
    """原 auto 規則。只產生預選與理由，呼叫端不得據此直接執行。"""
    from backend.core.execution_path_config import ExecutionPathConfig, load_execution_path_config

    cfg = config if isinstance(config, ExecutionPathConfig) else load_execution_path_config()
    text = query or ""
    if keywords_force_company(text, cfg.force_company_keywords):
        logger.debug("execution_path: admin_lock → company")
        return PathSuggestion("company", "admin_lock", True)

    if needs_opc_context(text):
        logger.debug("execution_path: industrial suggestion → company")
        return PathSuggestion("company", "opc_keyword", False)

    try:
        from backend.linkin.pipeline import is_linkin_complex_task

        if is_linkin_complex_task(text):
            logger.debug("execution_path: linkin complex suggestion → company")
            return PathSuggestion("company", "linkin_complex", False)
    except Exception as exc:
        logger.debug("execution_path: linkin 判斷略過：%s", exc)

    try:
        from backend.core.cost_speed_router import (
            classify_task_complexity,
            cost_speed_enabled,
            resolve_path_for_complexity,
        )

        if cost_speed_enabled():
            level = task_complexity or classify_task_complexity(text)
            path = resolve_path_for_complexity(level)  # type: ignore[arg-type]
            if path == "company":
                logger.debug("execution_path: cost_speed %s suggestion → company", level)
                return PathSuggestion("company", "cost_speed", False)
            return PathSuggestion("simple", "simple", False)
    except Exception as exc:
        logger.warning("execution_path: cost_speed 失敗，回退規則：%s", exc)

    if is_complex_task(text):
        if len(text) >= _complex_query_length():
            return PathSuggestion("company", "length_over_threshold", False)
        if _COMPANY_KEYWORDS.search(text):
            return PathSuggestion("company", "company_keyword", False)
        return PathSuggestion("company", "rule_company", False)
    return PathSuggestion("simple", "simple", False)


def resolve_execution_path(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
    user_choice: PathName | None = None,
    config: object | None = None,
) -> PathSuggestion:
    """解析查詢應走的執行路徑。

    ``user_choice`` 非空且未被管理員鎖定覆蓋時，直接返回該路徑。
    ``strategy="auto"`` 已棄用：只供內部圖相容，回傳建議路徑，不得當 API 默認。
    """
    from backend.core.execution_path_config import ExecutionPathConfig, load_execution_path_config

    cfg = config if isinstance(config, ExecutionPathConfig) else load_execution_path_config()
    text = query or ""
    if keywords_force_company(text, cfg.force_company_keywords):
        return PathSuggestion("company", "admin_lock", True)

    choice: PathName | None = user_choice if user_choice in ("simple", "company") else None
    strat = (strategy or "auto").strip().lower()
    if choice is None and strat in ("simple", "company"):
        choice = strat  # type: ignore[assignment]
    if choice in ("simple", "company"):
        return PathSuggestion(choice, "user_explicit", False)

    if strat == "user_default":
        if cfg.default_execution_strategy in ("simple", "company"):
            return PathSuggestion(cfg.default_execution_strategy, "user_default", False)
        return PathSuggestion("simple", "fallback", False)

    if strat == "suggest_only":
        return suggest_execution_path(text, task_complexity=task_complexity, config=cfg)

    if strat == "auto":
        _warn_auto_deprecated()
        return suggest_execution_path(text, task_complexity=task_complexity, config=cfg)

    return PathSuggestion("simple", "fallback", False)


def normalize_external_strategy(raw: str | None) -> str | None:
    """對外策略。``auto`` 與未知值拒絕。空白視為未提供。"""
    if raw is None:
        return None
    text = raw.strip().lower()
    if not text:
        return None
    if text == "auto":
        raise ValueError("auto")
    if text not in EXTERNAL_STRATEGIES:
        raise ValueError(text)
    return text


def decide_task_execution(
    query: str,
    strategy: str | None,
    *,
    config: object | None = None,
) -> TaskPathDecision:
    """POST /tasks 的決定。建議不執行；缺策略且無默認時丟 ChoiceRequiredError。"""
    from backend.core.execution_path_config import ExecutionPathConfig, load_execution_path_config

    cfg = config if isinstance(config, ExecutionPathConfig) else load_execution_path_config()
    suggestion = suggest_execution_path(query, config=cfg)
    if strategy == "suggest_only":
        return TaskPathDecision(
            suggested=suggestion.suggested,
            reason=suggestion.reason,
            locked=suggestion.locked,
            decision_source=None,
            using_default=False,
            can_switch=not suggestion.locked and cfg.allow_user_path_choice,
            created=False,
        )
    if suggestion.locked:
        return TaskPathDecision(
            suggested="company",
            reason="admin_lock",
            locked=True,
            decision_source="admin_lock",
            using_default=False,
            can_switch=False,
            created=True,
        )
    if strategy in ("simple", "company"):
        if not cfg.allow_user_path_choice:
            raise ChoiceForbiddenError("此租戶不允許自選執行路徑")
        return TaskPathDecision(
            suggested=strategy,  # type: ignore[arg-type]
            reason="user_explicit",
            locked=False,
            decision_source="user_explicit",
            using_default=False,
            can_switch=True,
            created=True,
        )
    if cfg.default_execution_strategy in ("simple", "company"):
        return TaskPathDecision(
            suggested=cfg.default_execution_strategy,
            reason="user_default",
            locked=False,
            decision_source="user_default",
            using_default=True,
            can_switch=cfg.allow_user_path_choice,
            created=True,
        )
    if strategy is None:
        raise ChoiceRequiredError(
            "請選擇執行路徑：simple（簡單生成）或 company（公司分析）。系統不會自動執行。"
        )
    return TaskPathDecision(
        suggested="simple",
        reason="fallback",
        locked=False,
        decision_source="fallback",
        using_default=False,
        can_switch=cfg.allow_user_path_choice,
        created=True,
    )


def route_by_complexity_target(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
    user_choice: PathName | None = None,
) -> Literal["run_company", "generate_initial_answer"]:
    """LangGraph 條件邊名稱。"""
    path = resolve_execution_path(
        query,
        strategy,
        task_complexity=task_complexity,
        user_choice=user_choice,
    )
    if path.suggested == "company":
        return "run_company"
    return "generate_initial_answer"


def chat_stream_uses_company_sse(
    query: str,
    strategy: str = "auto",
    *,
    task_complexity: str | None = None,
    user_choice: PathName | None = None,
) -> bool:
    """SSE /chat/stream 是否走公司運行時串流（不含 OPC 六級）。"""
    return (
        resolve_execution_path(
            query,
            strategy,
            task_complexity=task_complexity,
            user_choice=user_choice,
        ).suggested
        == "company"
    )
