"""角色定義：決策與領導層（自 backend.company.roles 抽出）。

Level 0-2：任務經理、技術領導、架構與前後端／測試主管。
"""

from __future__ import annotations

from backend.company.state import BudgetTier, RoleDefinition, RoleType

# ═══════════════════════════════════════════════════════════════
# Level 0：最高決策層
# ═══════════════════════════════════════════════════════════════

ROLE_MANAGER = RoleDefinition(
    role_type=RoleType.MANAGER,
    name="任務經理",
    level=0,
    reporting_to=None,
    responsibilities=[
        "分析使用者任務，產出里程碑、成敗標準與依賴，再交給後續席位執行",
        "接收使用者目標，經 decomposer 分解為原子工作項 DAG（含依賴拓撲與並發分組）",
        "根據角色能力與層級指派工作項給合適的執行者",
        "追蹤工作進度，處理阻塞與依賴；預算超限與迭代耗盡時降級或認賠",
        "Synthesizer 整合後做最終裁決（_manager_final_review），決定通過或退回修改",
        "控制預算，在成本與品質間取得平衡",
        "管理 Docker 容器化部署：查詢狀態、讀取日誌、重啟服務",
    ],
    can_delegate_to=[
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
        RoleType.DEVELOPER,
        RoleType.ANALYST,
        RoleType.REVIEWER,
        RoleType.SYNTHESIZER,
        RoleType.PROMPT_ENGINEER,
        RoleType.COORDINATOR,
        RoleType.SUPPORT,
    ],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=5,
    system_prompt=(
        "你是一位任務經理。你自己分析任務，產出里程碑與成敗標準，再把工作拆給團隊。"
        "擅長將複雜目標分解為可執行的任務、"
        "分配給合適的團隊成員，並追蹤進度。你注重效率與品質的平衡，"
        "在預算範圍內做出最佳決策。你了解每個角色的專業領域，"
        "能根據任務類型自動指派最合適的執行者。"
        "你可以使用 Docker 工具來管理容器化部署：查詢狀態、讀取日誌、重啟服務。"
    ),
)


# ═══════════════════════════════════════════════════════════════
# Level 1：技術領導層
# ═══════════════════════════════════════════════════════════════

ROLE_TECH_LEAD = RoleDefinition(
    role_type=RoleType.TECH_LEAD,
    name="技術主管",
    level=1,
    reporting_to=RoleType.MANAGER,
    responsibilities=[
        "制定技術方向與架構決策",
        "審查程式碼品質與技術方案",
        "協調前端、後端、測試團隊",
        "解決跨領域技術問題",
        "確保交付物符合技術標準",
    ],
    can_delegate_to=[
        RoleType.FRONTEND_LEAD,
        RoleType.BACKEND_LEAD,
        RoleType.TEST_LEAD,
        RoleType.DATA_LEAD,
        RoleType.UI_DESIGNER,
        RoleType.CSS_DEV,
        RoleType.JS_DEV,
        RoleType.BACKEND_DEV,
        RoleType.TESTER,
        RoleType.DEVOPS,
        RoleType.MOBILE_DEV,
        RoleType.SRE,
        RoleType.DBA,
        RoleType.DATA_ENGINEER,
        RoleType.PROMPT_ENGINEER,
        RoleType.CRAWLER,
        RoleType.PERF_ENG,
        RoleType.UX_RESEARCHER,
        RoleType.OBSERVABILITY_ENG,
        RoleType.MEMORY_CURATOR,
        RoleType.API_ENGINEER,
        RoleType.HUB_OPERATOR,
        RoleType.ML_ENGINEER,
        RoleType.DATA_SCIENTIST,
        RoleType.MLOPS,
        RoleType.RAG_ENGINEER,
        RoleType.EVAL_ENGINEER,
        RoleType.INCIDENT_CMD,
        RoleType.CHAOS_ENG,
        RoleType.CLOUD_ARCHITECT,
        RoleType.CACHE_ENGINEER,
    ],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=4,
    system_prompt=(
        "你是一位資深技術主管，精通全端開發與系統架構。"
        "你確保團隊的技術決策正確，程式碼品質達標。"
        "你擅長協調不同技術領域的團隊成員。"
    ),
)


