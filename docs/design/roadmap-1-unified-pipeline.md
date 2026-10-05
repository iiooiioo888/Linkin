# 路線圖 #1：三軌管線收斂 — 設計提案

| 項目 | 內容 |
| --- | --- |
| 狀態 | **已核准**（P0 可開工；實作依分階段 PR 交付） |
| 核准日期 | 2026-10-05（PM） |
| 基線 commit | `fdeb619`（`master`，已含 #6 `POST /routing/preview`、#7 輪次對齊相關合併） |
| 範圍 | `POST /chat`、`POST /chat/stream`（含公司／minecraft_ops 分支）、`POST /tasks` + Task WebSocket |
| 非目標 | AI Hub `/api/v1/*`、OPC 微服務內部六級圖、前端 Grill 產品邏輯重寫 |

## 1. 問題與目標

三個產品入口各自維護「前置增強 → 生成 → 反思閉環 → 收尾」，只有 `POST /chat` 完整走 `build_graph().ainvoke`；其餘為手抄迴圈或旁路編排。結果是**同一句 query** 可能出現：路徑標籤一致但注入上下文不同、反思輪數或終止條件不同、交付前長度／質量門不同、trace 覆蓋不全。

**驗收目標（實作階段）**

- 同一 query（含 `semantic_lock.locked_brief`）在三入口的 `path`、注入上下文、反思輪數上限與實際 `iteration` 一致（允許串流在 token 切分上與 batch 字串相同）。
- 既有測試全過；新增契約測試鎖死上述一致性。
- **TTFT** 驗收分兩類（詳 §7）：未命中 OPC／靈境增強的 query **零回歸**；命中者採 **並行＋超時降級**（§7.4(b)，已決）。

---

## 2. 現況盤點（三入口對照）

```mermaid
flowchart LR
  subgraph graph["POST /chat → evoloop_graph.ainvoke"]
    RM[retrieve_memories] --> OPC[enhance_with_opc_context]
    OPC --> LK[enhance_with_linkin_context]
    LK --> RC[enhance_with_recall_context]
    RC --> RT[route_by_complexity]
  end
  subgraph sse_simple["POST /chat/stream simple"]
    PR[path_resolved] --> RM2[retrieve_memories]
    RM2 --> RC2[enhance_recall_context]
    RC2 --> GEN[call_llm_stream + 手抄反思]
  end
  subgraph task_simple["POST /tasks simple"]
    PR2[path_resolved] --> RM3[retrieve_memories]
    RM3 --> OPC3[enhance_opc_context]
    OPC3 --> LK3[enhance_linkin_context]
    LK3 --> RC3[enhance_recall_context]
    RC3 --> G3[generate_initial_answer + 手抄反思]
  end
```

### 2.1 對照表

| 能力 | `POST /chat` | `POST /chat/stream` | `POST /tasks` + WS |
| --- | --- | --- | --- |
| **路由** | `route_by_complexity`（`company_nodes.py` L101–134） | `build_routing_preview` + 分支（`main.py:chat_stream` L1275+） | `build_routing_preview`（`task_manager.py:_run_unified_task` L694–709） |
| **OPC 注入** | 圖節點 async | simple：**缺** ⚠️ | 有 |
| **靈境 RAG** | 圖節點 | simple：**缺** ⚠️ | 有 |
| **recall** | 圖節點 | 有 | 有 + `recall_assembled` |
| **反思迴圈** | `should_improve` | `reflection_should_continue`（simple）；公司 SSE 仍用 `PASS_THRESHOLD` ⚠️ | `_run_reflection_loop` |
| **收尾** | decide → enforce_final → save → archive | simple：僅 `save_memory` ⚠️ | `finalize_task_answer` |
| **`record_outcome`** | `decide_final_answer`（`nodes.py` L569–583） | **無** ⚠️ | 經 finalize |
| **Billing** | **無** `begin_chat_billing`（`main.py:chat` L941–966）— **今日同步 chat 未走 chat 計費上下文**（見 §5.2） | `begin_chat_billing` + `event: billing` | `begin_billed_task`、402 |
| **客戶端中斷** | N/A | **無**協作式 cancel ⚠️（§3.5） | `cancel_task` + grace |

