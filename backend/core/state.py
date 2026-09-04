"""EvoLoop 核心狀態模型（Task 1.1）。

定義流轉於整個反思迴圈的狀態結構，每個 LangGraph 節點
接收此狀態並回傳需要更新的部份欄位。
"""

from typing import Any

from typing_extensions import TypedDict

from opc_service.state import OPCStateFields


class DimensionScore(TypedDict, total=False):
    """單一維度的評分。"""

    score: float  # 0-10
    reason: str


class MultiDimEvaluation(TypedDict, total=False):
    """多維度評估結果。"""

    accuracy: DimensionScore
    completeness: DimensionScore
    clarity: DimensionScore
    relevance: DimensionScore
    overall: float  # 加權總分 0-10
    source: str  # "llm" | "rule_fallback" | "cross_model"


class ReflectionRecord(TypedDict):
    """單次反思迴圈的紀錄。"""

    iteration: int
    score: float
    critique: str
    suggestion: str


class EvoLoopState(OPCStateFields, total=False):
    """EvoLoop 反思迴圈的完整狀態。

    繼承 OPCStateFields 以包含 OPC 相關狀態欄位。
    total=False 使所有欄位皆為選填，LangGraph 節點只需
    回傳自己更新的欄位，框架會自動合併進狀態。
    """

    # ---- 輸入 ----
    query: str
    history: list[dict[str, str]]
    session_id: str

    # ---- 記憶檢索（Phase 2 啟用向量檢索後注入） ----
    retrieved_memories: list[str]

    # ---- 生成 ----
    initial_answer: str
    current_answer: str

    # ---- 評估 ----
    score: float
    evaluation: dict[str, Any]
    multi_dim_evaluation: MultiDimEvaluation

    # ---- 反思 ----
    critique: str
    suggestion: str
    reflections: list[ReflectionRecord]
    iteration: int
    max_iterations: int

    # ---- 輸出 ----
    final_answer: str
    memory_saved: bool

    # ---- 文本化存檔（Task 8.6） ----
    archived: bool
    archive_metadata: dict[str, Any]

    # ---- 統一模式：執行策略（auto / simple / company） ----
    # auto: 由系統自動判斷複雜度
    # simple: 強制單次 LLM 生成
    # company: 強制多代理人公司運行時
    execution_strategy: str
    # cost_speed 路由推斷：simple | medium | complex
    task_complexity: str
    company_template: str
    company_result: dict[str, Any]
    company_kanban: dict[str, Any]
    company_budget: dict[str, Any]

    # ---- OPC 工業上下文（統一模式下自動注入） ----
    opc_context: dict[str, Any]

    # ---- 靈境世界觀上下文（命中關鍵詞時注入憲法／RAG） ----
    linkin_context: dict[str, Any]
