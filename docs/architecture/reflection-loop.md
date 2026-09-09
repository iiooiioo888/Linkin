# 反思閉環

反思閉環是 EvoLoop 的核心機制：**每個回答都經過自動評估，低分回答觸發反思和改進迴圈**。

## 流程

```
生成初始回答 → 輸出長度守門 → 多維度評估(4維) → 分數 ≥ 門檻？ → 是 → 決定最終回答 → 交付端長度守門 → 存入記憶
                                    ↓ 否
                              反思（根因分析）
                                    ↓
                              改進回答
                                    ↓
                       輸出長度守門 → 再次評估（迴圈）
```

## 多維度評估（優化 #1）

不再使用單一 0-10 分，而是從 4 個維度獨立評分：

| 維度 | 權重 | 評估內容 |
|------|------|----------|
| 準確性 (accuracy) | 35% | 資訊是否正確、有無事實錯誤 |
| 完整性 (completeness) | 30% | 是否涵蓋問題的所有關鍵要點 |
| 清晰度 (clarity) | 20% | 表達是否清楚、結構是否合理 |
| 相關性 (relevance) | 15% | 是否切題、有無偏題或冗餘 |

**加權總分** = Σ(維度分數 × 權重)，範圍 0-10。

### 評估流程

```
LLM 多維度評估 → 解析成功 → 加權總分
                 → 解析失敗 → 規則啟發式 fallback
可選：交叉評估（第二模型覆核，打破自評偏差）
```

### 規則 Fallback

LLM 評估失敗時，使用可量化的規則：

- **準確性**：回答長度、不確定性標記、重複內容檢測
- **完整性**：查詢關鍵詞在回答中的覆蓋率
- **清晰度**：段落結構、列表使用、標題層級、過長句子
- **相關性**：查詢類型匹配（how-to/定義）、字符重疊率

### 交叉評估（可選）

設置 `EVOL_CROSS_EVAL_MODEL` 環境變數後，第二個模型會覆核評估結果：
- 覆核模型同意 → 保留原始評估
- 覆核模型不同意 → 使用覆核分數

## 動態迭代策略（優化 #4）

不再固定 3 次迭代，而是根據分數變化動態決定：

**終止條件（任一滿足即停止）：**
1. 分數已達門檻（預設 8 分）
2. 達到最大迭代次數（預設 3 次）
3. 分數變化率過低（最近兩輪提升 < 0.5 分）

```
第 1 輪：5.0 → 反思改進
第 2 輪：7.2 → 反思改進（提升 2.2，繼續）
第 3 輪：7.5 → 提前終止（提升 0.3 < 0.5）
```

## 分層反思

根據分數選擇反思深度：

| 分數範圍 | 反思策略 | 說明 |
|----------|----------|------|
| < 5 分 | 深度反思 | 傳入完整多維度評估細節，強調根因分析 |
| 5-8 分 | 表面修正 | 只傳入摘要（最弱維度），聚焦具體改進點 |

公司運行時產出若帶有 RAHO 質詢樹，反思會額外注入「質詢交鋒」摘要（被質詢的規劃缺口、上交與逾時），而不只評最終交付物。

## 輸出長度守門

超長回答不再靠硬截斷交付，而是由 `enforce_output_length`（評估前，看 `current_answer`）與
`enforce_final_length`（交付端，看 `final_answer`）兩個節點拦下——同一實作的兩個掛點，
掛點二是為了補 `decide_final_answer` 在回答為空時降級改用 `initial_answer` 造成的漏洞。

