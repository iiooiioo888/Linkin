# 角色介紹

> 來源：`backend/company/roles.py`（`STANDARD_ROLES`）＋`backend/linkin/roles.py`（靈境子角色種子）
> 對齊日期：2026-09-09 · 內建 **85** 席＋靈境 **16** 席＋模板 **8**

## 先分清楚三種「角色」

| 種類 | 數量 | 程式來源 | 用途 |
|------|------|----------|------|
| **公司 STANDARD_ROLES** | 85 | `backend/company/roles.py` | 複雜任務／RAHO 調度的代理人席位 |
| **靈境子角色** | 16 | `backend/linkin/roles.py` → `role_catalog` | 建築／敘事／NPC／道具四部門 |
| **組織模板 BUILTIN_TEMPLATES** | 8 | 同 `roles.py` | 預組團隊（非獨立角色） |

監控中心可覆寫 Prompt／預算／工具；持久化於 `EVOL_ROLE_CATALOG_PATH`（預設 `backend/data/role_catalog.json`）。
詳見 [公司運行時](../architecture/company-runtime.md) · [術語表](../glossary.md)。

## 組織職級 vs RAHO 指揮鏈

兩套編號**不要混用**：

| 維度 | 含義 |
|------|------|
| **組織職級 Level 0–4** | `RoleDefinition.level`：數字越小越高層（Manager=0） |
| **RAHO L5–L0** | 指揮／審查協議層：用戶→審計→戰術→原子執行；獨立憲兵；環境核心注入 |

```
組織： L0 Manager → L1 Leads → L2 Domain Leads → L3 Executors → L4 Support
RAHO： L5 用戶 → L4 需求審計 → L3 戰術指揮 → L2 原子執行
       └─ 獨立 L1 憲兵（不隸屬 L3）
       └─ L0 環境與記憶核心（滲透各層，不參與質詢）
```

## 層級一覽（85 席）

| 組織 Level | 名稱 | 席數 |
|------------|------|------|
| 0 | 最高決策層 | 1 |
| 1 | 技術領導層 | 10 |
| 2 | 領域領導層 | 5 |
| 3 | 執行層 | 55 |
| 4 | 支援角色 | 14 |

## RAHO 脊柱（必讀）

這五席是遞歸對抗分層的固定脊柱，與一般「部門員工」不同：

| ID | 中文名 | RAHO | 一句話 |
|----|--------|------|--------|
| `requirement_auditor` | 需求審計官 | RAHO L4 | 戰役／需求審計，語意鎖定與高層 DAG |
| `tactical_commander` | 戰術指揮官 | RAHO L3 | 原子拆解、孵化 L2、Grill SOP |
| `atomic_executor` | 原子執行者 | RAHO L2 | 專注單一 KPI，任務結束回收 |
| `constitutional_inspector` | 憲兵審查官 | RAHO L1 | 獨立四維驗收與簽核 |
| `environment_kernel` | 環境與記憶核心 | RAHO L0 | 環境與記憶注入各層 |

