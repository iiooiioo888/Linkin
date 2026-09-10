"""小模型優先路由與升級上限（C-LLM-004／TODO §5.5）。

契約：
- 可程式化決策之外的生成，預設先走**小模型／本地端點**。
- 小模型輸出經**啟發式評估**；不達標才升級大模型。
- 升級有**次數上限**（預設每任務 2 次），且每次升級留**成本觀測記錄**。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

DEFAULT_ESCALATION_CAP = 2  # 每任務最多升級次數

REASON_SMALL_MODEL_OK = "small_model_ok"
REASON_ESCALATED = "escalated_to_large_model"
REASON_ESCALATION_CAP_REACHED = "escalation_cap_reached"

# ── 啟發式評估規則（可注入覆寫）──
_MIN_CHARS = 24                  # 過短視為不達標
_PLACEHOLDER_PAT = re.compile(r"(TODO|FIXME|抱歉|無法回答|I cannot|as an AI)", re.IGNORECASE)


def heuristic_score(text: str) -> tuple[bool, str]:
    """啟發式評估小模型輸出。

    Returns:
        (passed, reason)：passed=False 時 reason 為不達標原因。
    """
    body = (text or "").strip()
    if len(body) < _MIN_CHARS:
        return False, "too_short"
    if _PLACEHOLDER_PAT.search(body):
        return False, "placeholder_or_refusal"
    if body.count("\n") == 0 and len(body) > 400:
        return False, "unstructured_blob"
    return True, "ok"


@dataclass(frozen=True)
class EscalationEvent:
    task_id: str
    from_model: str
    to_model: str
    reason: str
    attempt: int


@dataclass
class SmallModelRouter:
    """小模型優先 + 啟發式升級 + 次數上限。

    ``cost_log`` 記錄每次升級（成本觀測）；``evaluator`` 可注入替換。
    """

    small_model: str = "local-small"
    large_model: str = "default-large"
    escalation_cap: int = DEFAULT_ESCALATION_CAP
    evaluator: callable = heuristic_score
    cost_log: list[EscalationEvent] = field(default_factory=list)
    _attempts: dict[str, int] = field(default_factory=dict)

    def remaining_attempts(self, task_id: str) -> int:
        return max(0, self.escalation_cap - self._attempts.get(task_id, 0))

    def route(self, task_id: str, small_output: str) -> dict:
        """評估小模型輸出並決定是否升級。

        Returns:
            dict: model（最終使用模型）、output 是否可用、reason_code、escalated。
        """
        passed, why = self.evaluator(small_output)
        if passed:
            return {
                "model": self.small_model,
                "usable": True,
                "reason_code": REASON_SMALL_MODEL_OK,
                "escalated": False,
            }
        if self.remaining_attempts(task_id) <= 0:
            logger.warning("任務 %s 升級次數耗盡（cap=%d）", task_id, self.escalation_cap)
            return {
                "model": self.small_model,
                "usable": False,
                "reason_code": REASON_ESCALATION_CAP_REACHED,
                "escalated": False,
            }
        attempt = self._attempts.get(task_id, 0) + 1
        self._attempts[task_id] = attempt
        self.cost_log.append(
            EscalationEvent(
                task_id=task_id,
                from_model=self.small_model,
                to_model=self.large_model,
                reason=why,
                attempt=attempt,
            )
        )
        return {
            "model": self.large_model,
            "usable": True,
            "reason_code": REASON_ESCALATED,
            "escalated": True,
            "attempt": attempt,
        }

    def reset_task(self, task_id: str) -> None:
        self._attempts.pop(task_id, None)
