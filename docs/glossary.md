# 術語表

> 新人與 Agent 共用。對齊日期：2026-10-22

| 術語 | 含義 |
|------|------|
| **Linkin／靈境** | 本倉庫產品名；世界觀＋監控中心掛在 EvoLoop 運行時上 |
| **EvoLoop** | 上游／運行時核心：LangGraph 統一管線（反思／公司／OPC） |
| **統一模式** | 不再分「標準／公司／OPC」三套產品；由複雜度路由選路 |
| **組件分類** | 核心的開發組件、minecraft組件、價格分析探針組件、整合。見 [目錄地圖](structure.md#組件分類) |
| **整合的功能** | 召回、採集、工業接線、Agent 工作流、設計、技能。見 [目錄地圖](structure.md#整合的功能) |
| **`resolve_execution_path`** | 選路唯一實作：`simple`／`company`／`opc`／`minecraft_ops`。Task、SSE、圖共用 |
| **`route_by_complexity`** | 圖的條件邊：`company`（含工業）→ `run_company`，`minecraft_ops` → `run_minecraft_ops`，`simple` → 單次生成 |
| **反思閉環** | 生成 → 多維評估 →（低分）反思 → 改進 → 再評估 |
| **公司運行時** | 複雜任務的多代理人協調（協調器＋角色＋預算＋工作項 DAG） |
| **任務經理** | 分析任務、拆工作項、做最終裁決的席位（`manager`） |
| **Reviewer／Synthesizer** | 公司流程末端：審查與整合最終交付 |
| **STANDARD_ROLES（80）** | 公司內建角色目錄；詳見 [角色介紹](company/roles.md) |
| **靈境子角色（16）** | 4 總監 ×（總監＋執行者＋審查員＋記錄員）；見 [角色介紹](company/roles.md) |
| **BUILTIN_TEMPLATES（8）** | 內建組織模板；見 [角色介紹](company/roles.md) |
| **LiteLLM／`call_llm`** | 唯一允許的 LLM 出口（`backend.core.llm.call_llm`） |
| **模型池鎖定** | 僅依已存 API／端點開放可用模型並 clamp |
| **AI Hub** | 探針／熔斷／目錄；契約見 `AI_HUB_DETAILED_DESIGN.md`（路徑勿搬） |
| **OPC** | 工業查詢進入公司運行時，由任務經理分析。模板 `industrial_ops`。主圖注入感測摘要；寫入經護欄。微服務自身仍有 sense → act |
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
| Docker Compose（prod nginx） | **宿主 3001→容器 80** | 8000 | 127.0.0.1:8001 | 127.0.0.1:6379 | 127.0.0.1:8100 | — |
| Docker Compose Dev（vite HMR） | **3001** | 8000 | 127.0.0.1:8001 | 127.0.0.1:6379 | 127.0.0.1:8100 | — |

> 勿再把本機開發寫成 5173；Compose 已與本機對齊為 3001。Redis、Chroma、OPC 的宿主埠只綁迴圈位址。

## 相關入口

- [新人導覽](onboarding.md) · [目錄地圖](structure.md) · [常見問題](faq.md)