### 2.2 關鍵分歧

1. Simple SSE 缺 OPC／靈境（P1）。
2. OPC 六級僅 Task（Q1）。
3. 公司 SSE 反思常數與 graph 分叉（P2）。
4. SSE 無 finalize／`record_outcome`（P2）。
5. 串流 disconnect 未停 LLM／未 skip save（§3.5）。

---

## 3. 目標架構：`run_unified_pipeline`

### 3.1 原則

單一編排核心（圖或同拓撲 `run_pipeline_stages`）；HTTP／Task 只訂閱 `PipelineEvent`；simple 路徑允許 `token_sink`，反思仍用 `nodes.*` 同步節點。

### 3.2 介面（摘要）

`run_unified_pipeline(req: PipelineRequest, mode=BATCH|STREAM|TASK, emit=…, token_sink=…)` → `EvoLoopState`。`mode=stream`：company 保留 EventBus；minecraft_ops 用 `ainvoke`；simple 用共用前置 + stream 生成 + 共用反思。

### 3.3 串流選型

採 **混合 B**（非全圖 `astream_events`），避免評估節點阻塞首 token。P1 後 TTFT 瓶頸在 **前置增強 I/O**（§7），不在 LangGraph 編譯。

### 3.4 分階段 Feature Flag（取代單一總開關）

**問題**：單一 `EVOL_UNIFIED_PIPELINE=1` 會把「改答案的 P1」與「改反思／收尾的 P2」「改同步入口的 P3」捆在一起，無法在 prod 獨立試水溫。

**提案**：環境變數 `EVOL_UNIFIED_PIPELINE`，取值：

| 值 | 啟用階段 | 預設 | Prod 開啟需 PM 簽核 |
| --- | --- | --- | --- |
| `off`（或空） | 全關 | **是** | — |
| `pre` | P1：SSE simple 跑共用 `run_pre_route_enhancements`（OPC+Linkin+順序與 Task 一致） | 否 | **是**（改回答、改 TTFT） |
| `reflect` | P2：`reflect` 含 P1；共用 `run_reflection_phases` + finalize + 公司 SSE 對齊 | 否 | **是**（改 iteration／長度交付） |
| `batch` | P3：`batch` 含 P2；`POST /chat` 走 `run_unified_pipeline(BATCH)` | 否 | **是**（計費行為待 Q7 用戶確認後實作，見 §6） |
| `full` | P4：清理死碼、可選前置並行、bench 進 CI | 否 | 工程內部 |

實作細節：`unified_pipeline.py` 內 `pipeline_level() -> Literal["off","pre","reflect","batch","full"]`，各入口只讀一次。

P0 僅引入旗標解析與契約測試，**行為等同 `off`**。

### 3.5 串流模式：客戶端斷開與中止（與 Task cancel 對齊）

**現況**：`event_stream` 在 `finally` 呼叫 `end_chat_billing`（`main.py` L1551–1552），但生成執行緒 `run_in_executor(_produce_tokens)` **不會**因客戶端斷開而停止；`save_memory` 在完整迴圈結束後仍可能執行；無 `record_outcome` 中斷語意。

**目標行為**（`run_unified_pipeline(STREAM)` 實作要求）：

```text
客戶端關閉 SSE / ASGI disconnect
  → 設 pipeline_cancelled（asyncio.Event）
  → 取消 token 生產 Future / 向 call_llm_stream 注入可中止 hook（與 Task 強制 cancel 同級意圖）
  → 反思迴圈每輪開頭檢查 cancelled：跳過 reflect/improve/evaluate
  → 不呼叫 save_memory、不呼叫 decide_final_answer/record_outcome（或 record 標記 aborted，見下）
  → billing：end_chat_billing 前將 snapshot 標 interrupted=True、reason=client_disconnect；已 meter 的 LLM 調用保留（與 Task 取消一致）
  → 可選 emit event: error code=CLIENT_DISCONNECT（非必須，客戶端已離線）
```

