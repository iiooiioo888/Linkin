"""執行流程 mixin（ExecutionMixin）：execute 主流程、執行-審查迴圈、MGP 裁決修補與作戰計畫建構。"""

from __future__ import annotations

from .loop import _ExecutionLoopMixin
from .mgp import _ExecutionMgpMixin
from .plan import _ExecutionPlanMixin
from .run import _ExecutionRunMixin


class ExecutionMixin(_ExecutionRunMixin, _ExecutionLoopMixin, _ExecutionMgpMixin, _ExecutionPlanMixin):
    """execute 主流程、執行-審查迴圈、MGP 裁決修補與作戰計畫建構。"""


__all__ = ["ExecutionMixin"]
