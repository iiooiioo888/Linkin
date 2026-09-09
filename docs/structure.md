# 專案目錄地圖

> **詳文單一來源**：改目錄或新增套件時，先更新本文，再同步根 `README.md`／`docs/architecture/overview.md` 的精簡樹。  
> 對齊日期：2026-09-09 · 測試收錄約 **639**（`pytest --collect-only -q`）

## 一眼看懂

```
請求 → backend/main.py (FastAPI)
     → backend/core/graph.py (LangGraph)
         ├─ 簡單 → nodes（生成／評估／反思）
         ├─ 複雜 → company/ + raho/
         └─ 工業 → opc_service 上下文 + 6 級閉環
前端 frontend/ 只觀測與配置；寫世界／OPC 仍走護欄。
```

## 根目錄

| 路徑 | 職責 | 備註 |
|------|------|------|
| `backend/` | FastAPI + LangGraph 主程式 | 見 [backend/README.md](../backend/README.md) |
| `opc_service/` | OPC UA 微服務與護欄 | 見 [opc_service/README.md](../opc_service/README.md) |
| `frontend/` | React 19 監控中心 | 見 [frontend/README.md](../frontend/README.md) |
| `docs/` | **知識庫（詳文唯一來源）** | 本目錄 |
| `vendor/archify/` | 策略圖 CLI（`file:` 依賴） | 勿當產品業務邏輯改 |
| `AGENTS.md` | Agent／自動化約束與禁止事項 | CI／協作必讀 |
| `CONTRIBUTING.md` | 貢獻流程與送審清單 | |
| `DESIGN.md` | **前端視覺 Token**（非系統設計） | 說明見 [design/README.md](design/README.md) |
| `DEPLOYMENT.md` | 捷徑 → [deployment/guide.md](deployment/guide.md) | 勿在此堆詳文 |
| `docker-compose.yml` | 全服務編排 | `docker-compose.dev.yml` 為開發變體 |
| `.env.example` | 環境變數範本 | 複製為 `.env`，勿提交 `.env` |

## backend/

| 路徑 | 職責 |
|------|------|
| `main.py` | REST／SSE／WebSocket 入口 |
| `auth/` | 登入閘門 |
| `core/` | 圖、節點、`call_llm`、評估、模型池、路由 |
| `company/` | 多代理人協調、`raho/`、角色目錄、量化工具 |
| `linkin/` | 靈境憲法、實體、Minecraft **業務**護欄、16 席子角色種子 |
| `tools/` | MineMCP／運維等**底層**橋接（角色勿直連） |
| `hub/` | AI Hub（探針／熔斷／目錄）；契約：`AI_HUB_DETAILED_DESIGN.md` |
| `memory/` | 向量記憶（Chroma 等） |
| `services/` | 任務、軌跡、監控、llm_ops、雲控制台、實驗室… |
| `environment/` | 環境探測／執行環境輔助 |
| `middleware/` | FastAPI 中介層 |
| `prompts/` | 共用提示詞片段 |
| `config/` | 執行期 JSON（價卡／成本等），非 Python 套件 |
| `data/` | 種子與執行期資料（部分路徑已 gitignore） |
| `scripts/` | seed／smoke／連線／匯出 |
| `tests/` | pytest（`monkeypatch` 隔離外部依賴） |

### 角色數字別搞混

| 數字 | 含義 | 來源 |
|------|------|------|
| **85** | 公司 `STANDARD_ROLES`（含 RAHO 脊柱） | `backend/company/roles.py` |
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
| `src/lib/monitorTabs.ts` | 活動欄分頁單一資料源 |
| `src/api/` | REST 客戶端 |
| `src/components/linkin/` | 靈境／Minecraft UI |
| 開發埠 | 預設 **3001**（`VITE_DEV_PORT` 可覆寫；勿再寫死 5173） |

## docs/（知識庫）

| 子目錄／檔 | 內容 |
|------------|------|
| `onboarding.md` | 新人導覽 |
| `structure.md` | **本文**（目錄地圖） |
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

- [新人導覽](onboarding.md) · [知識庫索引](README.md) · [開發指南](development/guide.md)  
- [AGENTS.md](../AGENTS.md) · [CONTRIBUTING.md](../CONTRIBUTING.md)
