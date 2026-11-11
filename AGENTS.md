# AGENTS.md — 靈境·Linkin（EvoLoop 運行時）

## 專案概述

Linkin 基於 EvoLoop：具備自我反思閉環的**統一模式** AI 系統。核心為 **LangGraph 統一管線**。每則查詢先注入記憶、OPC 上下文、靈境上下文與整合召回，再由 `resolve_execution_path` 選路（`route_by_complexity` 是圖上的條件邊）：

- **simple**：單次生成，接著多維評估與反思改進
- **company（含工業查詢）**：任務經理分析任務，產出里程碑與成敗標準，再拆給席位執行。工業查詢用模板 `industrial_ops`，感測讀數注入目標；寫入經 `opc_service/guard.py`。成功後預設定稿，公司後反思由 `EVOL_POST_COMPANY_REFLECT` 決定

不再區分「標準／公司／OPC」三種產品模式。工業查詢進入公司運行時，由任務經理分析。優先序與入口分派見根目錄 README「運作邏輯」。

**文件入口：** [docs/onboarding.md](docs/onboarding.md) · [docs/structure.md](docs/structure.md) · [docs/glossary.md](docs/glossary.md) · [docs/README.md](docs/README.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## 模組邊界與職責

| 模組 | 路徑 | 職責 |
| --- | --- | --- |
| 圖定義 | `backend/core/` | LangGraph 反思閉環、LiteLLM（`llm.py`）、多 API 路由（`api_router.py`）、模型池鎖定、EvoLoopState |
| API 路由 | `backend/api/` | REST／SSE／WebSocket 領域路由（`routers/*`）、請求模型、登入身分 helper；`backend/main.py` 只做 app 組裝（lifespan／middleware／例外／`include_router`） |
| 公司運行時 | `backend/company/` | 協調器、任務經理、**80** 席角色、工作項 DAG、預算、Prompt；席位表見 `docs/company/roles.md` |
| 靈境 | `backend/linkin/` | 憲法、實體、**16** 席子角色（敘事／NPC／道具等，不含遊戲寫入）；見同文「靈境子角色」 |
| 世界／整合模組 | `backend/modules/` | 可插拔目錄與閘道（`GET /modules`、`/{id}/api/*`）；內建 media-vault、local-video-studio |
| AI Hub | `backend/hub/` | 探針／熔斷／目錄（契約：`docs/AI_HUB_DETAILED_DESIGN.md`） |
| OPC 微服務 | `opc_service/` | OPC UA 讀寫與訂閱、護欄、模擬伺服器 |

套件 README：`backend/README.md` · `opc_service/README.md` · `frontend/README.md`。三類組件（核心的開發組件、價格分析探針組件、整合）見 [docs/structure.md](docs/structure.md#組件分類)。新套件先歸進其中一類。整合再按召回、採集、工業接線、Agent 工作流、設計、技能劃分，見 [docs/structure.md](docs/structure.md#整合的功能)。

## 關鍵約束

1. **LLM 調用層**：一律經 `backend.core.llm.call_llm`（LiteLLM），**禁止**直接呼叫任何模型供應商 SDK。
2. **測試隔離**：`monkeypatch` 隔離 LLM／Chroma／Redis／OPC，無需真實 API 金鑰。
3. **圖狀態不可直接修改**：編譯後的圖為運行時產物；變更透過 `build_graph()` 與節點實作。
4. **OPC 安全護欄**：寫入必須經 `opc_service/guard.py`，**禁止**繞過護欄。

## 常用命令

```powershell
# 全部測試
pytest backend/tests/

# 依模組
pytest backend/tests/test_reflection_loop.py
pytest backend/tests/test_company.py
pytest backend/tests/test_raho.py
pytest backend/tests/test_opc_service.py
pytest backend/tests/test_linkin_api.py
pytest backend/tests/test_modules.py

docker compose up -d
docker compose up -d redis chroma

python -m backend.main
cd frontend; npm run dev          # http://localhost:3001

python -m backend.scripts.seed_demo_content
$env:OPC_SIM_ENABLED="true"; python -m opc_service.main
python -m backend.scripts.smoke_test
python backend/scripts/test_llm_connection.py
```

## 禁止操作（索引）

- 禁止直接呼叫模型供應商 SDK → 關鍵約束 #1
- 禁止直接修改編譯後 LangGraph 圖 → #3
- 禁止繞過 OPC 護欄 → #4
