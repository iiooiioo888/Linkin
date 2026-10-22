# 專案目錄地圖

> **詳文單一來源**：改目錄或新增套件時，先更新本文，再同步根 `README.md`／`docs/architecture/overview.md` 的精簡樹。  
> 對齊日期：2026-10-22

## 組件分類

系統分成四類。新套件先歸進其中一類，再寫進下面的目錄表。選路是三條：`simple`、`company`、`minecraft_ops`。工業查詢走 `company`，感測讀數由 `backend/core/` 注入，寫入經 `opc_service/guard.py`。

| 類 | 做什麼 | 落在哪 | 實驗室 |
|----|--------|--------|--------|
| **核心的開發組件** | 前置注入、選路、簡單路徑的生成／評估／反思；任務經理分析與 80 席；提示詞、架構圖、精簡、A/B、臨時容器 | `backend/core/`、`backend/company/`（量化工具見下一類）、`backend/billing/`、`backend/prompts/`、對話與控制台 | 提示詞、架構、精簡、容器、A/B |
| **minecraft組件** | 憲法、16 席子角色、世界模組、MineMCP 寫入護欄、`minecraft_ops` | `backend/linkin/`、`backend/modules/`、`backend/tools/`、Minecraft 畫面 | 側欄進入 `#/modules/minecraft` |
| **價格分析探針組件** | 廠商延遲與報價探針；策略庫與策略圖 | `backend/hub/`、`backend/company/quant_*.py`、Hub 監控（基礎設施 → AI Hub） | 策略庫、策略圖、價格探針 |
| **整合** | 依功能再分：召回、採集、工業接線、Agent 工作流、設計、技能。見下一節 | `backend/memory/`、`backend/integrations/`、`.agents/skills/`、`opc_service/` | `LAB_INTEGRATE_SECTIONS` |

### 整合的功能

實驗室側欄的單一來源是 `frontend/src/lib/labTabs.ts` 的 `LAB_INTEGRATE_SECTIONS`。六個外部客戶端的群組（`recall`／`agent`／`design`）與此對齊。

