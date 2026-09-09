# 性能優化路線圖

本文記錄 EvoLoop 性能與成本優化的優先級、實作狀態與配置項。

## 優先級總覽

| 優先級 | 優化項 | 預期收益 | 狀態 |
|--------|--------|----------|------|
| **P0** | 任務—模型匹配（不同環節用不同規模模型） | 成本降低 40–60% | ✅ 已實作 |
| **P0** | 反思早停機制 | 避免無效呼叫，延遲降低 | ✅ 已實作 |
| **P1** | 模型池健康檢查 + 自動降級 | 主模型逾時／限流自動切換 | ✅ 已實作 |
| **P1** | 成本感知路由 | 簡單任務走便宜模型 | ✅ 已實作 |
| **P1** | Reviewer + Synthesizer 合併 | 延遲降低 ~25% | ✅ 已實作 |
| **P1** | 分層快取 | 命中率提升 | ✅ 已實作 |
| **P2** | 路由自適應回饋 | 長期品質提升 | ✅ 已實作 |
| **P2** | 邊緣快取層 | 相似請求延遲可控 | ✅ 已實作 |
| **P3** | 可觀測性全鏈路 trace | 為後續優化提供資料基礎 | ✅ 已實作 |
| **P3** | 動態反思閾值 | 簡單任務減少過度反思 | ✅ 已實作 |
| **P3** | 用戶回饋閉環 | 驅動策略自適應 | ✅ 已實作 |
| **P3** | Docker 資源限制 | 部署環境穩定性 | ✅ 已實作 |

---

## P0：任務—模型匹配

**模組**：`backend/core/stage_router.py`

反思閉環各環節自動選擇不同 `BudgetTier`：

| 環節 | 預設 Tier | 說明 |
|------|-----------|------|
| generate / improve | ROUTINE | 日常生成 |
| evaluate / cross_eval | SUMMARY | 最便宜，適合評分 |
| reflect | REASONING | 根因分析需較強推理 |

**環境變數**（可選覆寫）：

```env
EVOL_STAGE_TIER_GENERATE=routine
EVOL_STAGE_TIER_EVALUATE=summary
EVOL_STAGE_TIER_REFLECT=reasoning
EVOL_STAGE_TIER_IMPROVE=routine
```

公司運行時工作項級別路由見 `backend/company/budget.py` → `TierRouter`。

---

## P0：反思早停

**模組**：`backend/core/graph.py` → `should_improve`

終止條件（任一滿足即 finalize）：

1. 分數 ≥ `EVOL_PASS_THRESHOLD`（預設 8）
2. 迭代次數 ≥ `EVOL_MAX_ITERATIONS`（預設 3）
3. 分數提升 < `EVOL_MIN_SCORE_IMPROVEMENT`（預設 0.5）

詳見 [reflection-loop.md](./reflection-loop.md)。

---

## P1：模型池健康檢查 + 自動降級

**模組**：`backend/core/provider_pool.py` → `invoke_with_pool_failover`；`backend/core/llm.py` → `call_llm`

當主模型逾時、限流或連續失敗時，自動在 `allowed_models` 池內切換成本更低的備援模型（Hub 路由已有類似能力，此優化覆蓋反思閉環主鏈路）。

```env
EVOL_LLM_POOL_FAILOVER=true          # 預設開啟
EVOL_LLM_FAILOVER_TIMEOUT=30       # 單模型嘗試逾時（秒）
EVOL_LLM_FAILOVER_SLOW_S=10        # 慢呼叫視為失敗
EVOL_LLM_POOL_FAIL_THRESHOLD=2     # 連續失敗次數觸發熔斷
EVOL_LLM_POOL_OPEN_SEC=60          # 熔斷持續時間
```

監控：`GET /monitor/llm-ops` → `ops.pool_failover`；系統指標 roadmap 項 `pool_failover`。

---

## P1：成本感知路由

**模組**：`backend/core/cost_speed_router.py` · 配置 `backend/config/cost_speed.json`

依任務複雜度（simple / medium / complex）與管線環節選擇模型，並由 `route_by_complexity` 決定走單次生成或公司運行時：

| 複雜度 | 路徑 | 典型模型 |
|--------|------|----------|
| simple | 單次生成 | qwen-turbo |
| medium | 單次生成 | qwen-plus |
| complex | 公司運行時 | deepseek-v4-pro |

```env
EVOL_COST_SPEED_ENABLED=true
EVOL_COST_SPEED_PATH=backend/config/cost_speed.json
```

熱重載：`POST /config/cost-speed/reload`（修改配置後無需重啟）

監控：`GET /monitor/optimization` → `cost_speed`

---

## P1：Reviewer + Synthesizer 合併

**模組**：`backend/company/orchestrator.py` → `_review_and_synthesize`

公司運行時階段 3 預設啟用合併模式：單次 LLM 完成交付物審查 + 整合，減少一次 API 往返。

```env
EVOL_MERGE_REVIEW_SYNTH=true   # 預設 true；設為 false 恢復分離流程
```

---

## P1：分層快取