完整協議見 [company-runtime.md](../architecture/company-runtime.md#raho遞歸對抗分層)。

## Level 0：最高決策層（1）

| ID | 名稱 | 分類 | 預算層 | 主要職責 |
|----|------|------|--------|----------|
| `manager` | 專案經理 | 管理 | `reasoning` | 接收使用者目標，將其分解為可執行的工作項；根據角色能力與層級指派工作項給合適的執行者 |

## Level 1：技術領導層（10）

| ID | 名稱 | 分類 | 預算層 | 主要職責 |
|----|------|------|--------|----------|
| `ai_lead` | AI 主管 | AI / Prompt | `reasoning` | 制定模型評測、RAG 與 Prompt 策略；審查幻覺、成本與降級鏈 |
| `architect` | 架構師 | 管理 | `critical` | 設計系統架構與技術選型；制定技術規範與最佳實踐 |
| `creative_lead` | 創意主管 | 創意／敘事 | `reasoning` | 制定敘事基調、世界觀與角色聖經；審查故事、文案與在地化一致性 |
| `finance_lead` | 金融主管 | 金融／量化 | `reasoning` | 制定估值方法、風險上限與研究日曆；審查量化分析師的假設與數據來源 |
| `growth_lead` | 成長主管 | 成長／客戶成功 | `reasoning` | 規劃獲客、啟用與留存實驗；審查文案與對話漏斗 |
| `industrial_lead` | 工業主管 | 工業／OPC | `reasoning` | 規劃 OPC 感知-診斷-執行閉環；審查寫入護欄、白名單與事故升級 |
| `platform_lead` | 平台主管 | 平台／GitHub | `reasoning` | 統籌 GitHub 工作流、發布節奏與內部平台；審查 PR 策略、版本標記與回滾計畫 |
| `product_lead` | 產品主管 | 產品 | `reasoning` | 釐清使用者目標與驗收標準；排定需求優先序與範圍取捨 |
| `security_lead` | 資安主管 | 資安 | `reasoning` | 制定威脅模型與安全閘門；審查認證、授權與敏感資料流向 |
| `tech_lead` | 技術主管 | 管理 | `reasoning` | 制定技術方向與架構決策；審查程式碼品質與技術方案 |

## Level 2：領域領導層（5）

| ID | 名稱 | 分類 | 預算層 | 主要職責 |
|----|------|------|--------|----------|
| `backend_lead` | 後端主管 | 後端 | `reasoning` | 設計 API 架構與資料庫模型；審查後端程式碼品質 |
| `data_lead` | 資料主管 | 資料 | `reasoning` | 制定資料資產與分析策略；審查管線品質、指標定義與倉儲設計 |
| `frontend_lead` | 前端主管 | 前端邏輯 | `reasoning` | 制定前端架構與技術選型（React/Vue/框架選擇）；審查 UI/JS/CSS 交付物品質 |
| `tactical_commander` | 戰術指揮官 | 管理 | `reasoning` | 把 L4 戰術指令 JSON 拆成原子級 DAG，禁止模糊節點；為每個原子任務親手孵化 <200 Token 的 L2 執行者 |
| `test_lead` | 測試主管 | 測試 | `routine` | 制定測試策略（單元/整合/E2E）；審查測試案例覆蓋率 |

## Level 3：執行層（55）

| ID | 名稱 | 分類 | 預算層 | 主要職責 |
|----|------|------|--------|----------|
| `accessibility_eng` | 無障礙工程師 | UI 設計 | `routine` | 檢查對比、鍵盤操作與讀屏標籤；產出 WCAG 修復清單 |
| `api_engineer` | API 契約工程師 | 後端 | `reasoning` | 維護 OpenAPI 欄位、錯誤碼與相容性；檢查 Request/Response Header 與邊界條件 |
| `atomic_executor` | 原子執行者 | 管理 | `routine` | 執行前強制戰前檢查清單；不通過即向 L3 發結構化 [GRILL]；一次一動、沉默運作，只交付 Output Schema 定義的產出 |
| `backend_dev` | 後端開發者 | 後端 | `routine` | 實作 RESTful API 端點與業務邏輯；設計資料庫 schema 與查詢優化 |
| `billing_ops` | 計費運維 | AI Hub | `routine` | 核對用量、發票與異常扣款；對齊角色日預算與 Hub 攔截 |
| `cache_engineer` | 快取工程師 | 維運 | `reasoning` | 設計 Key、TTL 與失效；追蹤命中率與雪崩 |
| `chaos_eng` | 混沌工程師 | 維運 | `reasoning` | 設計故障注入實驗；驗證超時、重試與熔斷 |
| `cloud_architect` | 雲架構師 | 維運 | `critical` | 規劃帳號、網路與身分；估算成本與備援 |
| `conversation_designer` | 對話設計師 | AI / Prompt | `reasoning` | 設計意圖、槽位與降級話術；處理拒答與敏感話題 |
| `copy_editor` | 文案編輯 | 創意／敘事 | `summary` | 校對語氣、錯字與品牌用詞；統一繁中用詞 |
| `crawler` | 爬蟲工程師 | 爬蟲／採集 | `routine` | 設計 LittleCrawler 採集任務與選擇器；處理反爬、重試、去重與速率限制 |
| `css_dev` | CSS 開發者 | 樣式 | `routine` | 根據 UI 設計稿實作樣式（CSS/SCSS/Tailwind）；確保響應式設計（RWD）與跨瀏覽器相容 |
| `customer_success` | 客戶成功 | 成長／客戶成功 | `summary` | 追蹤健康度與升級條件；把回饋轉成需求或缺陷 |
| `data_engineer` | 資料工程師 | 資料 | `routine` | 設計 ETL / ELT 管線與資料品質檢查；建置倉儲模型與批次／串流作業 |
| `data_scientist` | 資料科學家 | 資料 | `reasoning` | 提出可驗證假設與實驗設計；解釋模型與業務指標關係 |
| `dba` | 資料庫管理員 | 資料 | `routine` | 設計 schema、索引與遷移；規劃備份、還原與權限 |
| `developer` | 通用開發者 | 後端 | `routine` | 執行被指派的工作項，產出高品質的交付物；遇到阻塞時主動回報，請求協助 |
| `devops` | 維運工程師 | 維運 | `routine` | 設定 CI/CD 管線；管理部署環境（Docker、K8s） |
| `eval_engineer` | 評測工程師 | AI / Prompt | `reasoning` | 建立基準集、回歸閘與紅隊題；對比模型成本與品質 |
| `feature_flag_eng` | 功能開關工程師 | 後端 | `routine` | 設計灰度、受眾與回滾；避免旗標永久化 |
| `github_ops` | GitHub 工程師 | 平台／GitHub | `routine` | 整理 PR、Issue、檢查狀態與分支保護；同步本地倉庫更新與遠端差異 |
| `hub_operator` | Hub 值班 | AI Hub | `routine` | 監控模型池延遲、熔斷與預算；依路由策略建議切換或降級 |
| `incident_cmd` | 事故指揮官 | 維運 | `reasoning` | 事故分級、溝通與時間線；協調緩解與事後檢討 |
| `integration_eng` | 整合工程師 | 後端 | `reasoning` | 對接外部 API 與 Webhook；處理冪等、重試與簽名 |
| `iot_engineer` | IoT 工程師 | 工業／OPC | `routine` | 規劃邊緣裝置與協定；處理斷線緩存與韌體版本 |
| `js_dev` | JS 開發者 | 前端邏輯 | `routine` | 實作前端互動邏輯（事件處理、狀態管理、API 串接）；開發可複用元件（React/Vue 元件） |
| `load_tester` | 負載測試工程師 | 測試 | `reasoning` | 設計負載模型與飽和點；量測 p95/p99 與錯誤率 |
| `market_data_eng` | 行情工程師 | 金融／量化 | `routine` | 檢查 Yahoo／東方財富／新浪／Stooq 行情時效、欄位與異常值；對齊幣別、復權與交易時段 |
| `ml_engineer` | 機器學習工程師 | AI / Prompt | `reasoning` | 設計特徵、訓練與推論服務；標明資料切分、指標與偏差 |
| `mlops` | MLOps 工程師 | AI / Prompt | `reasoning` | 部署模型、監控漂移與回滾；管理特徵商店與推論 SLA |
| `mobile_dev` | 行動開發者 | 行動端 | `routine` | 實作 iOS / Android / 跨平台介面與導航；處理離線快取、推播與裝置權限 |
| `narrative_editor` | 敘事編輯 | 創意／敘事 | `reasoning` | 審查情節節奏、角色一致性與對白；對齊 StoryForge 章節與世界觀 |
| `observability_eng` | 可觀測性工程師 | 維運 | `reasoning` | 設計 Tracing ID、指標與告警門檻；對齊 Jaeger/日誌與監控中心面板 |
| `opc_engineer` | OPC 工業工程師 | 工業／OPC | `reasoning` | 讀取 OPC 標籤、診斷品質與越界；擬定寫入建議並通過護欄檢查 |
| `pen_tester` | 滲透測試工程師 | 資安 | `reasoning` | 盤點攻擊面與優先序；驗證認證、注入與越權 |
| `perf_eng` | 效能工程師 | 維運 | `reasoning` | 量測延遲、吞吐與資源瓶頸；提出快取、查詢與前端渲染優化 |
| `plc_engineer` | PLC 工程師 | 工業／OPC | `reasoning` | 設計連鎖與安全回路；對齊 OPC 標籤與寫入護欄 |
| `portfolio_mgr` | 投資組合經理 | 金融／量化 | `reasoning` | 配置權重與再平衡規則；檢查集中度與上限 |
| `privacy_officer` | 隱私長 | 合規 | `reasoning` | 盤點個資欄位與留存；檢查出境與最小化 |
| `product_designer` | 產品設計師 | 產品 | `reasoning` | 設計使用者旅程與資訊架構；把角色工作台拆成可完成的畫面 |
| `qa_automation` | 自動化 QA | 測試 | `routine` | 撰寫 E2E / 回歸閘；穩定選擇器與重試策略 |
| `quant_analyst` | 量化分析師 | 金融／量化 | `reasoning` | 拉取行情、估值與基本面（market_quote／market_fundamentals）；以 market_strategy_catalog 選策略，必要時用 archify_strategies 看工作流，再用 market_kl… |
| `rag_engineer` | RAG 工程師 | AI / Prompt | `reasoning` | 設計切片、嵌入與重排；檢查檢索命中與引用 |
| `release_eng` | 發布工程師 | 平台／GitHub | `reasoning` | 準備版本號、變更紀錄與發布清單；檢查遷移、設定與回滾步驟 |
| `risk_analyst` | 風險分析師 | 金融／量化 | `reasoning` | 評估倉位、情境與最大回撤；可用 market_backtest／market_compare／market_watch 核對回撤與預警 |
| `router_eng` | 路由工程師 | AI Hub | `reasoning` | 調整權重、故障轉移與競速；大陸 IP 強制國內模型 |
| `security_eng` | 資安工程師 | 資安 | `reasoning` | 檢查認證授權、注入與敏感資料外洩；撰寫防護清單與修復建議 |
| `sentiment_analyst` | 情緒分析師 | 金融／量化 | `routine` | 整理新聞／社群事件衝擊；區分事實、傳聞與情緒 |
| `sre` | 可靠性工程師 | 維運 | `routine` | 定義 SLO / 錯誤預算與告警；處理事故、容量與降級策略 |
| `story_writer` | 故事創作者 | 創意／敘事 | `reasoning` | 撰寫情節、對白與角色弧線（StoryForge）；維持世界觀與語氣一致性 |
| `tech_writer` | 技術文件工程師 | 文件 | `summary` | 撰寫 API 文件、操作手冊與架構說明；整理錯誤碼與故障排除步驟 |
| `tester` | 測試工程師 | 測試 | `routine` | 撰寫測試案例（單元測試、整合測試、E2E 測試）；執行手動測試與自動化測試 |
| `translator` | 在地化專員 | 文件 | `summary` | 將介面與文件轉為自然繁中或其他語系；維持術語表與語氣一致 |
| `ui_designer` | UI 設計師 | UI 設計 | `routine` | 設計頁面視覺佈局與線框圖（wireframe）；產出 UI 元件設計稿與互動原型 |
| `ux_researcher` | UX 研究員 | 產品 | `routine` | 規劃可用性測試與訪談大綱；整理痛點、任務成功率與改進假設 |

## Level 4：支援角色（14）

| ID | 名稱 | 分類 | 預算層 | 主要職責 |
|----|------|------|--------|----------|
| `analyst` | 分析師 | 資料 | `routine` | 研究、分析與收集資料；提供數據驅動的見解與建議 |
| `constitutional_inspector` | 憲兵審查官 | 審查 | `reasoning` | 獨立四維度驗收 L2 產出（結構合規／語義完整／事實一致／極限邊界）；禁止同理心與跨級代勞：只指出錯誤並要求重做，不得幫忙改完 |
| `content_writer` | 內容撰寫 | 文件 | `summary` | 撰寫對外文案、報告敘事與摘要；統一語氣與讀者對象 |
| `coordinator` | 協調者 | 管理 | `routine` | 跨角色溝通，解決協作瓶頸；處理工作項阻塞，協調解除依賴 |
| `environment_kernel` | 環境與記憶核心 | 記憶／知識庫 | `summary` | 壓縮對話與任務軌跡，抽出決策點與教訓（STM／MTM／LTM）；檢索知識實體與合規指南，強制注入 L4／L3／L1 決策上下文 |
| `knowledge_mgr` | 知識庫管理員 | 記憶／知識庫 | `summary` | 維護 runbook、FAQ 與術語表；把完成的工作項沉澱成可重用知識 |
| `legal` | 合規審查 | 合規 | `reasoning` | 檢查個資、授權與敏感內容；標示資料出境與留存風險 |
| `memory_curator` | 記憶庫策展 | 記憶／知識庫 | `routine` | 整理向量記憶、去重與過期策略；檢查檢索命中是否與任務相關 |
| `prompt_engineer` | Prompt 工程師 | AI / Prompt | `reasoning` | 設計角色系統提示與評估標準；規劃模型路由、故障轉移與成本權衡 |
| `requirement_auditor` | 需求審計官 | 審查 | `reasoning` | 以零信任審查使用者需求，禁止確認偏誤與模糊妥協；依五維評分（具體性／邊界／約束／風險／成功定義）決定是否放行 |
| `researcher` | 研究員 | 研究 | `reasoning` | 蒐集文獻、競品與領域背景；提出可驗證的假設與實驗設計 |
| `reviewer` | 審查者 | 審查 | `reasoning` | 在 L1 憲兵簽核之後做第二道品質審查；提供具體、可執行的回饋 |
| `support` | 支援專員 | 產品 | `summary` | 整理工單、FAQ 與使用者回饋；把問題轉成可指派的缺陷或需求 |
| `synthesizer` | 整合者 | 審查 | `reasoning` | 合併多個工作項的交付物為統一的最終產出；解決不同交付物之間的矛盾與重複 |

## 組織模板（8）

| 模板 ID | 名稱 | 適用 | 核心角色 |
|--------|------|------|----------|
| `page_dev` | 頁面開發團隊 | 頁面／Mobile 前後端＋測試 | `architect`、`backend_dev`、`backend_lead`、`css_dev`、`frontend_lead`、`js_dev`、`manager`、`synthesizer` 等 12 席 |
| `fullstack_app` | 全端開發團隊 | 全端開發＋審查 | `backend_dev`、`backend_lead`、`constitutional_inspector`、`css_dev`、`frontend_lead`、`js_dev`、`manager`、`reviewer` 等 11 席 |
| `research_report` | 研究報告團隊 | 研究調查與報告 | `analyst`、`constitutional_inspector`、`content_writer`、`manager`、`researcher`、`reviewer`、`synthesizer` |
| `quick_task` | 快速任務團隊 | 單一任務、成本最低 | `developer`、`manager` |
| `full_company` | EvoLoop 完整公司 | 全席啟用 | `accessibility_eng`、`ai_lead`、`analyst`、`api_engineer`、`architect`、`atomic_executor`、`backend_dev`、`backend_lead` 等 85 席 |
| `quant_desk` | 量化研究桌 | 行情／回測／組合 | `analyst`、`constitutional_inspector`、`finance_lead`、`manager`、`market_data_eng`、`portfolio_mgr`、`quant_analyst`、`researcher` 等 12 席 |
| `industrial_ops` | 工業運維團隊 | OPC／PLC／IoT | `constitutional_inspector`、`industrial_lead`、`iot_engineer`、`manager`、`opc_engineer`、`plc_engineer`、`reviewer`、`security_eng` 等 10 席 |
| `story_studio` | 故事工作室 | 敘事／世界觀／可調 MCP | `constitutional_inspector`、`content_writer`、`copy_editor`、`creative_lead`、`manager`、`narrative_editor`、`reviewer`、`story_writer` 等 10 席 |

> Minecraft 建造／靈境任務在預設 `quick_task` 時會改走 `story_studio`，以免只有 `developer` 卻無權放方塊。

## 靈境子角色（16）

由 `seed_linkin_roles()` 冪等寫入 `role_catalog`（ID 前綴 `custom_linkin_*`）。
四部門 ×（總監＋執行者＋審查員＋記錄員）。

| 部門 | 總監 ID | 執行者 | 審查員 | 記錄員 | 工具重點 |
|------|---------|--------|--------|--------|----------|
| 建築（塑形） | `custom_linkin_build_director` | `…_build_executor` | `…_build_reviewer` | `…_build_scribe` | `BuilderAI.generate`＋MCP 建造；總監另可 `execute_command` |
| 敘事（言靈） | `custom_linkin_narrative_director` | `…_narrative_executor` | `…_narrative_reviewer` | `…_narrative_scribe` | `Quest.generate`＋讀玩家狀態 |
| NPC（共鳴） | `custom_linkin_npc_director` | `…_npc_executor` | `…_npc_reviewer` | `…_npc_scribe` | `NPC.create/dialogue`＋讀玩家狀態 |
| 道具（賦形） | `custom_linkin_item_director` | `…_item_executor` | `…_item_reviewer` | `…_item_scribe` | `Item.create`；無 Minecraft 寫入工具 |

世界觀憲法為最高裁決；工具鐵律見 [Minecraft MCP](../linkin/minecraft-mcp.md) · [世界觀](../linkin/worldview.md)。

## 開發者怎麼改角色

| 需求 | 作法 |
|------|------|
| 改內建席 Prompt／職責 | 編輯 `backend/company/roles.py` 對應 `ROLE_*`，補測試 |
| 執行期覆寫／自定義席 | 監控中心或 `role_catalog` API；檔案 `backend/data/role_catalog.json` |
| 新增組織模板 | 在 `roles.py` 加 `create_*` 並掛進 `BUILTIN_TEMPLATES` |
| 靈境 16 席 | `backend/linkin/roles.py`＋`prompts.py`，啟動時冪等刷新 |
| 禁止事項 | 勿讓角色直連 MineMCP／檔案系統工具；LLM 一律 `call_llm` |

## 相關入口

- [公司運行時](../architecture/company-runtime.md) · [目錄地圖](../structure.md) · [新人導覽](../onboarding.md)
- 程式：`backend/company/roles.py` · `role_catalog.py` · `backend/linkin/roles.py`