| 行為 | 說明 |
|------|------|
| 上限來源 | `cost_speed.json` 的 `complexity.<level>.max_output_chars`，simple 800 / medium 2000 / complex 4000；支援熱重載，配置缺欄時退回內建兜底值 |
| 合規時 | 直接放行，**不產生任何 LLM 呼叫**（零成本穿透） |
| 超限時 | 寫入 `length_directive`（長度硬性要求）與 `length_rewrites` 計數，由 `should_rewrite_length` 路由回 `reflect`，讓閉環把「精簡」當成一項改進目標 |
| 指令注入 | `length_directive` 會加進 `reflect` 與 `improve_answer` 的 prompt，否則閉環不知道長度是硬約束、不會收斂 |
| 預算用盡 | 重寫達 `EVOL_MAX_LENGTH_REWRITES`（預設 2）次仍超標 → 改交付歷次**最短**的一版（`length_best_answer`）並在 `length_warnings` 記一筆，不再回環，保證閉環終止 |
| fail-open | 回答為 `None`／缺欄、複雜度標籤無法辨識時，節點放行或退回兜底上限，不讓守門成為新的崩潰點 |

### 圖外迴圈同樣受守門

LangGraph 只覆蓋 `POST /chat`。另有三處**手抄的反思迴圈**（不走圖，改拓撲不會生效），
各自直接呼叫 `nodes.enforce_output_length`，並把迴圈條件寫成
`… or state["length_directive"]`，讓超標時多跑一輪 reflect/improve：

| 入口 | 位置 |
|------|------|
| `POST /chat/stream`（SSE 串流） | `backend/main.py` → `event_stream()` |
| 公司運行時 SSE | `backend/main.py` → `_company_stream()` |
| `POST /tasks` 背景任務 | `backend/services/task_manager.py` → `_run_reflection_loop()` |

新增第四條路徑時，務必照同樣方式接上守門節點，否則該路徑的超長輸出不會被拦。

## LLM 快取（優化 #3）

反思迴圈中 `evaluate → reflect → improve` 的 prompt 高度相似，使用兩級快取避免重複 API 呼叫：

- **Level 1 — 精確匹配**：`SHA256(prompt + system + model)` → O(1) 查找
- **Level 2 — 語義匹配**：embedding 餘弦相似度 > 0.92 時復用

快取策略：
- 只快取成功的 LLM 回應（失敗/重試不快取）
- TTL 1 小時自動過期
- LRU 淘汰，上限 512 條
- 新增記憶後自動失效

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_PASS_THRESHOLD` | `8` | 通過門檻分數 |
| `EVOL_MAX_ITERATIONS` | `3` | 最大迭代次數 |
| `EVOL_MIN_SCORE_IMPROVEMENT` | `0.5` | 最小分數提升（低於此值提前終止） |
| `EVOL_MAX_LENGTH_REWRITES` | `2` | 超長回答最多丢回閉環重寫的次數 |
| `EVOL_CROSS_EVAL_MODEL` | — | 交叉評估模型（不設置則跳過） |
| `EVOL_LLM_CACHE_SIZE` | `512` | LLM 快取條目上限 |
| `EVOL_LLM_CACHE_TTL` | `3600` | 快取 TTL（秒） |
| `EVOL_SEMANTIC_CACHE` | `true` | 是否啟用語義快取 |
| `EVOL_SEMANTIC_THRESHOLD` | `0.92` | 語義相似度閾值 |

## 狀態模型

```python
class EvoLoopState:
    # 輸入
    query: str
    history: list[dict]
    session_id: str

    # 記憶
    retrieved_memories: list[str]

    # 生成
    initial_answer: str
    current_answer: str

    # 評估
    score: float                          # 加權總分 0-10
    evaluation: dict                      # 向後相容格式
    multi_dim_evaluation: MultiDimEvaluation  # 多維度結果

    # 反思
    critique: str
    suggestion: str
    reflections: list[ReflectionRecord]   # 歷次反思記錄
    iteration: int

    # 輸出長度守門
    max_output_chars: int                 # 依複雜度解析出的上限
    length_directive: str                 # 未消化的長度硬性要求（非空則路由回 reflect）
    length_rewrites: int                  # 已丢回重寫的次數
    length_best_answer: str               # 歷次最短候選
    length_warnings: list[str]            # 預算用盡仍超標的說明

    # 輸出
    final_answer: str
    memory_saved: bool
```
