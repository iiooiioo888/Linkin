"""外部記憶／知識／代理平台整合層。

整合目標（全部為**可插拔、fail-open**的外部服務客戶端）：

- **MemOS**（本地部署）：長期記憶存取，token 節省主力（召回取代完整歷史）。
- **OpenViking**：上下文資料庫，L0/L1/L2 分層載入，按任務深度召回。
- **WeKnora**：企業級 RAG 知識庫（hybrid search / ask / list KB）。
- **Yao**：自架 agent 工作區與任務板 Open API。
- **Ouroboros**：Agent OS（訪談 ambiguity 閘門／三階段評估／演化迴圈）。

共同契約（對齊 docs/contracts/runtime.md）：
1. 所有客戶端 **fail-open**：外部服務不可用時回傳降級結果＋原因碼，絕不阻斷主任務。
2. 所有呼叫寫入**審計軌跡**（C-AUDIT-005 append-only store）。
3. 禁止在本層直連模型供應商 SDK（C-LLM-001）；召回結果只作為注入片段，
   生成一律經 ``backend.core.llm.call_llm``。
4. 啟用為**顯式動作**（環境變數開關＋健康檢查），禁止隱式自動接入（C-PLUGIN-001 精神）。
"""

from backend.integrations.base import (
    ERR_INTEGRATION_DISABLED,
    ERR_INTEGRATION_UNREACHABLE,
    IntegrationConfig,
    IntegrationResponse,
    ResilientHttpClient,
)

__all__ = [
    "ERR_INTEGRATION_DISABLED",
    "ERR_INTEGRATION_UNREACHABLE",
    "IntegrationConfig",
    "IntegrationResponse",
    "ResilientHttpClient",
]