| 層級 | 模組 | 說明 |
|------|------|------|
| LLM 精確 + 語義 | `backend/core/llm_cache.py` | 反思循環 prompt 複用 |
| Hub 語義 | `backend/hub/cache.py` | AI Hub 對話快取 |
| 任務拆分 | `backend/company/decomposer.py` | 分解結果 LRU |

```env
EVOL_LLM_CACHE_SIZE=512
EVOL_SEMANTIC_CACHE=true
EVOL_SEMANTIC_THRESHOLD=0.92
EVOL_DECOMPOSE_CACHE_SIZE=64
```

---

## P2：路由自適應回饋

**模組**：`backend/core/routing_feedback.py`

`route_by_complexity` 根據歷史 simple/company 路由結果與最終分數，動態調整複雜任務字數門檻。

- simple 路由低分（<6）多次 → 提高門檻，更早走 company
- company 路由高分且 query 短 → 略降門檻

資料存儲：`backend/data/routing_feedback.json`

```env
EVOL_ROUTING_FEEDBACK_PATH=backend/data/routing_feedback.json
EVOL_ROUTING_LENGTH_BIAS=0
```

---

## P2：邊緣快取層

監控中心「運行指標」彙總的是 **EvoLoop 自身運行狀態**（快取命中率、反思輪次、路由門檻、Trace、任務成功率等），**不是** OPC UA 工業現場感測。

- **前端**：`SystemMetricsPanel`（分頁鍵 `metrics`）· `GET /monitor/optimization`
- **工業 OPC 任務路徑**（閥位、馬達等感測標籤）僅在 `resolved_path === 'opc'` 時由 `opc_service` 處理，與監控中心系統指標無關

### 系統分層快取（監控 API）

**模組**：`backend/services/optimization_monitor.py` → `_layered_cache_status()`

反映 `backend/core/llm_cache.py` 精確 + 語義快取條目數與命中率，供 `GET /monitor/optimization` 與「運行指標」分頁使用。

```env
EVOL_LLM_CACHE_SIZE=512
EVOL_LLM_CACHE_TTL=3600
EVOL_SEMANTIC_CACHE=true
EVOL_SEMANTIC_THRESHOLD=0.92
```

### OPC 工業邊緣快取（僅工業任務路徑）

**模組**：`opc_service/sense.py`

僅在 `route_by_complexity` 走 OPC 6 級閉環時使用，與運行指標監控無關。

| 模式 | 行為 |
|------|------|
| `auto` | 邊緣快取 TTL 內復用，否則雲拉取 |
| `edge` | 僅使用本地快取 |
| `cloud` | 始終 HTTP 拉取 OPC 微服務 |

```env
EVOL_OPC_TIER=auto
EVOL_OPC_EDGE_TTL=5
EVOL_OPC_EDGE_CACHE=opc_service/data/edge_cache.json
```

---

## P3：全鏈路 trace

**模組**：

- `backend/services/trace_logger.py` — 任務級 JSONL 軌跡；`aggregate_reflection_stats()` 彙總反思輪次／耗時／改進幅度
- `backend/core/pipeline_trace.py` — LangGraph 節點事件

節點在 `session_id` / `task_id` 存在時自動寫入 trace，供監控面板與後續分析使用。

監控：`GET /monitor/optimization` → `reflection_trace`（均輪次、均改進幅度、最近任務鏈路表）；「系統指標」分頁展示。

---

## P3：動態反思閾值

**模組**：`backend/core/dynamic_threshold.py`

依任務複雜度與用戶滿意度自適應調整 `EVOL_PASS_THRESHOLD`：

| 場景 | 行為 |
|------|------|
| 短查詢（< 80 字）且無複雜關鍵詞 | 門檻降低（預設 -0.5） |
| 長查詢或含開發／架構關鍵詞 | 門檻提高（預設 +0.3） |
| simple 路由歷史低分率高 | 略提高門檻 |
| 用戶滿意度低 | 略提高門檻 |

```env
EVOL_PASS_THRESHOLD=8
EVOL_THRESHOLD_SIMPLE_BIAS=-0.5
EVOL_THRESHOLD_COMPLEX_BIAS=0.3
EVOL_THRESHOLD_MIN=6.5
EVOL_THRESHOLD_MAX=9.0
```

---

## P3：用戶回饋閉環

**模組**：`backend/core/user_feedback.py`

- `POST /feedback` — 收集 thumbs_up / thumbs_down / copy / edit
- `GET /feedback/stats` — 滿意度統計
- 回饋資料影響動態閾值微調

```env
EVOL_USER_FEEDBACK_PATH=backend/data/user_feedback.json
EVOL_USER_FEEDBACK_MAX=500
```

---

## P3：Docker 資源限制

**檔案**：`docker-compose.yml`

各服務已配置 `deploy.resources.limits`（CPU／記憶體），避免容器爭搶導致性能波動。

---

## 相關文件

- [反思閉環](./reflection-loop.md)
- [公司運行時](./company-runtime.md)
- [OPC 整合](./opc-integration.md)
- [術語表](../glossary.md)