與 Task 對照：`cancel_requested` + `CANCEL_GRACE_SECONDS`（`task_manager.py` L524–557）→ 串流用 **即時** disconnect 偵測（Starlette `request.is_disconnected()` 或 `asyncio.CancelledError` on send）。

**測試**：mock disconnect 在首 token 後／反思中 assert `save_memory` 未呼叫、`record_outcome` 未呼叫、`chat_billing_snapshot()["interrupted"]` 為真。

---

## 4. 分階段實施計畫

| 階段 | 範圍 | 旗標 | 測試 | 工作量 |
| --- | --- | --- | --- | --- |
| **P0** | 骨架 + `pipeline_level()` + 契約測試 | `off` | path/complexity/max rounds | **S（~2–3 人日）** |
| **P1** | 共用前置增強；SSE 接入；**B2 並行+超時**（cost_speed 300ms）；`degraded` 事件／trace | `pre` | 注入探針 + §7.4(a)(b) | **M（~4–5 人日）** |
| **P2** | 反思／finalize 單源；串流 **單次** `record_outcome`；串流 cancel；**PR 附 company 佔比影響** | `reflect` | 見 §9 + 全量 `pytest backend/tests/` | **M（~5–6 人日）** |
| **P3** | `/chat` batch 包裝 + 響應元資料；（計費僅在 Q7 用戶確認後） | `batch` | 同步響應契約；billing 用例 **條件執行** | **S（~2–3 人日）** |
| **P4** | 死碼清理、前置可選 gather、CI bench | `full` | 同程 TTFT 回歸 | **S（~2 人日）** |

**總工作量估算**：約 **15–19 人日**（含測試與文檔；不含 Q1 長期 OPC 語意統一）。

**合併與送審約定（PM）**

- **每個階段（P0–P4）各開一個 PR**，獨立送審；不得把多階段混在同一 PR（除非明確標為 follow-up 且前一階段已合併）。
- **合併前必須在本機跑完全量測試**：`pytest backend/tests/`（與 CI 同等範圍）；PR 描述需註明已執行。
- P2 PR **必須**附一段說明：啟用串流 `record_outcome` 後，對 `routing_feedback` 樣本量與 `max_company_ratio`（`cost_speed.json` → `routing_feedback.max_company_ratio`，預設 0.35）護欄的**預期影響**（見 §5.1、§5.3）。

---

## 5. 對外 API 行為變更

### 5.1 `POST /chat/stream`（simple）

| 變更 | 分類 |
| --- | --- |
| 新增 OPC／Linkin 前置 phase（P1） | 非 breaking（事件） |
| 命中 OPC／靈境時 **答案變化** | 語意 breaking |
| P2：`finalize_task_answer` 鏈 | 可能改交付長度 |
| P2：每請求 **一次** `record_outcome`（經 `decide_final_answer`）；**含串流 simple**（PM 已准） | **行為／數據（內部）**：#9 樣本量上升；P2 PR 須書面說明對 **company 佔比上限** 的預期（非對外 API breaking） |
| P2：客戶端斷開不再保證 `done`／`save_memory` | 非 breaking（客戶端已離線） |

### 5.2 `POST /chat`（同步）— Billing（**Q7**）

| 現況 | P3 若走 unified batch 的兩種產品選項 |
| --- | --- |
| **今日未計量展示**：無 `begin_chat_billing`、響應無 `billing` 欄位；與 `/chat/stream` 不一致 | **A. 維持不計量**：batch 仍直接 `ainvoke`，僅代碼路徑統一，**無** 402／無 `billing` 欄位 |
| | **B. 與 SSE 對齊計量**：batch 包裝內 `begin_chat_billing`；超限 402 或響應帶 `billing` — **API breaking** |

