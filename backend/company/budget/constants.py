"""公司預算的 window／forecast 常數與 logger（自 backend.company.budget 抽出）。"""

from __future__ import annotations

import logging

logger = logging.getLogger("backend.company.budget")


DEFAULT_HISTORY_WINDOW_DAYS = 7
DEFAULT_FORECAST_WINDOW_DAYS = 30
MIN_DATA_POINTS_FOR_FORECAST = 3
