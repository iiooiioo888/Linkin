# 術語表

> 新人與 Agent 共用。對齊日期：2026-09-09

| 術語 | 含義 |
|------|------|
| **Linkin／靈境** | 本倉庫產品名；世界觀＋監控中心掛在 EvoLoop 運行時上 |
| **EvoLoop** | 上游／運行時核心：LangGraph 統一管線（反思／公司／OPC） |
| **統一模式** | 不再分「標準／公司／OPC」三套產品；由複雜度路由選路 |
| **`route_by_complexity`** | 圖節點：依任務內容選簡單生成／公司運行時／OPC 六級 |
| **反思閉環** | 生成 → 多維評估 →（低分）反思 → 改進 → 再評估 |
| **公司運行時** | 複雜任務的多代理人協調（協調器＋角色＋預算＋工作項 DAG） |
| **RAHO** | 遞歸對抗分層組織：L5→L4→L3→L2；獨立 L1 憲兵；L0 注入各層 |
| **L5／Grill-Me** | 用戶層需求鎖定（可關：`EVOL_RAHO_USER_GRILL=false`） |
| **L4** | 戰役／需求審計，產出高層 DAG |
| **L3** | 戰術指揮，拆成原子工作項 |
| **L2** | 專注執行席 |
| **L1 憲兵** | 獨立驗收／簽核，與執行鏈分離 |
| **L0** | 環境與記憶核心，注入每一層 |
| **Reviewer／Synthesizer** | 公司流程末端：審查與整合最終交付 |
| **STANDARD_ROLES（85）** | 公司內建角色目錄（含 RAHO 脊柱）；詳見 [角色介紹](company/roles.md) |
| **靈境子角色（16）** | 4 總監 ×（總監＋執行者＋審查員＋記錄員）；見 [角色介紹](company/roles.md) |
| **BUILTIN_TEMPLATES（8）** | 內建組織模板；見 [角色介紹](company/roles.md) |
| **LiteLLM／`call_llm`** | 唯一允許的 LLM 出口（`backend.core.llm.call_llm`） |
| **模型池鎖定** | 僅依已存 API／端點開放可用模型並 clamp |
| **AI Hub** | 探針／熔斷／目錄；契約見 `AI_HUB_DETAILED_DESIGN.md`（路徑勿搬） |
| **OPC 六級** | sense → preprocess → analyze → diagnose → decide → act |
| **護欄（guard）** | OPC 寫入白名單／邊界；Minecraft 寫入允許清單與體積上限 |
| **MineMCP** | Minecraft JSON-RPC 橋；角色經 tool_registry，禁止直連 |
| **憲法／worldview** | 靈境世界觀最高裁決依據（`backend/linkin/`） |
| **監控中心** | 前端活動欄：對話 · 控制台 · 世界模組（Minecraft…） · 實驗室 |
| **世界模組** | 可插拔整合（目錄 `GET /modules`）。Minecraft 含世界觀、Admin、內容、建築、橋接 |
| **`DESIGN.md`** | **前端視覺 Token**，不是系統架構設計 |
| **Archify** | `vendor/archify` 策略圖 CLI（`file:` 依賴） |

## 埠號速查

| 情境 | 前端 | 後端 | OPC | Redis | Chroma | MineMCP |
|------|------|------|-----|-------|--------|---------|
| 本機 `npm run dev` | **3001** | 8000 | 8001 | 6379 | 8100 | 3000 |
| Docker Compose（prod nginx） | **宿主 3001→容器 80** | 8000 | 8001 | 6379 | 8100 | — |
| Docker Compose Dev（vite HMR） | **3001** | 8000 | 8001 | 6379 | 8100 | — |

> 勿再把本機開發寫成 5173；Compose 已與本機對齊為 3001。

## 相關入口

- [新人導覽](onboarding.md) · [目錄地圖](structure.md) · [常見問題](faq.md)
