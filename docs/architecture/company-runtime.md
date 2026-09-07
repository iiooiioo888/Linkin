# 公司運行時

複雜任務自動觸發多代理人公司運行時：**Manager 分解 → 多角色並行執行 → Reviewer 審查 → Synthesizer 整合**。

## 觸發條件

任務被判定為「複雜」時自動啟用：

- 查詢長度 ≥ 200 字符
- 包含關鍵詞：開發、設計、構建、實現、系統、架構、重構、deploy、build、implement 等
- 執行策略顯式設為 `company`

## 角色體系

內建 `STANDARD_ROLES` 共 **80** 席（Level 0–4）。監控中心可覆寫角色設定，或透過 `role_catalog` 新增自定義角色。

```
Level 0: Manager（1）           — 目標分解、最終審查
Level 1: Lead（10）             — 技術／架構／資安／產品／財務／工業／創意／平台／AI／成長
Level 2: Domain Lead（4）       — 前端／後端／測試／資料主管
Level 3: Executor（54）         — 具體任務執行（含 OPC／RAG／GitHub Ops／Hub 等）
Level 4: Support（11）          — 審查、整合、Prompt、法務、記憶策展、知識庫…
```

角色設定（Prompt、偏好模型、預算、工具）持久化於 `EVOL_ROLE_CATALOG_PATH`（預設 `backend/data/role_catalog.json`）。偏好模型一律經 `clamp_model` 鎖在當前 API 可用池內。

## 組織模板

| 模板 | 適用場景 | 角色配置 |
|------|----------|----------|
| `quick_task` | 快速任務 | 精簡團隊 |
| `page_dev` | 頁面開發 | 前端為主 |
| `fullstack_app` | 全端開發 | 完整團隊 |
| `research_report` | 研究報告 | 研究為主 |
| `story_studio` | 情節／世界觀／Minecraft 建造 | manager／creative_lead／story_writer 可調用 MCP |
| `full_company` | 完整公司 | 全角色啟用 |

## Minecraft MCP 工具

公司角色透過 `tool_registry` 的 ReAct `tool_call` 區塊呼叫 `backend/tools/minecraft_mcp.py`（JSON-RPC → MineMCP）。寫入工具僅 manager／creative_lead／story_writer／`custom_linkin_build_*` 可用；`execute_command` 另限建築總監。未設定 `EVOL_MC_MCP_TOKEN` 時乾跑，不寫入世界。Minecraft 控制查詢與靈境建造任務在預設 `quick_task` 時會改走 `story_studio`，避免只有 developer 執行卻無權放方塊。詳見 [Minecraft MCP](../linkin/minecraft-mcp.md)。

## 量化行情工具

金融／研究角色透過同一套 `tool_call` 呼叫 `backend/company/quant_tools.py`（Yahoo 主源，A 股可備援東方財富／新浪；外匯 Frankfurter；加密貨幣 CoinPaprika／CoinGecko／Binance；可選 Tushare／Finnhub／Alpha Vantage）。工具含報價、分鐘線、31 策略回測（含增強成交量／單成交量）、策略庫目錄、網格優化、Walk-Forward、訊號投票、11 種組合與基準對比。實驗室「策略庫」分類樹（`GET /lab/quant/strategies`）供瀏覽與複製 tool_call；「策略圖」（`GET /lab/archify/strategies`）用 Archify 可視化全部策略，角色可 `archify_strategies`。不嵌入 stock-quant 完整工作站。詳見 [量化行情工具](../company/quant-tools.md)。

## 執行流程

```
階段 1: TaskDecomposer 分解目標
  │  三策略：LLM / 模板 / 規則（預算壓力下自動降級）
  ▼
工作項 DAG（依賴 + 優先級排序）
  │
  ▼
階段 2: 執行-審查迴圈
  │  並行執行池（Semaphore 限流，自適應並發）
  │  Developer 角色依優先級執行
  ▼
Reviewer 審查閘
  ├─ ✅ 通過 → Done
  └─ ❌ 不通過 → Rework（最多 N 輪，失敗後角色升級）
  ▼
階段 3: Synthesizer 整合
  │
  ▼
階段 4: Manager 最終審查
  │
  ▼
外部反思迴圈（評估 → 反思 → 改進）
```

## 工作項狀態機

```
Planning → Ready → Executing → In Review → Done
                        ↑           │
                        └─ Rework ──┘
                                    │
                              Blocked（失敗）
```

## 預算管控

### 模型路由

根據任務複雜度和預算壓力自動選擇模型：

| 層級 | 適用場景 | 預設模型 |
|------|----------|----------|
| `SUMMARY` | 低複雜度 | gpt-4o-mini |
| `ROUTINE` | 中複雜度 | gpt-4o-mini |
| `REASONING` | 高複雜度 | gpt-4o |
| `CRITICAL` | 關鍵任務 | gpt-4o |

### 預算壓力

```
壓力 = max(任務花費/任務上限, 會話花費/會話上限, 月度花費/月度上限)
```

- 壓力 < 警告閾值：正常運行
- 壓力 ≥ 警告閾值：日誌警告 + 建議優化
- 壓力 ≥ 降級閾值：自動切換到便宜模型
- 壓力 ≥ 1.0：硬停止

### Docker 容器成本

類似雲端按量付費：`費用 = 小時費率 × 運行時長`，計入月度預算。

## 自適應並發控制（優化 #6）

根據 API 響應動態調節並行數：

```
有 429 錯誤 → 並發數 - 1
響應穩定（< 5s）→ 並發數 + 1
上限：配置值的 2 倍
調整週期：30 秒
```

## 錯誤回退（優化 #2）

公司運行時失敗時的降級策略：

```
成功 → evaluate_answer（進入反思迴圈）
失敗但有部分產出（> 50 字）→ evaluate_answer（嘗試反思修復）
失敗且無產出 → archive_state → END
```

## 事件系統

17 種生命週期事件，非阻塞 EventBus：

```
公司層級：COMPANY_START · COMPANY_DONE · PHASE_CHANGE · DECOMPOSE_DONE
工作項層級：WORK_ITEM_START · WORK_ITEM_DONE · WORK_ITEM_ERROR · WORK_ITEM_RETRY · WORK_ITEM_ESCALATE
工具層級：TOOL_CALL · TOOL_RESULT
審查層級：REVIEW_PASS · REVIEW_REWORK · REVIEW_FORCE_DONE
降級層級：FINAL_REVIEW_DEGRADED · BUDGET_WARNING · BUDGET_DEGRADE
```

## 檢查點

支持中斷恢復：

```python
# 序列化
checkpoint = orchestrator.to_checkpoint(goal)

# 恢復
orchestrator = CompanyOrchestrator.from_checkpoint(checkpoint)
```

包含：所有工作項狀態、預算、日誌、run_id。
