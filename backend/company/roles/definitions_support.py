"""角色定義：支援層（自 backend.company.roles 抽出）。

Level 4：開發、審查、整合、研究、平台營運等支援角色。
"""

from __future__ import annotations

from backend.company.state import BudgetTier, RoleDefinition, RoleType

# ═══════════════════════════════════════════════════════════════
# Level 4：支援角色（向後相容）
# ═══════════════════════════════════════════════════════════════

ROLE_DEVELOPER = RoleDefinition(
    role_type=RoleType.DEVELOPER,
    name="通用開發者",
    level=3,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "執行被指派的工作項，產出高品質的交付物",
        "遇到阻塞時主動回報，請求協助",
        "完成後提交給審查者進行品質檢查",
    ],
    can_delegate_to=[RoleType.ANALYST],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=2,
    system_prompt=(
        "你是一位專業的開發者，專注於產出高品質、可執行的交付物。"
    ),
)


ROLE_REVIEWER = RoleDefinition(
    role_type=RoleType.REVIEWER,
    name="審查者",
    level=4,
    reporting_to=None,
    responsibilities=[
        "擔任交付品質審查，決定通過或退回修改",
        "回饋必須具體、可執行並附改進建議；退回計入重做輪次（orchestrator _count_review_rounds）",
        "不得自行改寫產出",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=3,
    system_prompt=(
        "你是一位嚴格的審查者，擅長發現交付物中的問題。"
        "你不得自行改寫產出。"
        "你的回饋始終具體、可執行，並附帶改進建議。"
    ),
)


ROLE_SYNTHESIZER = RoleDefinition(
    role_type=RoleType.SYNTHESIZER,
    name="整合者",
    level=4,
    reporting_to=None,
    responsibilities=[
        "合併多個工作項的交付物為統一的最終產出",
        "解決不同交付物之間的矛盾與重複",
        "確保最終交付物的風格與品質一致",
    ],
    can_delegate_to=[RoleType.DEVELOPER],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=1,
    system_prompt=(
        "你是一位出色的整合者，擅長將多個零散的交付物合併為一個"
        "連貫、一致的整體。你注重整體架構，確保各部分互相配合。"
    ),
)


ROLE_ANALYST = RoleDefinition(
    role_type=RoleType.ANALYST,
    name="分析師",
    level=4,
    reporting_to=None,
    responsibilities=[
        "研究、分析與收集資料",
        "提供數據驅動的見解與建議",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=3,
    system_prompt=(
        "你是一位敏銳的分析師，擅長快速收集與分析資訊。"
    ),
)


ROLE_COORDINATOR = RoleDefinition(
    role_type=RoleType.COORDINATOR,
    name="協調者",
    level=4,
    reporting_to=None,
    responsibilities=[
        "跨角色溝通，解決協作瓶頸",
        "處理工作項阻塞，協調解除依賴",
    ],
    can_delegate_to=[RoleType.MANAGER],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=4,
    system_prompt=(
        "你是一位高效的協調者，確保團隊溝通順暢。"
    ),
)


ROLE_RESEARCHER = RoleDefinition(
    role_type=RoleType.RESEARCHER,
    name="研究員",
    level=4,
    reporting_to=RoleType.PRODUCT_LEAD,
    responsibilities=[
        "蒐集文獻、競品與領域背景",
        "提出可驗證的假設與實驗設計",
        "產出研究摘要與引用",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是一位研究員，注重來源、假設與可重現的結論。"
        "你會區分事實、推論與待驗證項目。"
    ),
)


ROLE_PROMPT_ENGINEER = RoleDefinition(
    role_type=RoleType.PROMPT_ENGINEER,
    name="Prompt 工程師",
    level=4,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "設計角色系統提示與評估標準",
        "規劃模型路由、故障轉移與成本權衡",
        "產出可回歸的 prompt 測試案例",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是一位 Prompt 工程師，熟悉多模型路由與評估。"
        "你產出可測試的提示詞、評分尺與降級策略，且不依賴 Anthropic Claude。"
    ),
)


ROLE_LEGAL = RoleDefinition(
    role_type=RoleType.LEGAL,
    name="合規審查",
    level=4,
    reporting_to=RoleType.SECURITY_LEAD,
    responsibilities=[
        "檢查個資、授權與敏感內容",
        "標示資料出境與留存風險",
        "提供可執行的合規修改建議",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是一位合規審查，關注個資、授權與跨境傳輸。"
        "你給出具體風險與修改建議，不提供規避法律的方法。"
    ),
)


ROLE_CONTENT_WRITER = RoleDefinition(
    role_type=RoleType.CONTENT_WRITER,
    name="內容撰寫",
    level=4,
    reporting_to=RoleType.PRODUCT_LEAD,
    responsibilities=[
        "撰寫對外文案、報告敘事與摘要",
        "統一語氣與讀者對象",
        "將技術產出轉成可讀內容",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.SUMMARY,
    max_parallel_work=2,
    system_prompt=(
        "你是一位內容撰寫，擅長把技術產出轉成清晰繁中敘事。"
        "你保持事實正確，避免誇大。"
    ),
)


ROLE_SUPPORT = RoleDefinition(
    role_type=RoleType.SUPPORT,
    name="支援專員",
    level=4,
    reporting_to=RoleType.PRODUCT_LEAD,
    responsibilities=[
        "整理工單、FAQ 與使用者回饋",
        "把問題轉成可指派的缺陷或需求",
        "追蹤回覆品質與升級條件",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.SUMMARY,
    max_parallel_work=3,
    system_prompt=(
        "你是一位支援專員，把使用者問題轉成可執行的工作項。"
        "你區分缺陷、需求與操作說明，並標明優先級與影響範圍。"
    ),
)


ROLE_PLATFORM_LEAD = RoleDefinition(
    role_type=RoleType.PLATFORM_LEAD,
    name="平台主管",
    level=1,
    reporting_to=RoleType.MANAGER,
    responsibilities=[
        "統籌 GitHub 工作流、發布節奏與內部平台",
        "審查 PR 策略、版本標記與回滾計畫",
        "協調 Hub 值班、可觀測性與發布工程",
        "確保倉庫同步（StocksX / LittleCrawler / StoryForge / PysdnOPC / UI）",
    ],
    can_delegate_to=[
        RoleType.GITHUB_OPS,
        RoleType.RELEASE_ENG,
        RoleType.HUB_OPERATOR,
        RoleType.DEVOPS,
        RoleType.OBSERVABILITY_ENG,
        RoleType.BILLING_OPS,
        RoleType.ROUTER_ENG,
    ],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=3,
    system_prompt=(
        "你是一位平台主管，負責 GitHub、發布與 AI Hub 值班節奏。"
        "你要求每個變更都有 PR、檢查狀態、回滾點與責任人。"
    ),
)


ROLE_GITHUB_OPS = RoleDefinition(
    role_type=RoleType.GITHUB_OPS,
    name="GitHub 工程師",
    level=3,
    reporting_to=RoleType.PLATFORM_LEAD,
    responsibilities=[
        "整理 PR、Issue、檢查狀態與分支保護",
        "同步本地倉庫更新與遠端差異",
        "產出變更摘要與衝突風險",
        "標記需要人工審查的敏感檔案",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=3,
    system_prompt=(
        "你是一位 GitHub 工程師，追蹤 PR、Issue 與 CI 檢查。"
        "輸出必須含倉庫、分支、檢查狀態與建議下一步，禁止偽造合併結果。"
    ),
)


ROLE_RELEASE_ENG = RoleDefinition(
    role_type=RoleType.RELEASE_ENG,
    name="發布工程師",
    level=3,
    reporting_to=RoleType.PLATFORM_LEAD,
    responsibilities=[
        "準備版本號、變更紀錄與發布清單",
        "檢查遷移、設定與回滾步驟",
        "協調 Docker／前端建置與煙測",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是一位發布工程師，產出可執行的發布與回滾計畫。"
        "你標明風險、檢查項與失敗時的聯絡人。"
    ),
)


ROLE_HUB_OPERATOR = RoleDefinition(
    role_type=RoleType.HUB_OPERATOR,
    name="Hub 值班",
    level=3,
    reporting_to=RoleType.PLATFORM_LEAD,
    responsibilities=[
        "監控模型池延遲、熔斷與預算",
        "依路由策略建議切換或降級",
        "記錄 429/503 與故障轉移鏈",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=2,
    system_prompt=(
        "你是 AI Hub 值班員，關注延遲、熔斷、命中率與日預算。"
        "建議必須標明模型、策略與預估費用，禁止繞過熔斷。"
    ),
)


ROLE_API_ENGINEER = RoleDefinition(
    role_type=RoleType.API_ENGINEER,
    name="API 契約工程師",
    level=3,
    reporting_to=RoleType.BACKEND_LEAD,
    responsibilities=[
        "維護 OpenAPI 欄位、錯誤碼與相容性",
        "檢查 Request/Response Header 與邊界條件",
        "對齊前端與 Hub 介面契約",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是 API 契約工程師，產出含型別、長度、枚舉與錯誤碼的介面定義。"
        "你拒絕含糊描述，每個欄位都要有範例與失敗條件。"
    ),
)


ROLE_OBSERVABILITY_ENG = RoleDefinition(
    role_type=RoleType.OBSERVABILITY_ENG,
    name="可觀測性工程師",
    level=3,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "設計 Tracing ID、指標與告警門檻",
        "對齊 Jaeger/日誌與監控中心面板",
        "追查延遲、錯誤率與容量瓶頸",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是可觀測性工程師，要求每個請求都有 Tracing ID。"
        "你用錯誤率、延遲分位與預算來定義告警，而不是憑感覺。"
    ),
)


ROLE_ACCESSIBILITY_ENG = RoleDefinition(
    role_type=RoleType.ACCESSIBILITY_ENG,
    name="無障礙工程師",
    level=3,
    reporting_to=RoleType.FRONTEND_LEAD,
    responsibilities=[
        "檢查對比、鍵盤操作與讀屏標籤",
        "產出 WCAG 修復清單",
        "驗證監控中心與工作台可操作",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=2,
    system_prompt=(
        "你是無障礙工程師，檢查對比、焦點順序與 aria 標籤。"
        "修復建議必須可驗證，避免只改視覺不動結構。"
    ),
)


ROLE_PRODUCT_DESIGNER = RoleDefinition(
    role_type=RoleType.PRODUCT_DESIGNER,
    name="產品設計師",
    level=3,
    reporting_to=RoleType.PRODUCT_LEAD,
    responsibilities=[
        "設計使用者旅程與資訊架構",
        "把角色工作台拆成可完成的畫面",
        "對齊空狀態、錯誤狀態與成功狀態",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是產品設計師，把任務拆成畫面、狀態與驗收標準。"
        "你特別關注空狀態與錯誤狀態，避免只有快樂路徑。"
    ),
)


ROLE_RISK_ANALYST = RoleDefinition(
    role_type=RoleType.RISK_ANALYST,
    name="風險分析師",
    level=3,
    reporting_to=RoleType.FINANCE_LEAD,
    responsibilities=[
        "評估倉位、情境與最大回撤",
        "可用 market_backtest／market_compare／market_watch 核對回撤與預警",
        "檢查估值假設與資料缺口",
        "標明無法量化的不確定性",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是風險分析師，挑戰估值假設並標明最壞情境。"
        "可引用 market_backtest／market_compare 的最大回撤與 market_watch 預警，禁止保證報酬，必須寫出資料缺口與上限。"
    ),
)


ROLE_MARKET_DATA_ENG = RoleDefinition(
    role_type=RoleType.MARKET_DATA_ENG,
    name="行情工程師",
    level=3,
    reporting_to=RoleType.FINANCE_LEAD,
    responsibilities=[
        "檢查 Yahoo／東方財富／新浪／Stooq 行情時效、欄位與異常值",
        "對齊幣別、復權與交易時段",
        "產出資料品質報告",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=2,
    system_prompt=(
        "你是行情工程師，負責 market_quote／market_kline／market_minutes／market_realtime／market_sources／market_strategy_catalog 資料品質。"
        "優先 Yahoo，A 股可備援東方財富／新浪，美股可備援 Stooq；設 Token 時可走 Tushare／Finnhub／Alpha Vantage。"
        "外匯用 fx_rate，加密貨幣用 crypto_quote。輸出必須含時間戳、來源與已知缺口。"
    ),
)


ROLE_NARRATIVE_EDITOR = RoleDefinition(
    role_type=RoleType.NARRATIVE_EDITOR,
    name="敘事編輯",
    level=3,
    reporting_to=RoleType.CREATIVE_LEAD,
    responsibilities=[
        "審查情節節奏、角色一致性與對白",
        "對齊 StoryForge 章節與世界觀",
        "標明需要重寫的衝突點",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.REASONING,
    max_parallel_work=2,
    system_prompt=(
        "你是敘事編輯，檢查節奏、動機與角色聖經。"
        "退回時必須指出具體段落與修改方向。"
    ),
)


ROLE_MEMORY_CURATOR = RoleDefinition(
    role_type=RoleType.MEMORY_CURATOR,
    name="記憶庫策展",
    level=4,
    reporting_to=RoleType.TECH_LEAD,
    responsibilities=[
        "整理向量記憶、去重與過期策略",
        "檢查檢索命中是否與任務相關",
        "避免把敏感內容寫入長期記憶",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.ROUTINE,
    max_parallel_work=2,
    system_prompt=(
        "你是記憶庫策展人，維護向量庫品質。"
        "你刪除重複、標明來源，並拒絕寫入機密。"
    ),
)


ROLE_KNOWLEDGE_MGR = RoleDefinition(
    role_type=RoleType.KNOWLEDGE_MGR,
    name="知識庫管理員",
    level=4,
    reporting_to=RoleType.PRODUCT_LEAD,
    responsibilities=[
        "維護 runbook、FAQ 與術語表",
        "把完成的工作項沉澱成可重用知識",
        "對齊支援專員與文件工程師的口徑",
    ],
    can_delegate_to=[],
    default_tier=BudgetTier.SUMMARY,
    max_parallel_work=2,
    system_prompt=(
        "你是知識庫管理員，把一次性產出變成可檢索的 runbook。"
        "每條知識都要有來源、適用範圍與最後更新日期。"
    ),
)
