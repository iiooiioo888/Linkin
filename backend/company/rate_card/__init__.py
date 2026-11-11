"""模型公開價卡：輸入／輸出之外的收費項。

金額單位預設 USD / 1M tokens；搜尋、工具、圖像生成等以每次／每千次計。
實際帳單以供應商為準，此處供路由、預算估算與前端目錄顯示。

套件化：本模組已拆為 backend/company/rate_card/ 套件，公開 import 路徑不變。
fields／cards／parsing／service 各自持有領域內容，本 __init__.py 只做 re-export；費率數字與 model id 逐字保留。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .cards import (
    _DEFAULT_RATE_CARDS,
    _card,
    _empty_card,
)
from .fields import (
    RATE_FIELD_LABELS,
    RATE_FIELD_SCALE,
    RATE_FIELD_UNITS,
    RATE_FIELDS,
)
from .parsing import (
    _field_meta,
    _load_rate_cards,
    _parse_card,
    logger,
)
from .service import (
    _cards,
    estimate_usage_cost,
    get_model_costs,
    get_model_rate_cards,
    public_rate_cards,
    rate_card_for,
    reload_model_costs,
)

__all__ = [
    "RATE_FIELDS",
    "RATE_FIELD_LABELS",
    "RATE_FIELD_SCALE",
    "RATE_FIELD_UNITS",
    "_DEFAULT_RATE_CARDS",
    "Any",
    "Path",
    "_card",
    "_cards",
    "_empty_card",
    "_field_meta",
    "_load_rate_cards",
    "_parse_card",
    "estimate_usage_cost",
    "get_model_costs",
    "get_model_rate_cards",
    "json",
    "logger",
    "logging",
    "os",
    "public_rate_cards",
    "rate_card_for",
    "reload_model_costs",
]

# 只保留原單檔模組的介面：移除 import 子模組時自動掛在套件上的屬性，
# 讓 dir(backend.company.rate_card) 的公開名稱與原模組一致（17 個）。
for _submodule in (
    "cards",
    "fields",
    "parsing",
    "service",
):
    globals().pop(_submodule, None)
del _submodule

