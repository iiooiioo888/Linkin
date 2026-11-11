"""內建組織架構模板（自 backend.company.roles 抽出）。

create_*_team／create_full_company 等 CompanyConfig 建構與 BUILTIN_TEMPLATES。
"""

from __future__ import annotations

from backend.company.state import BudgetConfig, CompanyConfig, RoleType

from .definitions_engineering import (
    ROLE_BACKEND_DEV,
    ROLE_CSS_DEV,
    ROLE_JS_DEV,
    ROLE_SECURITY_ENG,
    ROLE_SRE,
    ROLE_TESTER,
    ROLE_UI_DESIGNER,
)
from .definitions_exec import (
    ROLE_COPY_EDITOR,
    ROLE_IOT_ENGINEER,
    ROLE_PLC_ENGINEER,
    ROLE_PORTFOLIO_MGR,
    ROLE_SENTIMENT_ANALYST,
)
from .definitions_leadership import (
    ROLE_ARCHITECT,
    ROLE_BACKEND_LEAD,
    ROLE_FRONTEND_LEAD,
    ROLE_MANAGER,
    ROLE_TECH_LEAD,
    ROLE_TEST_LEAD,
)
from .definitions_specialist import (
    ROLE_CREATIVE_LEAD,
    ROLE_FINANCE_LEAD,
    ROLE_INDUSTRIAL_LEAD,
    ROLE_OPC_ENGINEER,
    ROLE_QUANT_ANALYST,
    ROLE_STORY_WRITER,
    ROLE_TRANSLATOR,
)
from .definitions_support import (
    ROLE_ANALYST,
    ROLE_CONTENT_WRITER,
    ROLE_DEVELOPER,
    ROLE_MARKET_DATA_ENG,
    ROLE_NARRATIVE_EDITOR,
    ROLE_RESEARCHER,
    ROLE_REVIEWER,
    ROLE_RISK_ANALYST,
    ROLE_SYNTHESIZER,
)
from .templates import STANDARD_ROLES

# ═══════════════════════════════════════════════════════════════
# 內建組織架構模板
# ═══════════════════════════════════════════════════════════════

def create_page_dev_team() -> CompanyConfig:
    """頁面開發團隊：完整的層級分工。

    層級結構：
      MANAGER
      ├── TECH_LEAD
      │   ├── FRONTEND_LEAD
      │   │   ├── UI_DESIGNER    ← 線框圖、設計稿
      │   │   ├── CSS_DEV        ← 樣式、RWD、動畫
      │   │   └── JS_DEV         ← 互動邏輯、API 串接
      │   ├── BACKEND_LEAD
      │   │   └── BACKEND_DEV    ← API、資料庫
      │   └── TEST_LEAD
      │       └── TESTER         ← 測試案例、QA
      └── ARCHITECT              ← 系統架構設計

    並發執行策略：
      Phase 1（平行）：UI_DESIGNER + ARCHITECT + BACKEND_DEV
      Phase 2（平行，依賴 Phase 1）：CSS_DEV + JS_DEV
      Phase 3（依賴 Phase 2）：TESTER
      Phase 4：TECH_LEAD 審查 → SYNTHESIZER 整合
    """
    config = CompanyConfig(
        name="頁面開發團隊",
        description=(
            "適用於網頁/Mobile 頁面開發：從 UI 設計、前後端實作到測試的完整流程。"
            "支援層級委派與並發執行。"
        ),
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.TECH_LEAD: ROLE_TECH_LEAD,
            RoleType.ARCHITECT: ROLE_ARCHITECT,
            RoleType.FRONTEND_LEAD: ROLE_FRONTEND_LEAD,
            RoleType.BACKEND_LEAD: ROLE_BACKEND_LEAD,
            RoleType.TEST_LEAD: ROLE_TEST_LEAD,
            RoleType.UI_DESIGNER: ROLE_UI_DESIGNER,
            RoleType.CSS_DEV: ROLE_CSS_DEV,
            RoleType.JS_DEV: ROLE_JS_DEV,
            RoleType.BACKEND_DEV: ROLE_BACKEND_DEV,
            RoleType.TESTER: ROLE_TESTER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        org_chart={
            RoleType.MANAGER: [RoleType.TECH_LEAD, RoleType.ARCHITECT],
            RoleType.TECH_LEAD: [RoleType.FRONTEND_LEAD, RoleType.BACKEND_LEAD, RoleType.TEST_LEAD],
            RoleType.FRONTEND_LEAD: [RoleType.UI_DESIGNER, RoleType.CSS_DEV, RoleType.JS_DEV],
            RoleType.BACKEND_LEAD: [RoleType.BACKEND_DEV],
            RoleType.TEST_LEAD: [RoleType.TESTER],
        },
        max_parallel_workers=6,
        max_review_rounds=3,
        decompose_strategy="hierarchical",
        enable_parallel_decompose=True,
    )
    config.budget = BudgetConfig(
        task_limit_usd=3.0,
        session_limit_usd=15.0,
        monthly_limit_usd=150.0,
    )
    return config


