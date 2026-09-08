"""公司運行時狀態模型。

定義公司配置、角色、工作項、預算追蹤等核心資料結構。
所有模型均為 dataclass，方便序列化與測試隔離。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from backend.company.prompts import PromptConfig

# ═══════════════════════════════════════════════════════════════
# 工作項狀態機
# ═══════════════════════════════════════════════════════════════

class WorkItemStatus(str, Enum):
    """工作項生命週期狀態。

    流轉路徑：
      PLANNING → READY → EXECUTING → IN_REVIEW
        → REWORK → EXECUTING（迴圈）
        → DONE
        → BLOCKED（可由任何狀態轉入，解除後回到原狀態）
    """

    PLANNING = "planning"        # 規劃中：Manager 正在拆解/定義
    READY = "ready"              # 就緒：可被領取執行
    EXECUTING = "executing"      # 執行中：Worker 正在處理
    IN_REVIEW = "in_review"      # 審查中：Reviewer 正在評估
    REWORK = "rework"            # 需修改：審查不通過，退回重做
    DONE = "done"                # 已完成
    BLOCKED = "blocked"          # 阻塞：等待外部依賴或決策


# 合法的狀態轉換
VALID_TRANSITIONS: dict[WorkItemStatus, set[WorkItemStatus]] = {
    WorkItemStatus.PLANNING:   {WorkItemStatus.READY, WorkItemStatus.BLOCKED},
    WorkItemStatus.READY:      {WorkItemStatus.EXECUTING, WorkItemStatus.BLOCKED},
    WorkItemStatus.EXECUTING:  {WorkItemStatus.IN_REVIEW, WorkItemStatus.BLOCKED},
    WorkItemStatus.IN_REVIEW:  {WorkItemStatus.DONE, WorkItemStatus.REWORK, WorkItemStatus.BLOCKED},
    WorkItemStatus.REWORK:     {WorkItemStatus.EXECUTING, WorkItemStatus.BLOCKED},
    WorkItemStatus.DONE:       set(),  # 終態
    WorkItemStatus.BLOCKED:    {WorkItemStatus.READY, WorkItemStatus.EXECUTING,
                                WorkItemStatus.IN_REVIEW, WorkItemStatus.REWORK},
}


# ═══════════════════════════════════════════════════════════════
# 預算層級
# ═══════════════════════════════════════════════════════════════

class BudgetTier(str, Enum):
    """模型路由層級，決定使用哪個模型處理任務。

    - critical:  關鍵決策、複雜程式碼生成（最貴模型）
    - reasoning: 多步驟規劃、邏輯推理
    - routine:   日常對話、簡單任務
    - summary:   摘要、分類（最便宜模型）
    """

    CRITICAL = "critical"
    REASONING = "reasoning"
    ROUTINE = "routine"
    SUMMARY = "summary"


# ═══════════════════════════════════════════════════════════════
# 工作項優先級
# ═══════════════════════════════════════════════════════════════

class Priority(int, Enum):
    """工作項優先級。數值越小優先級越高。"""

    CRITICAL = 0   # 關鍵路徑，必須最先完成
    HIGH = 1       # 高優先級
    MEDIUM = 2     # 中優先級（預設）
    LOW = 3        # 低優先級，可延後


# ═══════════════════════════════════════════════════════════════
# 角色定義
# ═══════════════════════════════════════════════════════════════

class RoleType(str, Enum):
    """預定義角色類型，含層級關係。

    層級結構（從上到下）：
      Level 0: MANAGER
      Level 1: TECH/ARCHITECT/SECURITY/PRODUCT/FINANCE/INDUSTRIAL/CREATIVE/PLATFORM/AI/GROWTH LEAD
      Level 2: FRONTEND/BACKEND/TEST/DATA LEAD
      Level 3: 執行層（開發、量化、爬蟲、OPC、故事、GitHub、Hub、行情等）
      Level 4: REVIEWER, SYNTHESIZER, ANALYST, COORDINATOR, RESEARCHER, PROMPT_ENGINEER, LEGAL, CONTENT_WRITER, SUPPORT, MEMORY, KNOWLEDGE, REQUIREMENT_AUDITOR
    """

    # ── Level 0：最高決策層 ──
    MANAGER = "manager"

    # ── Level 1：技術／產品／領域領導層 ──
    TECH_LEAD = "tech_lead"          # 技術主管：技術方向、架構決策、程式碼審查
    ARCHITECT = "architect"          # 架構師：系統設計、技術選型
    SECURITY_LEAD = "security_lead"  # 資安主管：威脅模型、合規、安全閘
    PRODUCT_LEAD = "product_lead"    # 產品主管：需求、優先序、驗收標準
    FINANCE_LEAD = "finance_lead"    # 金融主管：估值、風險、StocksX
    INDUSTRIAL_LEAD = "industrial_lead"  # 工業主管：OPC 閉環、產線
    CREATIVE_LEAD = "creative_lead"  # 創意主管：敘事、StoryForge
    PLATFORM_LEAD = "platform_lead"  # 平台主管：GitHub、發布、Hub、內部工具
    AI_LEAD = "ai_lead"              # AI 主管：模型評測、RAG、Prompt 策略
    GROWTH_LEAD = "growth_lead"      # 成長主管：獲客、留存、客戶成功

    # ── Level 2：領域領導層 ──
    FRONTEND_LEAD = "frontend_lead"  # 前端主管：UI/UX 方向、前端架構
    BACKEND_LEAD = "backend_lead"    # 後端主管：API 設計、資料庫架構
    TEST_LEAD = "test_lead"          # 測試主管：測試策略、品質標準
    DATA_LEAD = "data_lead"          # 資料主管：資料資產、分析策略

    # ── Level 3：執行層 ──
    UI_DESIGNER = "ui_designer"      # UI 設計師：視覺設計、線框圖、原型
    CSS_DEV = "css_dev"              # CSS 開發者：樣式、響應式、動畫
    JS_DEV = "js_dev"                # JS 開發者：前端邏輯、互動、狀態管理
    BACKEND_DEV = "backend_dev"      # 後端開發者：API、業務邏輯、資料庫
    TESTER = "tester"                # 測試工程師：測試案例、自動化測試、QA
    DEVOPS = "devops"                # 維運工程師：部署、CI/CD、監控
    MOBILE_DEV = "mobile_dev"        # 行動開發者：iOS/Android/跨平台
    SRE = "sre"                      # 可靠性工程師：SLO、告警、事故
    DBA = "dba"                      # 資料庫管理員：schema、備份、效能
    SECURITY_ENG = "security_eng"    # 資安工程師：弱點掃描、防護實作
    DATA_ENGINEER = "data_engineer"  # 資料工程師：管線、倉儲、品質
    TECH_WRITER = "tech_writer"      # 技術文件工程師：API/操作手冊
    QUANT_ANALYST = "quant_analyst"  # 量化分析師：估值、回測、StocksX
    CRAWLER = "crawler"              # 爬蟲工程師：LittleCrawler
    OPC_ENGINEER = "opc_engineer"    # OPC 工業工程師：PysdnOPC
    STORY_WRITER = "story_writer"    # 故事創作者：StoryForge
    UX_RESEARCHER = "ux_researcher"  # UX 研究員：訪談、可用性
    PERF_ENG = "perf_eng"            # 效能工程師：延遲、容量
    TRANSLATOR = "translator"        # 在地化：繁中／多語
    GITHUB_OPS = "github_ops"        # GitHub 工程師：PR、Issue、Release
    RELEASE_ENG = "release_eng"      # 發布工程師：版本、變更紀錄、回滾
    HUB_OPERATOR = "hub_operator"    # Hub 值班：路由、熔斷、預算
    API_ENGINEER = "api_engineer"    # API 契約工程師：OpenAPI、相容性
    OBSERVABILITY_ENG = "observability_eng"  # 可觀測性：追蹤、儀表、告警
    ACCESSIBILITY_ENG = "accessibility_eng"  # 無障礙：對比、鍵盤、讀屏
    PRODUCT_DESIGNER = "product_designer"    # 產品設計師：旅程、資訊架構
    RISK_ANALYST = "risk_analyst"    # 風險分析師：倉位、情境、上限
    MARKET_DATA_ENG = "market_data_eng"  # 行情工程師：StocksX 資料品質
    NARRATIVE_EDITOR = "narrative_editor"    # 敘事編輯：節奏、角色聖經
    ML_ENGINEER = "ml_engineer"              # 機器學習工程師：訓練、特徵、推論
    DATA_SCIENTIST = "data_scientist"        # 資料科學家：假設、實驗、模型解釋
    MLOPS = "mlops"                          # MLOps：模型部署、監控、回滾
    RAG_ENGINEER = "rag_engineer"            # RAG 工程師：檢索、切片、重排
    EVAL_ENGINEER = "eval_engineer"          # 評測工程師：基準、回歸、紅隊題
    CONVERSATION_DESIGNER = "conversation_designer"  # 對話設計師：意圖、回覆、降級話術
    QA_AUTOMATION = "qa_automation"          # 自動化 QA：E2E、回歸閘
    LOAD_TESTER = "load_tester"              # 負載測試：吞吐、飽和、瓶頸
    PEN_TESTER = "pen_tester"                # 滲透測試：攻擊面、PoC、修復優先序
    INCIDENT_CMD = "incident_cmd"            # 事故指揮官：分級、溝通、事後檢討
    CHAOS_ENG = "chaos_eng"                  # 混沌工程師：故障注入、韌性實驗
    CLOUD_ARCHITECT = "cloud_architect"      # 雲架構師：帳號、網路、成本
    INTEGRATION_ENG = "integration_eng"      # 整合工程師：外部 API、Webhook
    FEATURE_FLAG_ENG = "feature_flag_eng"    # 功能開關工程師：灰度、回滾
    CACHE_ENGINEER = "cache_engineer"        # 快取工程師：TTL、命中率、失效
    PLC_ENGINEER = "plc_engineer"            # PLC 工程師：梯形圖、連鎖、安全回路
    IOT_ENGINEER = "iot_engineer"            # IoT 工程師：邊緣裝置、協定、韌體
    PORTFOLIO_MGR = "portfolio_mgr"          # 投資組合經理：權重、再平衡、上限
    SENTIMENT_ANALYST = "sentiment_analyst"  # 情緒分析師：新聞、社群、事件衝擊
    BILLING_OPS = "billing_ops"              # 計費運維：用量、發票、異常扣款
    ROUTER_ENG = "router_eng"                # 路由工程師：權重、故障轉移、競速
    COPY_EDITOR = "copy_editor"              # 文案編輯：語氣、錯字、品牌用詞
    PRIVACY_OFFICER = "privacy_officer"      # 隱私長：個資盤點、最小化、留存
    CUSTOMER_SUCCESS = "customer_success"    # 客戶成功：健康度、升級、續約風險

    # ── Level 4：支援角色 ──
    DEVELOPER = "developer"          # 通用開發者（向後相容）
    REVIEWER = "reviewer"            # 審查者
    SYNTHESIZER = "synthesizer"      # 整合者
    ANALYST = "analyst"              # 分析師
    COORDINATOR = "coordinator"      # 協調者
    RESEARCHER = "researcher"        # 研究員：文獻、競品、實驗設計
    PROMPT_ENGINEER = "prompt_engineer"  # Prompt 工程師：路由、評估、提示詞
    LEGAL = "legal"                  # 合規審查：個資、授權、敏感內容
    CONTENT_WRITER = "content_writer"    # 內容撰寫：對外文案、報告敘事
    SUPPORT = "support"              # 支援專員：工單、FAQ、回饋
    MEMORY_CURATOR = "memory_curator"    # 記憶庫策展：向量庫、去重、過期
    KNOWLEDGE_MGR = "knowledge_mgr"      # 知識庫管理員：runbook、FAQ、術語
    REQUIREMENT_AUDITOR = "requirement_auditor"  # 需求審計官：五維鎖定、戰術指令門票


class RoleCategory(str, Enum):
    """角色分類：用於任務分解時的自動指派邏輯。"""

    UI = "ui"                  # UI 設計類
    CSS = "css"                # 樣式類
    JS = "js"                  # 前端邏輯類
    BACKEND = "backend"        # 後端類
    TEST = "test"              # 測試類
    DEVOPS = "devops"          # 維運類
    MANAGEMENT = "management"  # 管理類
    REVIEW = "review"          # 審查類
    SECURITY = "security"      # 資安類
    DATA = "data"              # 資料類
    PRODUCT = "product"        # 產品類
    DOCS = "docs"              # 文件類
    MOBILE = "mobile"          # 行動端類
    RESEARCH = "research"      # 研究類
    AI = "ai"                  # AI / Prompt 類
    LEGAL = "legal"            # 合規類
    FINANCE = "finance"        # 金融／量化類
    INDUSTRIAL = "industrial"  # 工業／OPC 類
    CREATIVE = "creative"      # 創意／敘事類
    CRAWLER = "crawler"        # 爬蟲／採集類
    PLATFORM = "platform"      # GitHub／發布／平台
    HUB = "hub"                # AI Hub 路由
    MEMORY = "memory"          # 向量記憶／知識庫
    GROWTH = "growth"          # 成長／客戶成功


# 角色到分類的映射（供自動指派使用）
ROLE_CATEGORY_MAP: dict[RoleType, RoleCategory] = {
    RoleType.UI_DESIGNER: RoleCategory.UI,
    RoleType.CSS_DEV: RoleCategory.CSS,
    RoleType.JS_DEV: RoleCategory.JS,
    RoleType.FRONTEND_LEAD: RoleCategory.JS,
    RoleType.BACKEND_DEV: RoleCategory.BACKEND,
    RoleType.BACKEND_LEAD: RoleCategory.BACKEND,
    RoleType.TESTER: RoleCategory.TEST,
    RoleType.TEST_LEAD: RoleCategory.TEST,
    RoleType.DEVOPS: RoleCategory.DEVOPS,
    RoleType.SRE: RoleCategory.DEVOPS,
    RoleType.MANAGER: RoleCategory.MANAGEMENT,
    RoleType.TECH_LEAD: RoleCategory.MANAGEMENT,
    RoleType.ARCHITECT: RoleCategory.MANAGEMENT,
    RoleType.REVIEWER: RoleCategory.REVIEW,
    RoleType.SECURITY_LEAD: RoleCategory.SECURITY,
    RoleType.SECURITY_ENG: RoleCategory.SECURITY,
    RoleType.PRODUCT_LEAD: RoleCategory.PRODUCT,
    RoleType.DATA_LEAD: RoleCategory.DATA,
    RoleType.DATA_ENGINEER: RoleCategory.DATA,
    RoleType.DBA: RoleCategory.DATA,
    RoleType.ANALYST: RoleCategory.DATA,
    RoleType.MOBILE_DEV: RoleCategory.MOBILE,
    RoleType.TECH_WRITER: RoleCategory.DOCS,
    RoleType.CONTENT_WRITER: RoleCategory.DOCS,
    RoleType.RESEARCHER: RoleCategory.RESEARCH,
    RoleType.PROMPT_ENGINEER: RoleCategory.AI,
    RoleType.LEGAL: RoleCategory.LEGAL,
    RoleType.SYNTHESIZER: RoleCategory.REVIEW,
    RoleType.COORDINATOR: RoleCategory.MANAGEMENT,
    RoleType.DEVELOPER: RoleCategory.BACKEND,
    RoleType.FINANCE_LEAD: RoleCategory.FINANCE,
    RoleType.QUANT_ANALYST: RoleCategory.FINANCE,
    RoleType.INDUSTRIAL_LEAD: RoleCategory.INDUSTRIAL,
    RoleType.OPC_ENGINEER: RoleCategory.INDUSTRIAL,
    RoleType.CREATIVE_LEAD: RoleCategory.CREATIVE,
    RoleType.STORY_WRITER: RoleCategory.CREATIVE,
    RoleType.CRAWLER: RoleCategory.CRAWLER,
    RoleType.UX_RESEARCHER: RoleCategory.PRODUCT,
    RoleType.PERF_ENG: RoleCategory.DEVOPS,
    RoleType.TRANSLATOR: RoleCategory.DOCS,
    RoleType.SUPPORT: RoleCategory.PRODUCT,
    RoleType.PLATFORM_LEAD: RoleCategory.PLATFORM,
    RoleType.GITHUB_OPS: RoleCategory.PLATFORM,
    RoleType.RELEASE_ENG: RoleCategory.PLATFORM,
    RoleType.HUB_OPERATOR: RoleCategory.HUB,
    RoleType.MEMORY_CURATOR: RoleCategory.MEMORY,
    RoleType.KNOWLEDGE_MGR: RoleCategory.MEMORY,
    RoleType.REQUIREMENT_AUDITOR: RoleCategory.REVIEW,
    RoleType.API_ENGINEER: RoleCategory.BACKEND,
    RoleType.OBSERVABILITY_ENG: RoleCategory.DEVOPS,
    RoleType.ACCESSIBILITY_ENG: RoleCategory.UI,
    RoleType.PRODUCT_DESIGNER: RoleCategory.PRODUCT,
    RoleType.RISK_ANALYST: RoleCategory.FINANCE,
    RoleType.MARKET_DATA_ENG: RoleCategory.FINANCE,
    RoleType.NARRATIVE_EDITOR: RoleCategory.CREATIVE,
    RoleType.AI_LEAD: RoleCategory.AI,
    RoleType.GROWTH_LEAD: RoleCategory.GROWTH,
    RoleType.ML_ENGINEER: RoleCategory.AI,
    RoleType.DATA_SCIENTIST: RoleCategory.DATA,
    RoleType.MLOPS: RoleCategory.AI,
    RoleType.RAG_ENGINEER: RoleCategory.AI,
    RoleType.EVAL_ENGINEER: RoleCategory.AI,
    RoleType.CONVERSATION_DESIGNER: RoleCategory.AI,
    RoleType.QA_AUTOMATION: RoleCategory.TEST,
    RoleType.LOAD_TESTER: RoleCategory.TEST,
    RoleType.PEN_TESTER: RoleCategory.SECURITY,
    RoleType.INCIDENT_CMD: RoleCategory.DEVOPS,
    RoleType.CHAOS_ENG: RoleCategory.DEVOPS,
    RoleType.CLOUD_ARCHITECT: RoleCategory.DEVOPS,
    RoleType.INTEGRATION_ENG: RoleCategory.BACKEND,
    RoleType.FEATURE_FLAG_ENG: RoleCategory.BACKEND,
    RoleType.CACHE_ENGINEER: RoleCategory.DEVOPS,
    RoleType.PLC_ENGINEER: RoleCategory.INDUSTRIAL,
    RoleType.IOT_ENGINEER: RoleCategory.INDUSTRIAL,
    RoleType.PORTFOLIO_MGR: RoleCategory.FINANCE,
    RoleType.SENTIMENT_ANALYST: RoleCategory.FINANCE,
    RoleType.BILLING_OPS: RoleCategory.HUB,
    RoleType.ROUTER_ENG: RoleCategory.HUB,
    RoleType.COPY_EDITOR: RoleCategory.CREATIVE,
    RoleType.PRIVACY_OFFICER: RoleCategory.LEGAL,
    RoleType.CUSTOMER_SUCCESS: RoleCategory.GROWTH,
}


# 角色層級（數字越小越高層）
ROLE_LEVEL: dict[RoleType, int] = {
    RoleType.MANAGER: 0,
    RoleType.TECH_LEAD: 1,
    RoleType.ARCHITECT: 1,
    RoleType.SECURITY_LEAD: 1,
    RoleType.PRODUCT_LEAD: 1,
    RoleType.FINANCE_LEAD: 1,
    RoleType.INDUSTRIAL_LEAD: 1,
    RoleType.CREATIVE_LEAD: 1,
    RoleType.PLATFORM_LEAD: 1,
    RoleType.AI_LEAD: 1,
    RoleType.GROWTH_LEAD: 1,
    RoleType.FRONTEND_LEAD: 2,
    RoleType.BACKEND_LEAD: 2,
    RoleType.TEST_LEAD: 2,
    RoleType.DATA_LEAD: 2,
    RoleType.UI_DESIGNER: 3,
    RoleType.CSS_DEV: 3,
    RoleType.JS_DEV: 3,
    RoleType.BACKEND_DEV: 3,
    RoleType.TESTER: 3,
    RoleType.DEVOPS: 3,
    RoleType.MOBILE_DEV: 3,
    RoleType.SRE: 3,
    RoleType.DBA: 3,
    RoleType.SECURITY_ENG: 3,
    RoleType.DATA_ENGINEER: 3,
    RoleType.TECH_WRITER: 3,
    RoleType.QUANT_ANALYST: 3,
    RoleType.CRAWLER: 3,
    RoleType.OPC_ENGINEER: 3,
    RoleType.STORY_WRITER: 3,
    RoleType.UX_RESEARCHER: 3,
    RoleType.PERF_ENG: 3,
    RoleType.TRANSLATOR: 3,
    RoleType.DEVELOPER: 3,
    RoleType.GITHUB_OPS: 3,
    RoleType.RELEASE_ENG: 3,
    RoleType.HUB_OPERATOR: 3,
    RoleType.API_ENGINEER: 3,
    RoleType.OBSERVABILITY_ENG: 3,
    RoleType.ACCESSIBILITY_ENG: 3,
    RoleType.PRODUCT_DESIGNER: 3,
    RoleType.RISK_ANALYST: 3,
    RoleType.MARKET_DATA_ENG: 3,
    RoleType.NARRATIVE_EDITOR: 3,
    RoleType.ML_ENGINEER: 3,
    RoleType.DATA_SCIENTIST: 3,
    RoleType.MLOPS: 3,
    RoleType.RAG_ENGINEER: 3,
    RoleType.EVAL_ENGINEER: 3,
    RoleType.CONVERSATION_DESIGNER: 3,
    RoleType.QA_AUTOMATION: 3,
    RoleType.LOAD_TESTER: 3,
    RoleType.PEN_TESTER: 3,
    RoleType.INCIDENT_CMD: 3,
    RoleType.CHAOS_ENG: 3,
    RoleType.CLOUD_ARCHITECT: 3,
    RoleType.INTEGRATION_ENG: 3,
    RoleType.FEATURE_FLAG_ENG: 3,
    RoleType.CACHE_ENGINEER: 3,
    RoleType.PLC_ENGINEER: 3,
    RoleType.IOT_ENGINEER: 3,
    RoleType.PORTFOLIO_MGR: 3,
    RoleType.SENTIMENT_ANALYST: 3,
    RoleType.BILLING_OPS: 3,
    RoleType.ROUTER_ENG: 3,
    RoleType.COPY_EDITOR: 3,
    RoleType.PRIVACY_OFFICER: 3,
    RoleType.CUSTOMER_SUCCESS: 3,
    RoleType.REVIEWER: 4,
    RoleType.SYNTHESIZER: 4,
    RoleType.ANALYST: 4,
    RoleType.COORDINATOR: 4,
    RoleType.RESEARCHER: 4,
    RoleType.PROMPT_ENGINEER: 4,
    RoleType.LEGAL: 4,
    RoleType.CONTENT_WRITER: 4,
    RoleType.SUPPORT: 4,
    RoleType.MEMORY_CURATOR: 4,
    RoleType.KNOWLEDGE_MGR: 4,
    RoleType.REQUIREMENT_AUDITOR: 4,
}


@dataclass
class RoleDefinition:
    """角色定義：職責、能力、層級關係、可委派對象。"""

    role_type: RoleType
    name: str                                    # 角色名稱（如 "前端主管"）
    responsibilities: list[str] = field(default_factory=list)
    can_delegate_to: list[RoleType] = field(default_factory=list)
    reporting_to: RoleType | None = None          # 匯報對象（上級角色）
    default_tier: BudgetTier = BudgetTier.ROUTINE
    max_parallel_work: int = 3
    system_prompt: str = ""
    level: int = 3                                # 角色層級（0=最高）

    def is_superior_to(self, other: RoleType) -> bool:
        """判斷是否為 other 的上級。"""
        return other in self.can_delegate_to

    def can_manage(self, other: RoleType) -> bool:
        """判斷是否可管理 other（直接或間接）。"""
        return other in self.can_delegate_to


# ═══════════════════════════════════════════════════════════════
# 工作項
# ═══════════════════════════════════════════════════════════════

@dataclass
class WorkItem:
    """單一工作項：可被指派、執行、審查的任務單元。"""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    description: str = ""
    status: WorkItemStatus = WorkItemStatus.PLANNING
    assignee: RoleType | None = None             # 負責角色
    created_by: RoleType | None = None            # 創建者
    depends_on: list[str] = field(default_factory=list)  # 依賴的工作項 ID
    artifacts: dict[str, Any] = field(default_factory=dict)  # 產出物
    feedback: list[dict[str, Any]] = field(default_factory=list)  # 審查回饋
    tier: BudgetTier = BudgetTier.ROUTINE         # 所需模型層級
    priority: Priority = Priority.MEDIUM            # 優先級
    estimated_cost: float = 0.0                   # 預估成本
    actual_cost: float = 0.0                      # 實際成本
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None

    def transition_to(self, new_status: WorkItemStatus) -> bool:
        """嘗試狀態轉換，回傳是否成功。"""
        if new_status in VALID_TRANSITIONS.get(self.status, set()):
            self.status = new_status
            self.updated_at = datetime.now(timezone.utc).isoformat()
            if new_status == WorkItemStatus.DONE:
                self.completed_at = datetime.now(timezone.utc).isoformat()
            return True
        return False


# ═══════════════════════════════════════════════════════════════
# 預算設定
# ═══════════════════════════════════════════════════════════════

@dataclass
class RetryConfig:
    """錯誤重試與升級配置。"""

    max_retries: int = 3                    # 最大重試次數
    retry_backoff_base: float = 1.0         # 退避基礎秒數（指數增長）
    enable_escalation: bool = True          # 是否啟用角色升級
    deadline_seconds: float = 300.0         # 單一工作項超時秒數（0=不限）


def _default_tier_models() -> dict["BudgetTier", str]:
    """層級模型預設值：用戶明確配置過 LLM 模型時全部層級跟随該模型。

    確保公司模式與前端/API 配置的供應商（如 Qwen）一致；
    未配置時保持傳統多模型層級預設。
    """
    from backend.core.llm_config import get_explicit_model

    configured = get_explicit_model()
    if configured:
        # 單一供應商場景：所有層級統一使用配置的模型
        return {
            BudgetTier.CRITICAL: configured,
            BudgetTier.REASONING: configured,
            BudgetTier.ROUTINE: configured,
            BudgetTier.SUMMARY: configured,
        }
    return {
        BudgetTier.CRITICAL: "gpt-4o",
        BudgetTier.REASONING: "gpt-4o",
        BudgetTier.ROUTINE: "gpt-4o-mini",
        BudgetTier.SUMMARY: "gpt-4o-mini",
    }


@dataclass
class BudgetConfig:
    """預算配置：每任務/每會話/每月上限與降級策略。"""

    task_limit_usd: float = 2.0        # 每任務上限（0=不限）
    session_limit_usd: float = 10.0    # 每會話上限
    monthly_limit_usd: float = 100.0   # 每月上限
    warn_threshold: float = 0.8        # 80% 時警告
    degrade_threshold: float = 0.9     # 90% 時降級到便宜模型
    hard_stop: bool = False            # True=超限停止，False=降級繼續

    # 層級路由：每個 tier 對應的模型名稱（預設跟随運行時配置）
    tier_models: dict[BudgetTier, str] = field(default_factory=_default_tier_models)

    # 降級鏈：預算壓力下每個 tier 的備用模型
    # 預設與 tier_models 相同（單一供應商場景無可降級模型）
    degrade_chain: dict[BudgetTier, str] = field(
        default_factory=lambda: {
            tier: model
            for tier, model in _default_tier_models().items()
            if tier in (BudgetTier.CRITICAL, BudgetTier.REASONING)
        }
    )


# ═══════════════════════════════════════════════════════════════
# 公司配置
# ═══════════════════════════════════════════════════════════════

@dataclass
class CompanyConfig:
    """公司配置：組織架構、角色、層級樹、預算、執行策略。"""

    name: str = "EvoLoop 公司"
    description: str = ""
    roles: dict[RoleType, RoleDefinition] = field(default_factory=dict)
    budget: BudgetConfig = field(default_factory=BudgetConfig)

    # 層級關係
    org_chart: dict[RoleType, list[RoleType]] = field(default_factory=dict)
    # org_chart[MANAGER] = [TECH_LEAD, ARCHITECT]
    # org_chart[TECH_LEAD] = [FRONTEND_LEAD, BACKEND_LEAD, TEST_LEAD]

    # 執行策略
    max_parallel_workers: int = 4
    max_review_rounds: int = 3
    auto_approve_risk: str = "medium"

    # 提示詞配置（可完全自定義）
    prompt_config: PromptConfig = field(default_factory=PromptConfig)

    # 重試與錯誤處理配置
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # 任務分解策略
    decompose_strategy: str = "auto"  # auto | hierarchical | flat
    enable_parallel_decompose: bool = True  # 是否允許 LLM 規劃並發執行

    def get_subordinates(self, role: RoleType) -> list[RoleType]:
        """取得某角色的直屬下級。"""
        return self.org_chart.get(role, [])

    def get_all_subordinates(self, role: RoleType) -> list[RoleType]:
        """遞迴取得所有下級（含間接）。"""
        result = []
        direct = self.org_chart.get(role, [])
        for sub in direct:
            result.append(sub)
            result.extend(self.get_all_subordinates(sub))
        return result

    def get_superior(self, role: RoleType) -> RoleType | None:
        """取得某角色的直屬上級。"""
        for superior, subs in self.org_chart.items():
            if role in subs:
                return superior
        return None

    def get_role_level(self, role: RoleType) -> int:
        """取得角色層級。"""
        return ROLE_LEVEL.get(role, 3)

    def build_org_tree(self) -> dict:
        """構建組織樹（供視覺化）。"""
        def _build(node: RoleType) -> dict:
            role_def = self.roles.get(node)
            return {
                "role": node.value,
                "name": role_def.name if role_def else node.value,
                "level": self.get_role_level(node),
                "children": [
                    _build(child)
                    for child in self.org_chart.get(node, [])
                ],
            }
        # 找根節點（Level 0）
        roots = [r for r in self.roles if self.get_role_level(r) == 0]
        if not roots:
            roots = [next(iter(self.roles))] if self.roles else []
        return {
            "company": self.name,
            "tree": [_build(root) for root in roots],
        }


# ═══════════════════════════════════════════════════════════════
# 公司運行時狀態
# ═══════════════════════════════════════════════════════════════

@dataclass
class CompanyRunState:
    """公司單次運行的即時狀態。"""

    config: CompanyConfig = field(default_factory=CompanyConfig)
    goal: str = ""                                  # 公司目標
    work_items: dict[str, WorkItem] = field(default_factory=dict)
    run_log: list[dict[str, Any]] = field(default_factory=list)

    # 預算追蹤
    task_spent: float = 0.0
    session_spent: float = 0.0
    monthly_spent: float = 0.0
    active_tier: BudgetTier = BudgetTier.ROUTINE

    # 執行統計
    total_items: int = 0
    completed_items: int = 0
    review_rounds: int = 0

    def get_kanban(self) -> dict[WorkItemStatus, list[WorkItem]]:
        """回傳當前看板狀態。"""
        board: dict[WorkItemStatus, list[WorkItem]] = {
            s: [] for s in WorkItemStatus
        }
        for item in self.work_items.values():
            board[item.status].append(item)
        return board

    def get_ready_items(self) -> list[WorkItem]:
        """取得所有就緒可執行的工作項（依賴已滿足）。"""
        done_ids = {
            wid for wid, item in self.work_items.items()
            if item.status == WorkItemStatus.DONE
        }
        ready = []
        for item in self.work_items.values():
            if item.status != WorkItemStatus.READY:
                continue
            if all(dep in done_ids for dep in item.depends_on):
                ready.append(item)
        return ready

    def to_dict(self) -> dict[str, Any]:
        """序列化為字典（供存檔/API 回應）。"""
        return {
            "goal": self.goal,
            "work_items": {
                wid: {
                    "id": item.id,
                    "title": item.title,
                    "status": item.status.value,
                    "assignee": item.assignee.value if item.assignee else None,
                    "depends_on": item.depends_on,
                    "tier": item.tier.value,
                    "actual_cost": item.actual_cost,
                    "created_at": item.created_at,
                    "completed_at": item.completed_at,
                }
                for wid, item in self.work_items.items()
            },
            "budget": {
                "task_spent": round(self.task_spent, 4),
                "task_limit": self.config.budget.task_limit_usd,
                "session_spent": round(self.session_spent, 4),
                "session_limit": self.config.budget.session_limit_usd,
                "monthly_spent": round(self.monthly_spent, 4),
                "monthly_limit": self.config.budget.monthly_limit_usd,
                "active_tier": self.active_tier.value,
            },
            "progress": {
                "total": self.total_items,
                "completed": self.completed_items,
                "review_rounds": self.review_rounds,
            },
        }