**已決（Q7）**：P0–P2 **不變更**同步 `/chat` 計量行為。P3 **開工前** PM 須向**終端用戶**確認是否採用計量；在此之前實作一律按 **方案 A**（不 `begin_chat_billing`、無 402、響應無 `billing`）。用戶確認後若選 B，另開產品／API 變更說明。

### 5.3 `record_outcome`（P2，§5.1 已述）

- 僅在成功走完 `decide_final_answer` 且未 `pipeline_cancelled` 時呼叫 **一次**。
- `finalize_task_answer` 與 graph `decide_final_answer` 共用實作；Task 路徑不得再額外 `record_outcome`。
- **測試**：`test_record_outcome_once_per_request` — mock `record_outcome`，SSE／Task／batch 各一請求，assert `call_count == 1`；disconnect 案例 assert `call_count == 0`。

### 5.4 其他入口

（Company SSE 反思、Task 事件名、OPC 六級 Q1、前端適配 — 同 v1 §5.2–5.5。）

### 5.5 Breaking 清單（已核准範圍）

1. P1：Simple 串流 OPC／靈境 query 答案與現網不同（超時降級時可能與 `/chat` 短暫不一致，見 §7.4(b) `degraded`）。  
2. P2：極長答案交付行為可能變化（與 `/chat` 對齊）。  
3. P3（**僅當** Q7 用戶確認後採方案 B）：同步 `/chat` 可能 402 或出現 `billing` — **目前不適用**。  
4. ~~OPC 六級廢止~~ → **暫不適用**（Q1：Task 六級保留，見 §6）。

---

## 6. 決策紀錄（PM 核准）

### 6.1 已決策

| # | 決策 |
| --- | --- |
| **Q1** | **短期維持現狀並寫入運維／產品說明**：`path=opc` 時 Task 仍走 **OPC 六級**，不廢止；`/chat` 圖與 SSE 仍為「注入 + simple 生成」。**長期**是否與 graph 完全一致 → **P3 開工前再議**，不阻塞 P0–P2。 |
| **Q2** | 串流採混合 **B**（非全圖 `astream_events`）。 |
| **Q3** | **同意**：Task `options.auditor_ticket`（及既有 `semantic_brief`）映射進 `PipelineRequest.semantic_lock`（與 Chat `semantic_lock` 同形）。 |
| **Q7** | P0–P2 **不碰**同步 `/chat` 計量。P3 實作前 PM **向用戶確認**；確認前一律 **方案 A**（不計量、無 402）。 |
| **Q8** | 採 **B2：並行＋超時**（見 §7.4(b)）。超時則**跳過**該次 OPC／Linkin（及可並行的 recall 子步）注入，**不硬等**；須標記 **`degraded`**。 |

**Q8 配置**：前置增強總等待上限寫入 `backend/config/cost_speed.json`（支援熱重載，與其他路由參數一致），建議鍵：

```json
"unified_pipeline": {
  "pre_enhance_timeout_ms": 300
}
```

預設 **300 ms**。實作時由 `cost_speed_router` 或同檔讀取；環境變數僅作覆寫（可選，如 `EVOL_PRE_ENHANCE_TIMEOUT_MS`）。

**`degraded` 可見性（必做）**

| 出口 | 欄位 |
| --- | --- |
| `event: path_resolved` | `context_degraded: true`，`degraded_sources: ["opc"\|"linkin"\|"recall", …]`（命中逾時的源） |
| `event: done`（及 Task `task_finished`） | 同上，便於前端／任務列表展示 |
| Trace | `TraceLogger.log_custom("pre_enhance_degraded", {sources, timeout_ms, elapsed_ms})`；`pipeline_trace.log_node` 附 `degraded` |

### 6.2 實作期仍須工程對齊（非 PM 待決）

| # | 說明 | 階段 |
| --- | --- | --- |
| **Q4** | 公司 SSE 保留 `CompanyOrchestrator`，反思收尾走共用 helper | P2 |
| **Q5** | 串流 billing 事件時機與現 `begin_chat_billing` 一致 | P2 |
| **Q6** | P2 合併後禁止新增圖外反思 while | P2+ |