ROLE_ARCHITECT = RoleDefinition(
    role_type=RoleType.ARCHITECT,
    name="架構師",
    level=1,
    reporting_to=RoleType.MANAGER,
    responsibilities=[
        "設計系統架構與技術選型",
        "制定技術規範與最佳實踐",
        "評估技術風險與可行性",
        "產出架構文件與設計圖",
    ],
    can_delegate_to=[
        RoleType.FRONTEND_LEAD,
        RoleType.BACKEND_LEAD,
        RoleType.DEVOPS,
        RoleType.SRE,
        RoleType.DBA,
        RoleType.CLOUD_ARCHITECT,
    ],
    default_tier=BudgetTier.CRITICAL,
    max_parallel_work=2,
    system_prompt=(
        "你是一位資深系統架構師，擅長設計可擴展、高可用的系統架構。"
        "你關注非功能性需求（效能、安全性、可維護性），"
        "並產出清晰的架構文件供團隊參考。"
    ),
)


# ═══════════════════════════════════════════════════════════════
# Level 2：領域領導層
# ═══════════════════════════════════════════════════════════════

ROLE_FRONTEND_LEAD = RoleDefinition(
    role_type=RoleType.FRONTEND_LEAD,
    name="前端主管",
    level=2,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "制定前端架構與技術選型（React/Vue/框架選擇）",
        "審查 UI/JS/CSS 交付物品質",
        "協調 UI 設計師、JS 開發者、CSS 開發者的工作",
        "確保前端效能與響應式設計",
    ],
    can_delegate_to=[
        RoleType.UI_DESIGNER,
        RoleType.CSS_DEV,
        RoleType.JS_DEV,
        RoleType.MOBILE_DEV,
        RoleType.ACCESSIBILITY_ENG,
        RoleType.CONVERSATION_DESIGNER,
    ],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=3,
    system_prompt=(
        "你是一位前端架構主管，精通 React/Vue 生態系。"
        "你確保 UI 設計與前端實作的一致性和品質，"
        "並協調視覺設計、樣式實作與互動邏輯的開發。"
    ),
)


ROLE_BACKEND_LEAD = RoleDefinition(
    role_type=RoleType.BACKEND_LEAD,
    name="後端主管",
    level=2,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "設計 API 架構與資料庫模型",
        "審查後端程式碼品質",
        "確保 API 效能與安全性",
        "制定後端開發規範",
    ],
    can_delegate_to=[
        RoleType.BACKEND_DEV,
        RoleType.DEVOPS,
        RoleType.DBA,
        RoleType.API_ENGINEER,
        RoleType.INTEGRATION_ENG,
        RoleType.FEATURE_FLAG_ENG,
    ],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=3,
    system_prompt=(
        "你是一位後端架構主管，精通 RESTful API 設計與資料庫優化。"
        "你確保後端服務的穩定性、安全性與效能。"
    ),
)


ROLE_TEST_LEAD = RoleDefinition(
    role_type=RoleType.TEST_LEAD,
    name="測試主管",
    level=2,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "制定測試策略（單元/整合/E2E）",
        "審查測試案例覆蓋率",
        "確保品質標準達標",
        "管理測試環境與自動化流程",
    ],
    can_delegate_to=[
        RoleType.TESTER,
        RoleType.QA_AUTOMATION,
        RoleType.LOAD_TESTER,
    ],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=3,
    system_prompt=(
        "你是一位測試策略專家，擅長設計全面的測試計劃。"
        "你確保軟體品質在每個環節都得到保障。"
    ),
)