def create_fullstack_team() -> CompanyConfig:
    """全端開發團隊（含層級）"""
    config = CompanyConfig(
        name="全端開發團隊",
        description="適用於軟體開發專案：從需求分析到程式碼交付的完整流程",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.TECH_LEAD: ROLE_TECH_LEAD,
            RoleType.FRONTEND_LEAD: ROLE_FRONTEND_LEAD,
            RoleType.BACKEND_LEAD: ROLE_BACKEND_LEAD,
            RoleType.JS_DEV: ROLE_JS_DEV,
            RoleType.CSS_DEV: ROLE_CSS_DEV,
            RoleType.BACKEND_DEV: ROLE_BACKEND_DEV,
            RoleType.TESTER: ROLE_TESTER,
            RoleType.REVIEWER: ROLE_REVIEWER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        org_chart={
            RoleType.MANAGER: [RoleType.TECH_LEAD],
            RoleType.TECH_LEAD: [RoleType.FRONTEND_LEAD, RoleType.BACKEND_LEAD],
            RoleType.FRONTEND_LEAD: [RoleType.JS_DEV, RoleType.CSS_DEV],
            RoleType.BACKEND_LEAD: [RoleType.BACKEND_DEV],
        },
        max_parallel_workers=4,
        max_review_rounds=3,
    )
    return config


def create_research_team() -> CompanyConfig:
    """研究報告團隊"""
    return CompanyConfig(
        name="研究報告團隊",
        description="適用於研究調查、市場分析、報告撰寫",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.ANALYST: ROLE_ANALYST,
            RoleType.RESEARCHER: ROLE_RESEARCHER,
            RoleType.CONTENT_WRITER: ROLE_CONTENT_WRITER,
            RoleType.REVIEWER: ROLE_REVIEWER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        max_parallel_workers=3,
        max_review_rounds=2,
    )


def create_quick_task_team() -> CompanyConfig:
    """快速任務團隊"""
    config = CompanyConfig(
        name="快速任務團隊",
        description="適用於簡單、單一任務，最小化協調開銷與成本",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.DEVELOPER: ROLE_DEVELOPER,
        },
        max_parallel_workers=1,
        max_review_rounds=2,
    )
    config.budget = BudgetConfig(
        task_limit_usd=0.5,
        session_limit_usd=2.0,
        monthly_limit_usd=50.0,
    )
    return config


