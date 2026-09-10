# AGENTS.md — 靈境·Linkin（EvoLoop 運行時）

## 專案概述

Linkin 基於 EvoLoop：具備自我反思閉環的**統一模式** AI 系統。核心為 **LangGraph 統一管線**，三大能力走同一條管線：

- **反思閉環**（生成 → 評估 → 反思 → 優化）：產出一律進入評估／反思／改進迴圈
- **公司運行時**（指揮鏈 L5 用戶 → L4 需求審計 → L3 戰術指揮 → L2 專注執行；獨立審查 L1 憲兵；L0 環境與記憶核心注入每一層；其後 Reviewer → Synthesizer）：複雜任務觸發 RAHO
- **OPC 整合**（感知 → 預處理 → 分析 → 診斷 → 決策 → 執行）：工業任務注入感測上下文

不再區分「標準／公司／OPC」三種產品模式；由 `route_by_complexity` 依任務選路。

**文件入口：** [docs/onboarding.md](docs/onboarding.md) · [docs/structure.md](docs/structure.md) · [docs/glossary.md](docs/glossary.md) · [docs/README.md](docs/README.md) · [CONTRIBUTING.md](CONTRIBUTING.md)

## 模組邊界與職責

| 模組 | 路徑 | 職責 |
| --- | --- | --- |
| 圖定義 | `backend/core/` | LangGraph 反思閉環、LiteLLM（`llm.py`）、多 API 路由（`api_router.py`）、模型池鎖定、EvoLoopState |
| 公司運行時 | `backend/company/` | 協調器、RAHO（`company/raho/`）、**85** 席角色、工作項 DAG、預算、Prompt；席位表見 `docs/company/roles.md` |
| 靈境 | `backend/linkin/` | 憲法、實體、**16** 席子角色、Minecraft 業務護欄；見同文「靈境子角色」 |
| 世界模組 | `backend/modules/` | 可插拔目錄與閘道（`GET /modules`、`/{id}/api/*`）；Minecraft 為第一個模組 |
| Minecraft MCP | `backend/tools/` + `backend/linkin/minecraft.py` | MineMCP JSON-RPC、鐵律、審計；角色經 tool_registry |
| AI Hub | `backend/hub/` | 探針／熔斷／目錄（契約：`docs/AI_HUB_DETAILED_DESIGN.md`） |
| OPC 微服務 | `opc_service/` | OPC UA 讀寫與訂閱、護欄、模擬伺服器 |

套件 README：`backend/README.md` · `opc_service/README.md` · `frontend/README.md` · 目錄地圖：`docs/structure.md`

## 關鍵約束

1. **LLM 調用層**：一律經 `backend.core.llm.call_llm`（LiteLLM），**禁止**直接呼叫任何模型供應商 SDK。
2. **測試隔離**：`monkeypatch` 隔離 LLM／Chroma／Redis／OPC／MineMCP，無需真實 API 金鑰或遊戲伺服器。
3. **圖狀態不可直接修改**：編譯後的圖為運行時產物；變更透過 `build_graph()` 與節點實作。
4. **OPC 安全護欄**：寫入必須經 `opc_service/guard.py`，**禁止**繞過護欄。
5. **Minecraft MCP**：寫入必須經 `backend/tools/minecraft_mcp.py` 與 `backend/linkin/minecraft.py`；**禁止**角色直連 MineMCP，禁止暴露 `write_file` 等檔案系統工具。

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
pytest backend/tests/test_minecraft_mcp.py

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
- 禁止繞過 Minecraft MCP 護欄或暴露檔案系統工具 → #5