### 6.3 開工與上線節點

| 里程碑 | 條件 |
| --- | --- |
| **P0 開工** | 本文件已核准（已滿足） |
| **P1 prod（`pre`）** | Q8 實作 + §7 驗收 + PM 運維知悉 `degraded` 文案 |
| **P2 prod（`reflect`）** | P2 PR 含 company 佔比影響說明 + 全量測試 |
| **P3 開工** | Q1 長期 OPC 再議結論（可與 P3 範圍分離）+ **Q7 用戶確認**完成 |

---

## 7. TTFT 量測與驗收（修訂）

### 7.1 定義

- **TTFT**：`POST /chat/stream`（`execution_strategy=simple`，`path` 為 simple）從請求發出到第一個 `event: token`（ms）。
- **前置窗**：`path_resolved` 之後至首 token 之前所有同步／await 階段（含 P1 新增的 OPC／Linkin）。

### 7.2 增強器成本分析（讀碼結論）

| 節點 | 關鍵字／條件門控 | I/O | Embedding / RAG | LLM |
| --- | --- | --- | --- | --- |
| **`enhance_with_opc_context`**（`company_nodes.py` L58–68） | `needs_opc_context(query)`（`execution_path._OPC_KEYWORDS`）；**未命中**立即 `_opc_context("not_required")` | **命中**：`await sense_opc` → HTTP `opc_service` 或 edge JSON 快取（`opc_service/sense.py` L64–71，timeout 10s） | 無 | 無 |
| **`enhance_with_linkin_context`**（`linkin/pipeline.py` L139–192） | 未同時滿足 `world_hit`／`mc_hit`／`obs_hit`／`players_presence_block` 則 **`return {"linkin_context": {}}`**（L191–192） | `world_hit`：`get_store().search` Chroma／JSON（L198–204）；`mc_hit`：`connector_status_brief()`；可觀測性：`build_ai_context` | **RAG 檢索含 embedding 查詢**（Chroma 路徑） | 無 |
| **`retrieve_memories`** | 無關鍵字門控（總執行） | Chroma `search_similar` | 是（向量檢索） | 无 |
| **`enhance_with_recall_context`** | 內部依整合源 fail-open | 可能 HTTP 多源 | 可能有 | 無 |

**P1 真實風險**：基線 bench 若 stub 掉 enhancer（v1），會**低估** P1；必須分 query 類型量測。

### 7.3 VM 實測（`master` @ fdeb619，本機 OPC 未啟動）

| Query 類型 | `enhance_with_opc_context` p50 | `enhance_with_linkin_context` p50（warm） |
| --- | --- | --- |
| 未命中（例：「今天天氣如何」） | **~0 ms** | **~0.25 ms**（僅 regex） |
| OPC 命中（「產線馬達溫度…」） | **~14 ms**（HTTP 快速失敗） | ~0.25 ms（未走靈境 RAG） |
| 靈境世界觀（「靈境精靈森林…」） | ~0 ms | **~7.3 ms**（p95 ~10 ms；Chroma 降級 JSON） |
| MC 單步控制 | ~0 ms | **~6.8 ms**（MCP 摘要 + 可觀測性，無 world RAG） |

OPC 服務可用時，命中延遲可能升至 **數十–數百 ms**（受 `EVOL_OPC_TIER`／edge TTL 影響）；**不可**用單一絕對毫秒閘門跨 CI runner。

### 7.4 驗收標準（兩段式）

**(a) 未命中 OPC 且未命中 Linkin 注入**（與 `build_routing_preview.reason_codes` 無 `opc_keyword`／靈境注入等價判斷）

- 同一進程內 **A/B**：`EVOL_UNIFIED_PIPELINE=off` vs `pre`，各 ≥30 次 TTFT。
- 通過：`median(TTFT_pre) <= median(TTFT_off) * 1.05 + 5ms` 且 `p95_pre <= p95_off * 1.10 + 10ms`。
- **不得**回歸（相對 off 為準）。