def create_full_company() -> CompanyConfig:
    """完整公司：所有角色，適用於複雜專案。"""
    config = CompanyConfig(
        name="EvoLoop 完整公司",
        description="包含所有標準角色，支援完整層級委派與並發執行",
        roles=STANDARD_ROLES,
        org_chart={
            RoleType.MANAGER: [
                RoleType.TECH_LEAD,
                RoleType.ARCHITECT,
                RoleType.SECURITY_LEAD,
                RoleType.PRODUCT_LEAD,
                RoleType.FINANCE_LEAD,
                RoleType.INDUSTRIAL_LEAD,
                RoleType.CREATIVE_LEAD,
                RoleType.PLATFORM_LEAD,
                RoleType.AI_LEAD,
                RoleType.GROWTH_LEAD,
            ],
            RoleType.TECH_LEAD: [
                RoleType.FRONTEND_LEAD,
                RoleType.BACKEND_LEAD,
                RoleType.TEST_LEAD,
                RoleType.DATA_LEAD,
                RoleType.DEVOPS,
                RoleType.SRE,
                RoleType.PROMPT_ENGINEER,
                RoleType.PERF_ENG,
                RoleType.OBSERVABILITY_ENG,
                RoleType.MEMORY_CURATOR,
                RoleType.INCIDENT_CMD,
                RoleType.CHAOS_ENG,
                RoleType.CACHE_ENGINEER,
            ],
            RoleType.ARCHITECT: [RoleType.CLOUD_ARCHITECT],
            RoleType.SECURITY_LEAD: [RoleType.SECURITY_ENG, RoleType.LEGAL, RoleType.PEN_TESTER, RoleType.PRIVACY_OFFICER],
            RoleType.PRODUCT_LEAD: [
                RoleType.TECH_WRITER,
                RoleType.CONTENT_WRITER,
                RoleType.RESEARCHER,
                RoleType.UX_RESEARCHER,
                RoleType.SUPPORT,
                RoleType.PRODUCT_DESIGNER,
                RoleType.KNOWLEDGE_MGR,
                RoleType.CUSTOMER_SUCCESS,
                RoleType.CONVERSATION_DESIGNER,
            ],
            RoleType.FINANCE_LEAD: [
                RoleType.QUANT_ANALYST,
                RoleType.RISK_ANALYST,
                RoleType.MARKET_DATA_ENG,
                RoleType.PORTFOLIO_MGR,
                RoleType.SENTIMENT_ANALYST,
            ],
            RoleType.INDUSTRIAL_LEAD: [
                RoleType.OPC_ENGINEER,
                RoleType.PLC_ENGINEER,
                RoleType.IOT_ENGINEER,
            ],
            RoleType.CREATIVE_LEAD: [
                RoleType.STORY_WRITER,
                RoleType.TRANSLATOR,
                RoleType.NARRATIVE_EDITOR,
                RoleType.COPY_EDITOR,
            ],
            RoleType.PLATFORM_LEAD: [
                RoleType.GITHUB_OPS,
                RoleType.RELEASE_ENG,
                RoleType.HUB_OPERATOR,
                RoleType.BILLING_OPS,
                RoleType.ROUTER_ENG,
            ],
            RoleType.AI_LEAD: [
                RoleType.ML_ENGINEER,
                RoleType.MLOPS,
                RoleType.RAG_ENGINEER,
                RoleType.EVAL_ENGINEER,
                RoleType.PROMPT_ENGINEER,
            ],
            RoleType.GROWTH_LEAD: [RoleType.CUSTOMER_SUCCESS, RoleType.CONVERSATION_DESIGNER],
            RoleType.FRONTEND_LEAD: [
                RoleType.UI_DESIGNER,
                RoleType.CSS_DEV,
                RoleType.JS_DEV,
                RoleType.MOBILE_DEV,
                RoleType.ACCESSIBILITY_ENG,
            ],
            RoleType.BACKEND_LEAD: [
                RoleType.BACKEND_DEV,
                RoleType.DBA,
                RoleType.API_ENGINEER,
                RoleType.INTEGRATION_ENG,
                RoleType.FEATURE_FLAG_ENG,
            ],
            RoleType.TEST_LEAD: [RoleType.TESTER, RoleType.QA_AUTOMATION, RoleType.LOAD_TESTER],
            RoleType.DATA_LEAD: [
                RoleType.DATA_ENGINEER,
                RoleType.ANALYST,
                RoleType.CRAWLER,
                RoleType.DATA_SCIENTIST,
            ],
        },
        max_parallel_workers=6,
        max_review_rounds=3,
        decompose_strategy="hierarchical",
        enable_parallel_decompose=True,
    )
    return config


