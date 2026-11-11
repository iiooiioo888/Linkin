"""Requirement Auditor 的門檻、維度標籤、階段標籤與判定用正則（自 backend.services.auditor 抽出）。"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("backend.services.auditor")

AUDITOR_DIM_THRESHOLD = 90.0
MAX_PHASE_ROUNDS = 3
MAX_AUDITOR_ROUNDS = 10
CONFIDENCE_THRESHOLD = 0.90

DIM_KEYS = ("specificity", "boundary", "constraints", "risk", "success")
DIM_LABELS = {
    "specificity": "目標具體性",
    "boundary": "邊界清晰度",
    "constraints": "約束量化度",
    "risk": "風險感知度",
    "success": "成功定義",
}
PHASE_LABELS = {
    1: "Phase 1 基礎錨定",
    2: "Phase 2 量化絞殺",
    3: "Phase 3 對抗性壓力測試",
    4: "Phase 4 語義鎖定",
}

_VAGUE = re.compile(r"(大概|盡量|尽量|好一點|好一点|隨便|随便|看看|差不多|或許|或许|可能吧)")
_OVER_AUTH_PHRASE = re.compile(
    r"(你看著辦|你看着办|你是 AI 你應該比我懂|你是AI你應該比我懂|你應該比我懂|你应该比我懂)"
)
_QUANT = re.compile(
    r"(\d+(\.\d+)?\s*(%|％|小時|小时|分鐘|分钟|天|週|周|萬|万|元|塊|块|人)|"
    r"\d{4}-\d{2}-\d{2})"
)
_METRIC_WORD = re.compile(
    r"(gmv|kpi|roi|復購|复购|轉化|转化|誤報|误报|準確|准确|預算|预算)",
    re.IGNORECASE,
)
_RATE_PAIR = re.compile(r"(\d+(?:\.\d+)?)\s*%[^%\n]{0,32}(\d+(?:\.\d+)?)\s*%")
_MONEY = re.compile(r"(\d+(?:\.\d+)?)\s*(萬|万|元|塊|块)")
_REVIEW_GATE = re.compile(r"(人工審核|人工审核|停止推播|人工確認|人工确认)")
_QUALITY_BOUND = re.compile(r"(品質不可|质量不可|不可降|不得降|絕對不|绝对不)")
_SUBJECT = re.compile(r"(用戶|用户|客群|受眾|受众|賣家|卖家|粉絲|粉丝|員工|员工|客戶|客户|終端|终端|老闆|老板|發起人|发起人)")
_ACTION = re.compile(
    r"(生成|壓縮|压缩|提升|預警|预警|調價|调价|產出|产出|交付|盯盤|盯盘|審核|审核|追蹤|追踪)"
)
_BEFORE_AFTER = re.compile(r"(目前|現狀|现状|介入前|目標|目标|壓縮至|压缩至|從.{0,12}到|提升到)")
_BOUNDARY = re.compile(
    r"(不做|不包含|不使用|不開發|不开发|排除|絕對不|绝对不|禁止|只做|必須|必须|先做|"
    r"人工審核|人工审核|停止推播)"
)
_BUDGET = re.compile(r"(預算|预算|萬|万|USD|usd|新台幣|新台币|\d+\s*(元|塊|块))")
_TIME = re.compile(r"(時程|时程|期限|deadline|週內|周内|天內|天内|\d{4}-\d{2}-\d{2}|上線|上线)")
_RESOURCE = re.compile(
    r"(人力|幾人|几人|Python|PostgreSQL|API|Excel|Prototype|既有|資料庫|数据库|Line Notify)"
)
_TRADEOFF = re.compile(r"(砍功能|延後|延后|借貸|借贷|犧牲|牺牲|範圍|范围|時程|时程|成本|優先|优先)")
_RISK = re.compile(r"(備案|备案|失敗|失败|風險|风险|斷了|断了|退粉|誤報|误报|停損|停损|降級|降级)")
_FALLBACK = re.compile(r"(人工確認|人工确认|人工審核|人工审核|CSV|手動|手动|停止推播|按下停止)")
_SUCCESS = re.compile(
    r"(準確率|准确率|誤報率|误报率|復購率|复购率|小時|小时|分鐘|分钟|不得低於|不得低于|"
    r"Excel|Prototype|報表|报表|JSON|備忘錄|备忘录|可點擊|可点击)"
)
_CONFIRM = re.compile(r"^(確認|确认|確認無誤|确认无误|確認鎖定|确认锁定|同意|無誤|无误|作為最終|作为最终)")
_UNLIMITED_BUDGET = re.compile(r"(預算無限|预算无限|不限預算|不限预算|多少錢都行|多少钱都行)")
_FREE_OSS = re.compile(r"(開源免費|开源免费|必須免費|必须免费|零成本|不能花錢|不能花钱)")
_COMPLEX = re.compile(
    r"(开发|設計|设计|构建|實現|实现|建立|打造|完整|系統|系统|專案|项目|"
    r"多步|架構|架构|提升|優化|优化|策略|報告|报告|develop|build|implement|"
    r"design|create|project|system|管粉|自動|自动)",
    re.IGNORECASE,
)
_VAGUE_VERB_PRIORITY = (
    "管粉絲",
    "管粉丝",
    "自動管",
    "自动管",
    "幫我管",
    "帮我管",
    "管粉",
    "提升效率",
    "優化一下",
    "优化一下",
    "弄一個",
    "弄一个",
    "搞一個",
    "搞一个",
)
_FAN_KEYS = (
    "管粉絲",
    "管粉丝",
    "管粉",
    "粉絲",
    "粉丝",
    "自動管",
    "自动管",
    "幫我管",
    "帮我管",
)
_SOFT_GOAL = re.compile(
    r"(更黏|黏我|多買|多买|更好|提升效率|優化|优化|改善|智慧|智能|管粉|隨便|随便|看看)"
)
_FAN_METRIC = re.compile(r"(復購|复购|回購|回购)")
_FAN_COST = re.compile(r"(單粉|单粉|每個新粉|每个新粉|行銷成本|营销成本|\d+\s*(元|塊|块))")
