"""任務拆分模板與關鍵詞對照（字句逐字保留；自 backend.company.prompts 抽出）。"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════════════
# 任務拆分模板（供 TEMPLATE 策略使用）
# ═══════════════════════════════════════════════════════════════

PAGE_DEV_TEMPLATE: list[dict[str, Any]] = [
    {
        "title": "UI 設計",
        "description": "設計頁面視覺佈局、線框圖、配色方案、元件設計稿",
        "assignee": "ui_designer",
        "depends_on": [],
        "complexity": "medium",
        "phase": 1,
    },
    {
        "title": "系統架構設計",
        "description": "設計系統架構、技術選型、API 設計原則、資料庫 schema",
        "assignee": "architect",
        "depends_on": [],
        "complexity": "high",
        "phase": 1,
    },
    {
        "title": "後端 API 開發",
        "description": "實作 RESTful API 端點、業務邏輯、資料庫操作、認證授權",
        "assignee": "backend_dev",
        "depends_on": [1],
        "complexity": "high",
        "phase": 1,
    },
    {
        "title": "CSS 樣式開發",
        "description": "根據 UI 設計稿實作樣式（Tailwind CSS），含 RWD 與動畫",
        "assignee": "css_dev",
        "depends_on": [0],
        "complexity": "medium",
        "phase": 2,
    },
    {
        "title": "JS 互動邏輯開發",
        "description": "實作前端互動邏輯、狀態管理、API 串接、路由配置",
        "assignee": "js_dev",
        "depends_on": [0, 2],
        "complexity": "high",
        "phase": 2,
    },
    {
        "title": "測試撰寫",
        "description": "撰寫單元測試、整合測試、E2E 測試，確保覆蓋率",
        "assignee": "tester",
        "depends_on": [3, 4],
        "complexity": "medium",
        "phase": 3,
    },
    {
        "title": "技術審查與整合",
        "description": "審查所有交付物品質，整合為最終產出",
        "assignee": "tech_lead",
        "depends_on": [5],
        "complexity": "medium",
        "phase": 4,
    },
]

GENERIC_DEV_TEMPLATE: list[dict[str, Any]] = [
    {
        "title": "需求分析",
        "description": "分析需求，產出規格文件",
        "assignee": "analyst",
        "depends_on": [],
        "complexity": "medium",
        "phase": 1,
    },
    {
        "title": "實作開發",
        "description": "根據規格實作核心功能",
        "assignee": "developer",
        "depends_on": [0],
        "complexity": "high",
        "phase": 2,
    },
    {
        "title": "測試驗證",
        "description": "測試功能完整性與正確性",
        "assignee": "tester",
        "depends_on": [1],
        "complexity": "medium",
        "phase": 3,
    },
    {
        "title": "審查與整合",
        "description": "審查所有交付物，整合最終產出",
        "assignee": "reviewer",
        "depends_on": [2],
        "complexity": "low",
        "phase": 4,
    },
]

RESEARCH_TEMPLATE: list[dict[str, Any]] = [
    {
        "title": "資料收集",
        "description": "收集相關資料、文獻、數據",
        "assignee": "analyst",
        "depends_on": [],
        "complexity": "medium",
        "phase": 1,
    },
    {
        "title": "分析與撰寫",
        "description": "分析資料，撰寫報告主體",
        "assignee": "analyst",
        "depends_on": [0],
        "complexity": "high",
        "phase": 2,
    },
    {
        "title": "審查與潤飾",
        "description": "審查報告品質，潤飾文字",
        "assignee": "reviewer",
        "depends_on": [1],
        "complexity": "low",
        "phase": 3,
    },
]

TEMPLATE_KEYWORDS: dict[str, list[dict[str, Any]]] = {
    "page": PAGE_DEV_TEMPLATE,
    "頁面": PAGE_DEV_TEMPLATE,
    "ui": PAGE_DEV_TEMPLATE,
    "前端": PAGE_DEV_TEMPLATE,
    "frontend": PAGE_DEV_TEMPLATE,
    "web": PAGE_DEV_TEMPLATE,
    "網頁": PAGE_DEV_TEMPLATE,
    "網站": PAGE_DEV_TEMPLATE,
    "report": RESEARCH_TEMPLATE,
    "報告": RESEARCH_TEMPLATE,
    "research": RESEARCH_TEMPLATE,
    "研究": RESEARCH_TEMPLATE,
    "分析": RESEARCH_TEMPLATE,
    "develop": GENERIC_DEV_TEMPLATE,
    "開發": GENERIC_DEV_TEMPLATE,
    "api": GENERIC_DEV_TEMPLATE,
    "系統": GENERIC_DEV_TEMPLATE,
}