**(b) 命中 OPC 或 Linkin 注入 — 已採用方案 B2（Q8）**

- **並行**：在依賴允許下，將 `enhance_with_opc_context`、`enhance_with_linkin_context`、`enhance_with_recall_context`（及已完成的 `retrieve_memories`）以 `asyncio.gather` 與彼此並行；**不得**為等待慢源而阻塞已完成的快源。
- **超時**：整段前置增強（或分源 `wait_for`）受 `cost_speed.json` → `unified_pipeline.pre_enhance_timeout_ms` 約束，**預設 300 ms**。
- **逾時行為**：取消尚未完成的增強任務；**跳過**對應注入（不硬等 OPC／RAG）；在 state 記錄 `context_degraded` / `degraded_sources`；**首 token 照常開跑**（TTFT 不因慢 OPC 無限延長）。
- **與 `/chat` 差異**：全圖 `ainvoke` 在 P1 仍可能硬等增強；僅 **SSE simple（flag≥`pre`）** 採超時降級 — 逾時時 SSE 答案可能暫時少上下文，以 `degraded` 標記明示（PM 已接受）。
- ~~**B1**（允許固定增量 TTFT）~~：**未採用**。
- 命中類 query **不**與 (a) 混跑同一閾值；bench 另列「命中 + 降級」用例（mock 慢 OPC assert `degraded` 且 TTFT < timeout + 裕量）。

### 7.5 CI 腳本（`scripts/bench_stream_ttft.py`）

- **同程相對比較**：單一 pytest 進程內先跑 `off` 再跑 `pre`（或 parametrize 順序固定），mock `call_llm_stream` sleep 5ms；enhancer **不** mock（或 OPC mock 固定 1ms 僅用於單元測試分支）。
- 輸出：`ttft_off_p50`、`ttft_pre_p50`、`ratio`；失敗時打印 phase 時間分解（optional spans）。
- **禁止**跨 job 絕對閾值（如 v1 的 41ms）。

### 7.6 生產可觀測

- `TraceLogger.log_custom("stream_ttft", {ms, preview_path, opc_status, linkin_active, context_degraded, degraded_sources})`（flag≥`pre`）。
- 監控／Optimization 面板可聚合 `pre_enhance_degraded` 率（實作 P1 起可選）。

---

## 8. 程式锚點

| 符號 | 位置 |
| --- | --- |
| OPC 增強 | `backend/core/company_nodes.py:enhance_with_opc_context` L58–95 |
| 靈境增強 | `backend/linkin/pipeline.py:enhance_with_linkin_context` L139–234 |
| `record_outcome` | `backend/core/nodes.py:decide_final_answer` L569–583 |
| Task finalize | `backend/core/nodes.py:finalize_task_answer` L83–88 |
| SSE 計費 | `backend/main.py:event_stream` L1315–1316、L1551–1552 |
| 同步 chat（無計費上下文） | `backend/main.py:chat` L941–966 |

---

## 9. 驗收測試清單

1. 契約：三入口 path／complexity／max rounds。  
2. P1：注入探針（SSE = batch）。  
3. P2：反思 iteration 一致；**`record_outcome` 恰一次**；disconnect 零次。  
4. `test_length_gate` SSE 用例。  
5. §7.5 同程 TTFT A/B（miss 類 query）。  
6. P2：串流 cancel 與 billing `interrupted`。

---

## 10. 摘要

**狀態：已核准，P0 可開工。** 三軌收斂 = 單一編排 + 分級旗標 + TTFT 雙軌驗收。P1 採 **並行＋300ms 超時降級**（`cost_speed.json`），`degraded` 須在 path_resolved／done／trace 可見。Q1 短期 **保留 Task OPC 六級**；Q3 **auditor_ticket→semantic_lock**；Q7 **P0–P2 不計量**，P3 前 PM 問用戶。P2 串流寫入 `routing_feedback` **每請求一次**，PR 須說明 company 佔比護欄影響。各階段 **獨立 PR**，合併前 **本機全量測試**。
