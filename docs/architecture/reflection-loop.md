# 反思閉環

反思閉環是 EvoLoop 的核心機制：**每個回答都經過自動評估，低分回答觸發反思和改進迴圈**。

## 流程

```
生成初始回答 → 多維度評估(4維) → 分數 ≥ 門檻？ → 是 → 決定最終回答 → 存入記憶
                                    ↓ 否
                              反思（根因分析）
                                    ↓
                              改進回答
                                    ↓
                              再次評估（迴圈）
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

    # 輸出
    final_answer: str
    memory_saved: bool
```
