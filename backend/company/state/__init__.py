"""公司運行時狀態模型。

定義公司配置、角色、工作項、預算追蹤等核心資料結構。
所有模型均為 dataclass，方便序列化與測試隔離。

本檔案已於第十輪重構拆為套件：對外仍以
from backend.company.state import RoleType, CompanyConfig, WorkItem 等名稱匯入；
實作分散在 enums／role_types／role／budget／models／config／run_state 等模組，內容與行為逐字不變。
"""

from __future__ import annotations

# 以下名稱是重構前模組的順帶轉出（dir() 公開集合的一部分），保留以維持相容
import uuid  # noqa: F401
from dataclasses import dataclass, field  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from enum import Enum  # noqa: F401
from typing import Any  # noqa: F401

from backend.company.prompts import PromptConfig  # noqa: F401

# 舊模組私有 helper（非公開 API，但維持頂層名稱相容）
from .budget import (
    BudgetConfig,  # noqa: F401
    _default_tier_models,  # noqa: F401
)
from .config import CompanyConfig  # noqa: F401
from .enums import VALID_TRANSITIONS, BudgetTier, Priority, WorkItemStatus  # noqa: F401
from .models import RetryConfig, WorkItem  # noqa: F401
from .role import RoleDefinition, assignee_token  # noqa: F401
from .role_types import ROLE_CATEGORY_MAP, ROLE_LEVEL, RoleCategory, RoleType  # noqa: F401
from .run_state import CompanyRunState  # noqa: F401

# 子模組名稱不留在套件公開命名空間（維持重構前 dir() 的公開名稱集合）
for _submodule in (
    "budget", "config", "enums", "models", "role", "role_types", "run_state"
):
    globals().pop(_submodule, None)
del _submodule
