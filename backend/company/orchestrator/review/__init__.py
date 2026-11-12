"""審查整合 mixin（ReviewMixin）：L1 憲兵檢查、Reviewer 審查、退回重做、整合與任務經理終審。"""

from __future__ import annotations

from .final import _ReviewFinalMixin
from .item import _ReviewItemMixin
from .l1 import _ReviewL1Mixin
from .rework import _ReviewReworkMixin


class ReviewMixin(_ReviewL1Mixin, _ReviewItemMixin, _ReviewReworkMixin, _ReviewFinalMixin):
    """L1 憲兵檢查、Reviewer 審查、退回重做、整合與任務經理終審。"""


__all__ = ["ReviewMixin"]