def create_quant_desk() -> CompanyConfig:
    """量化研究桌：StocksX 估值與風險備忘。"""
    return CompanyConfig(
        name="量化研究桌",
        description="適用於行情分析、估值與投資備忘（market_quote／market_backtest／market_optimize／market_portfolio／資金流）",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.FINANCE_LEAD: ROLE_FINANCE_LEAD,
            RoleType.QUANT_ANALYST: ROLE_QUANT_ANALYST,
            RoleType.RISK_ANALYST: ROLE_RISK_ANALYST,
            RoleType.MARKET_DATA_ENG: ROLE_MARKET_DATA_ENG,
            RoleType.PORTFOLIO_MGR: ROLE_PORTFOLIO_MGR,
            RoleType.SENTIMENT_ANALYST: ROLE_SENTIMENT_ANALYST,
            RoleType.ANALYST: ROLE_ANALYST,
            RoleType.RESEARCHER: ROLE_RESEARCHER,
            RoleType.REVIEWER: ROLE_REVIEWER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        org_chart={
            RoleType.MANAGER: [RoleType.FINANCE_LEAD],
            RoleType.FINANCE_LEAD: [
                RoleType.QUANT_ANALYST,
                RoleType.ANALYST,
                RoleType.RESEARCHER,
                RoleType.RISK_ANALYST,
                RoleType.MARKET_DATA_ENG,
                RoleType.PORTFOLIO_MGR,
                RoleType.SENTIMENT_ANALYST,
            ],
        },
        max_parallel_workers=3,
        max_review_rounds=2,
    )


def create_industrial_ops() -> CompanyConfig:
    """工業運維團隊：OPC 感知-診斷-執行。"""
    return CompanyConfig(
        name="工業運維團隊",
        description="適用於 OPC 標籤診斷、護欄寫入與產線建議（PysdnOPC）",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.INDUSTRIAL_LEAD: ROLE_INDUSTRIAL_LEAD,
            RoleType.OPC_ENGINEER: ROLE_OPC_ENGINEER,
            RoleType.SRE: ROLE_SRE,
            RoleType.SECURITY_ENG: ROLE_SECURITY_ENG,
            RoleType.PLC_ENGINEER: ROLE_PLC_ENGINEER,
            RoleType.IOT_ENGINEER: ROLE_IOT_ENGINEER,
            RoleType.REVIEWER: ROLE_REVIEWER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        org_chart={
            RoleType.MANAGER: [RoleType.INDUSTRIAL_LEAD],
            RoleType.INDUSTRIAL_LEAD: [
                RoleType.OPC_ENGINEER,
                RoleType.SRE,
                RoleType.SECURITY_ENG,
                RoleType.PLC_ENGINEER,
                RoleType.IOT_ENGINEER,
            ],
        },
        max_parallel_workers=3,
        max_review_rounds=2,
    )


def create_story_studio() -> CompanyConfig:
    """故事工作室：StoryForge 敘事與在地化。"""
    return CompanyConfig(
        name="故事工作室",
        description="適用於情節、對白、世界觀與在地化（StoryForge）",
        roles={
            RoleType.MANAGER: ROLE_MANAGER,
            RoleType.CREATIVE_LEAD: ROLE_CREATIVE_LEAD,
            RoleType.STORY_WRITER: ROLE_STORY_WRITER,
            RoleType.NARRATIVE_EDITOR: ROLE_NARRATIVE_EDITOR,
            RoleType.CONTENT_WRITER: ROLE_CONTENT_WRITER,
            RoleType.TRANSLATOR: ROLE_TRANSLATOR,
            RoleType.COPY_EDITOR: ROLE_COPY_EDITOR,
            RoleType.REVIEWER: ROLE_REVIEWER,
            RoleType.SYNTHESIZER: ROLE_SYNTHESIZER,
        },
        org_chart={
            RoleType.MANAGER: [RoleType.CREATIVE_LEAD],
            RoleType.CREATIVE_LEAD: [
                RoleType.STORY_WRITER,
                RoleType.NARRATIVE_EDITOR,
                RoleType.CONTENT_WRITER,
                RoleType.TRANSLATOR,
                RoleType.COPY_EDITOR,
            ],
        },
        max_parallel_workers=3,
        max_review_rounds=2,
    )


# 預設模板
BUILTIN_TEMPLATES: dict[str, CompanyConfig] = {
    "page_dev": create_page_dev_team(),
    "fullstack_app": create_fullstack_team(),
    "research_report": create_research_team(),
    "quick_task": create_quick_task_team(),
    "full_company": create_full_company(),
    "quant_desk": create_quant_desk(),
    "industrial_ops": create_industrial_ops(),
    "story_studio": create_story_studio(),
}
