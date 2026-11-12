"""原子執行者常數與規則 regex：憲法／任務層標記、阻塞類型、護欄預算與檢查樣式。"""

from __future__ import annotations

import re

CONSTITUTION_MARKER = "[憲法層 - 唯讀區塊]"
TASK_LAYER_MARKER = "[任務層 - 由 L3 動態注入的內容]"

BLOCKER_INPUT = "資料缺失"
BLOCKER_TOOL = "工具不足"
BLOCKER_CRITERIA = "標準模糊"
BLOCKER_CAPACITY = "容量矛盾"
BLOCKER_CONSTRAINT = "約束衝突"
BLOCKER_TYPES = (
    BLOCKER_INPUT,
    BLOCKER_TOOL,
    BLOCKER_CRITERIA,
    BLOCKER_CAPACITY,
    BLOCKER_CONSTRAINT,
)

GRILL_TARGET_L3 = "L3_Commander"
GRILL_TARGET_L4 = "L4_Planner"
GRILL_TARGET_L5 = "L5_User"

DEFAULT_MAX_ITERATIONS = 2
DEFAULT_TOKEN_BUDGET = 2000
MIN_RETRY_ITERATIONS = 2
MIN_TOKEN_BUDGET = 400

_EMPTY_REFS = frozenset(
    {"", "null", "none", "nil", "undefined", "n/a", "na", "tbd", "todo", "-", "—"}
)
_SUBJECTIVE_ONLY = re.compile(
    r"^(盡量完美|盡量做好|盡力|高品質|更好|優化一下|盡可能好|完美|"
    r"as good as possible|high quality|best effort)$",
    re.IGNORECASE,
)
_MEASURABLE = re.compile(
    r"(\d+|json|csv|key|鍵|欄|列|行|字|char|token|包含|不得|必須|"
    r"schema|list\[|dict\[|通過|失敗|空值|來源|引用)",
    re.IGNORECASE,
)
_LARGE_INPUT = re.compile(
    r"(\d{2,}\s*頁|100\s*頁|長文|全書|完整報告|完整論文|完整手冊)",
    re.IGNORECASE,
)
_TINY_OUTPUT = re.compile(
    r"(max\s*50|最多\s*50|50\s*字|≤\s*50|<=\s*50|plain text \(max 50)",
    re.IGNORECASE,
)
_GRILL_JSON = re.compile(
    r"\{[^{}]*\"type\"\s*:\s*\"(?:GRILL|ESCALATE)\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)
_FAILED_JSON = re.compile(
    r"\{[^{}]*\"status\"\s*:\s*\"FAILED\"[^{}]*\}",
    re.DOTALL | re.IGNORECASE,
)