| 功能 | 做什麼 | 落在哪 |
|------|--------|--------|
| **召回** | 向量記憶與 Token 節省注入：MemOS、OpenViking、WeKnora | `backend/memory/`、`backend/integrations/memos.py`、`openviking.py`、`weknora.py` |
| **採集** | 網頁轉 Markdown、社媒公開採集、Agent Reach 即時閱讀與搜尋 | 實驗室「爬蟲」；MediaCrawler 與 [Agent Reach](https://github.com/Panniantong/Agent-Reach)（`.agents/skills/agent-reach/`）。Agent Reach、just-scrape、agent-browser 要本機 CLI，用 `python -m backend.scripts.cli_runtimes` 檢查 |
| **工業接線** | OPC 讀寫。寫入經護欄。實驗室 MCP 頁把 OPC 開關放在這一組 | `opc_service/` |
| **Agent 工作流** | 任務板與訪談閘門：Yao、Ouroboros | `backend/integrations/yao.py`、`ouroboros.py` |
| **設計** | Design-as-Code，須顯式觸發：OpenPencil | `backend/integrations/openpencil.py` |
| **技能** | Agent skills | `.agents/skills/`、`#/monitor/skills` |

控制台左側（總覽、執行、角色、審計、計費、系統）是核心的開發組件裡的導覽，定義在 `frontend/src/lib/monitorTabs.ts` 的 `CONSOLE_NAV_GROUPS`。Minecraft 世界模組用自己的導覽。實驗室四類的單一來源是 `frontend/src/lib/labTabs.ts` 的 `LAB_NAV_GROUPS`。

```
請求 → backend/main.py
     → 前置：記憶、OPC 讀數、靈境、整合召回
     → resolve_execution_path
         ├─ simple          → 生成／評估／反思
         ├─ company         → 任務經理分析 → 席位（含工業模板）
         └─ minecraft_ops   → 輕量 ReAct + MineMCP
寫世界／OPC 仍走護欄。
```

## 根目錄

| 路徑 | 職責 | 備註 |
|------|------|------|
| `backend/` | FastAPI + LangGraph 主程式 | 見 [backend/README.md](../backend/README.md) |
| `opc_service/` | OPC UA 微服務與護欄 | 整合類。見 [opc_service/README.md](../opc_service/README.md) |
| `frontend/` | React 19 監控中心 | 見 [frontend/README.md](../frontend/README.md) |
| `docs/` | **知識庫（詳文唯一來源）** | 本目錄 |
| `vendor/archify/` | 策略圖與架構圖 CLI（`file:` 依賴） | 價格分析探針／核心開發共用。勿當產品業務邏輯改 |
| `AGENTS.md` | Agent／自動化約束與禁止事項 | CI／協作必讀 |
| `CONTRIBUTING.md` | 貢獻流程與送審清單 | |
| `DESIGN.md` | **前端視覺 Token**（非系統設計） | 說明見 [design/README.md](design/README.md) |
| `DEPLOYMENT.md` | 捷徑 → [deployment/guide.md](deployment/guide.md) | 勿在此堆詳文 |
| `docker-compose.yml` | 全服務編排 | `docker-compose.dev.yml` 為開發變體 |
| `.env.example` | 環境變數範本 | 複製為 `.env`，勿提交 `.env` |
| `pyproject.toml` | Ruff／Mypy／Pytest；`requires-python >=3.12` | |
| `requirements.txt` | Python 依賴 | |

## 埠號（勿混淆）

| 情境 | 前端 | 後端 | OPC | Redis | Chroma |
|------|------|------|-----|-------|--------|
| 本機 Vite | **3001** | 8000 | 8001 | 6379 | 8100 |
| Compose prod（nginx） | **3001→80** | 8000 | 8001 | 6379 | 8100 |
| Compose dev（vite HMR） | **3001** | 8000 | 8001 | 6379 | 8100 |

MineMCP 預設 **3000**（與前端錯開）。術語見 [glossary.md](glossary.md)。

## backend/

| 路徑 | 職責 |
|------|------|
| `main.py` | REST／SSE／WebSocket 入口 |
| `auth/` | 登入閘門 |
| `core/` | 核心的開發組件：圖、節點、`call_llm`、評估、模型池、路由 |
| `company/` | 核心的開發組件：任務經理、80 席、工作項、預算。量化工具屬價格分析探針組件 |
| `linkin/` | minecraft組件：憲法、實體、Minecraft **業務**護欄、16 席子角色種子 |
| `modules/` | minecraft組件：可插拔世界模組目錄（`GET /modules`）；Minecraft 為內建模組 |
| `tools/` | minecraft組件：MineMCP／運維等**底層**橋接（角色勿直連） |
| `hub/` | 價格分析探針組件：廠商延遲／價格探針、熔斷、目錄；契約：`AI_HUB_DETAILED_DESIGN.md` |
| `billing/` | 核心的開發組件：積分池 v6、Docker 計量 |
| `memory/` | 整合：向量記憶（Chroma 等） |
| `integrations/` | 整合：MemOS、OpenViking、WeKnora、Yao、Ouroboros、OpenPencil |
| `services/` | 任務、軌跡、監控、llm_ops、雲控制台、實驗室。跨四類，不單獨成類 |
| `environment/` | 環境探測／執行環境輔助 |
| `middleware/` | FastAPI 中介層 |
| `prompts/` | 共用提示詞片段 |
| `config/` | 執行期 JSON（價卡／成本等），非 Python 套件 |
| `data/` | 種子與執行期資料（部分路徑已 gitignore） |
| `scripts/` | seed／smoke／連線／匯出 |
| `tests/` | pytest（`monkeypatch` 隔離外部依賴） |

### backend/core/（關鍵檔）

| 檔案 | 職責 |
|------|------|
| `graph.py` | `build_graph()`、複雜度路由、編譯圖 |
| `nodes.py` | 生成／評估／反思／改進 |
| `company_nodes.py` | 公司運行時節點橋接 |
| `llm.py` | **`call_llm`（唯一 LLM 出口）** |
| `llm_config.py` · `api_router.py` · `provider_pool.py` | 配置、多 API 路由、模型池鎖定 |
| `evaluation.py` | 多維評估與權重 |
| `state.py` | EvoLoopState |
| `llm_cache.py` · `dynamic_threshold.py` · `routing_feedback.py` | 快取、門檻、路由回饋 |
| `cost_speed_router.py` · `stage_router.py` | 成本／階段路由 |
| `pipeline_trace.py` · `user_feedback.py` | 管線軌跡、用戶回饋 |

### backend/services/（關鍵檔）

| 檔案 | 職責 |
|------|------|
| `task_manager.py` · `task_broadcaster.py` | 任務生命週期與廣播 |
| `trace_logger.py` · `archiver.py` · `state_store.py` | 軌跡、存檔、狀態 |
| `monitor_hub.py` · `dashboard.py` · `agent_monitor.py` | 監控彙總 |
| `llm_ops.py` | 模型目錄爬取／運維 |
| `cloud_console.py` · `docker_manager.py` · `aliyun_bss.py` | 雲／Docker／帳單 |
| `opc_monitor.py` · `optimization_monitor.py` | OPC 與優化指標 |
| `lab_tools.py` | 實驗室工具 |

### backend/company/（關鍵）

| 路徑 | 職責 |
|------|------|
| `orchestrator.py` · `work_item.py` · `state.py` | 協調、工作項 DAG、狀態機 |
| `roles.py` · `role_catalog.py` · `role_memory.py` | 80 席、自定義 CRUD、角色記憶；詳表 [roles.md](company/roles.md) |
| `raho/` | 執行期內部協議（記憶注入與交付檢查），不再佔名冊席位 |
| `budget.py` · `rate_card.py` · `events.py` · `run_log.py` | 預算、價卡、事件、執行日誌 |
| `seat_io.py` | 席位投遞 I/O 軌跡（prompt／system／response 全文＋來源分解）；前端席位監察頁資料源，契約見 [api/reference.md](api/reference.md) |
| `decomposer.py` · `react_loop.py` · `tools.py` | 拆解、ReAct、工具 |
| `quant_*.py` · `docker_tools.py` · `archify_compile.py` | 量化與策略圖（價格分析探針）；Docker 容器（核心的開發組件） |

### backend/linkin/（關鍵）

| 檔案 | 職責 |
|------|------|
| `api.py` | `/linkin/*` 路由 |
| `constitution.py` · `knowledge.py` | 憲法、知識／RAG |
| `minecraft.py` · `tools.py` | **業務護欄**、工具鐵律 |
| `roles.py` · `prompts.py` | 16 席種子、提示詞 |
| `schematic.py` · `nbt.py` · `schem_nbtlib.py` | 建築圖／NBT |
| `pipeline.py` · `grill_me.py` · `design_llm.py` · `server_admin.py` | 管線、Grill、設計、伺服器管理 |

### backend/modules/

| 檔案 | 職責 |
|------|------|
| `registry.py` | `ModuleSpec` 註冊表；禁止與 chat／console／lab 撞 id |
| `api.py` | `GET /modules`、`/{id}`、`/{id}/pages`、`/{id}/capabilities`、`/{id}/health`、`/{id}/api/{path}` |
| `gateway.py` | 統一業務閘道：校驗 capabilities 後轉發 `api_prefix` |
| `minecraft.py` | 內建 Minecraft 模組契約（世界觀／Admin／建築／橋接） |

### backend/scripts/

| 腳本 | 用途 |
|------|------|
| `seed_demo_content` | 示範任務／記憶／軌跡（不呼叫 LLM） |
| `seed_linkin_world` | 靈境世界種子 |
| `smoke_test` | 向量記憶冒煙 |
| `test_llm_connection` | LLM 連線探測 |
| `export_openapi` | 匯出 OpenAPI → `docs/openapi.json` |
| `export_roles_doc` | 匯出角色介紹 → `docs/company/roles.md` |
| `export_monitor_fallback` | Pages／離線監控降級資料 |
| `build_schem` · `archify_compile_ir` | 建築圖／Archify IR |

```powershell
python -m backend.scripts.seed_demo_content
python -m backend.scripts.smoke_test
python backend/scripts/test_llm_connection.py
```

### 角色數字別搞混

| 數字 | 含義 | 來源 |
|------|------|------|
| **80** | 公司 `STANDARD_ROLES` | `backend/company/roles.py` |
| **16** | 靈境子角色（4 總監 × 總監+執行者+審查員+記錄員） | `backend/linkin/roles.py` |
| **8** | `BUILTIN_TEMPLATES` 組織模板 | `backend/company/roles.py` |

## opc_service/

| 路徑 | 職責 |
|------|------|
| `main.py` / `app.py` | 服務入口 |
| `graph.py` + `sense`…`act` | OPC 6 級閉環節點 |
| `guard.py` | **寫入必經**白名單／邊界 |
| `opc_client.py` | OPC UA 客戶端 |
| `simulator/` | 模擬伺服器（`OPC_SIM_ENABLED`） |
| `audit.py` | 審計 |

## frontend/

| 路徑 | 職責 |
|------|------|
| `src/components/MonitorView.tsx` | 監控主視圖 |
| `src/lib/monitorTabs.ts` | 控制台分頁（總覽／執行／審計／計費／系統） |
| `src/lib/worldModules.ts` | 世界模組目錄（hydrate `GET /modules`） |
| `src/modules/` | 模組宿主；`minecraft/` 為獨立世界模組 UI |
| `src/api/` | REST 客戶端（`modules.ts` 的 `createModuleClient`、`linkin.ts` 為 Minecraft typed wrapper） |
| 開發埠 | 預設 **3001**（`VITE_DEV_PORT` 可覆寫） |

## docs/（知識庫）

| 子目錄／檔 | 內容 |
|------------|------|
| `onboarding.md` | 新人導覽 |
| `structure.md` | **本文**（目錄地圖） |
| `glossary.md` | 術語與埠號速查 |
| `architecture/` | 管線、反思、公司、OPC、路線圖 |
| `api/` · `config/` | REST 與環境變數 |
| `linkin/` | 世界觀、靈境 API、Minecraft MCP |
| `company/` | 量化工具等 |
| `development/` · `deployment/` · `faq.md` | 開發、部署、FAQ |
| `AI_HUB_DETAILED_DESIGN.md` | Hub 契約（**路徑固定**，測試會讀取） |
| `openapi.json` | OpenAPI 匯出（若有） |
| `design/` | 視覺 Token 說明（避免與架構混淆） |

## 本機產物（勿提交）

已由 `.gitignore` 忽略，開發時可安心刪除以清盤：

- `.pytest_tmp/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`
- `.archify_cache/`、`hub_data.sqlite3`
- `.venv/`、`frontend/node_modules/`、`frontend/dist/`

## 相關入口

- [新人導覽](onboarding.md) · [術語表](glossary.md) · [知識庫索引](README.md) · [開發指南](development/guide.md)  
- [AGENTS.md](../AGENTS.md) · [CONTRIBUTING.md](../CONTRIBUTING.md)
