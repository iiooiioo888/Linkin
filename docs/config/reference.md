# 配置參考

## 環境變數總覽

### 必填

| 變數 | 說明 |
|------|------|
| `OPENAI_API_KEY` | LLM 金鑰（LiteLLM；亦可用 DeepSeek／OpenRouter 等相容金鑰） |

### 登入閘門

來源值只放環境變數。未設定帳號與密語時，登入一律拒絕。

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LINKIN_GATE_ID` | 必填 | 閘門帳號 |
| `LINKIN_GATE_SECRET` | 必填 | 閘門密語 |
| `LINKIN_COOKIE_SECURE` | 依請求是否為 HTTPS | `1` 強制 Secure Cookie；本機 HTTP 不要設 |
| `LINKIN_ENABLE_DOCS` | 關閉 | `1` 才掛 `/docs`，且仍要先登入 |
| `LINKIN_AUTH_DISABLED` | `0` | `1` 關閉閘門 |
| `LINKIN_AUTH_FORCE` | `0` | `1` 即使 pytest 也強制開啟 |

### LLM 配置

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `OPENAI_API_BASE` | — | 可選端點（如 `https://api.deepseek.com`、`https://openrouter.ai/api/v1`） |
| `EVOL_MODEL` | 未設時：無端點為 `gpt-5.6-luna`，有端點則該供應商模型池首項 | 預設模型（會被模型池 clamp） |
| `EVOL_EMBED_MODEL` | `text-embedding-3-small` | 嵌入模型（用於記憶檢索和語義快取） |

多組 API 請用控制台「配置 → API 路由」（或頂欄齒輪）或 `POST /config/routes` 寫入**目前登入帳號**的設定。未登入的腳本仍讀 `EVOL_CONFIG_DIR/llm_config.json`。遷移與隔離說明見 [per-user-settings.md](../migration/per-user-settings.md)。

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_USER_SETTINGS_DIR` | `backend/data/user_settings` | 每帳號設定目錄 |
| `EVOL_SETTINGS_LEGACY_OWNER` | 先 `LINKIN_GATE_ID`，否則 `deploy_admin` | 既有全域 `llm_config.json` 複製給哪一個帳號（不刪除來源） |
| `LINKIN_GATE_ACCOUNTS` | — | 選用。JSON 陣列或檔案路徑，多帳號 `{"username","secret"}`，與單一閘門並存 |

### 模型池運維

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_LLM_OPS_ENABLED` | `true` | 啟用背景目錄刷新（OpenRouter 等 `/models`） |
| `EVOL_LLM_OPS_INTERVAL_SEC` | `300` | 刷新間隔（秒，限制 60–3600） |

### 角色目錄

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_ROLE_CATALOG_PATH` | `backend/data/role_catalog.json` | 角色設定覆蓋 + 自定義角色持久化路徑 |

### Minecraft MCP

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_MC_MCP_ENABLED` | `false` | 對 MineMCP 發送真實 JSON-RPC |
| `EVOL_MC_MCP_URL` | `http://127.0.0.1:3000` | 插件 HTTP 位址 |
| `EVOL_MC_MCP_TOKEN` | — | 與 `plugins/MineMCP/config.yml` 相同 |
| `EVOL_MC_MCP_RPC_PATH` | `/sse` | JSON-RPC 路徑 |
| `EVOL_MC_MCP_WORLD` | `world` | 預設世界 |
| `EVOL_MC_MCP_MAX_FILL` | `5000` | 單次 fill 上限 |
| `EVOL_MC_JOIN_ADDRESS` | — | 玩家現場空狀態「加入伺服器」位址（host:port） |

### 量化行情工具

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_TUSHARE_TOKEN` | — | 可選；設定後 A 股日線可備援 Tushare |
| `EVOL_FINNHUB_TOKEN` | — | 可選；美股報價／日線備援 |
| `EVOL_ALPHAVANTAGE_KEY` | — | 可選；免費層約 25 次/日 |

無需金鑰即可使用 Yahoo／東方財富／新浪／Stooq／Frankfurter／CoinPaprika。詳見 [量化行情工具](../company/quant-tools.md)。

### 反思閉環

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_PASS_THRESHOLD` | `8` | 通過門檻分數（0-10） |
| `EVOL_MAX_ITERATIONS` | `3` | 最大迭代次數 |
| `EVOL_MIN_SCORE_IMPROVEMENT` | `0.5` | 最小分數提升（低於此值提前終止） |
| `EVOL_CROSS_EVAL_MODEL` | — | 交叉評估模型（不設置則跳過） |

### RAHO 遞歸對抗分層

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_RAHO_ENABLED` | `true` | 總開關 |
| `EVOL_RAHO_USER_GRILL` | `true` | L5→L4 用戶 Grill-Me／需求審計 |
| `EVOL_RAHO_MGP` | `true` | 強制質詢協議 |
| `EVOL_RAHO_LOCK_THRESHOLD` | `0.92` | 語意鎖定綜合置信度（需求審計官五維皆 > 90，總分 > 0.92 才進 Planner） |
| `EVOL_RAHO_DECISION_TTL` | `60` | 熱馬桶圈決策逾時（秒；`0` = 立即自動裁決） |
| `EVOL_RAHO_PLANNER_LLM` | `false` | L4 戰役 DAG 是否呼叫 LLM（關閉則純規則） |
| `EVOL_RAHO_COMMANDER_LLM` | `false` | L3 原子 DAG 是否呼叫 LLM（關閉則純規則） |
| `EVOL_RAHO_L1_LLM` | `false` | L1 憲兵是否在規則通過後再呼叫 LLM 覆核（關閉則純規則） |
| `EVOL_RAHO_L0` | `true` | L0 環境與記憶核心（記憶／知識／態勢注入 L1–L5） |

### LLM 快取

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_LLM_CACHE_SIZE` | `512` | 快取條目上限 |
| `EVOL_LLM_CACHE_TTL` | `3600` | 快取 TTL（秒） |
| `EVOL_SEMANTIC_CACHE` | `true` | 是否啟用語義快取 |
| `EVOL_SEMANTIC_THRESHOLD` | `0.92` | 語義相似度閾值 |

### 向量記憶庫

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CHROMA_HOST` | — | ChromaDB 主機（不設置則用本地） |
| `CHROMA_PORT` | `8100` | ChromaDB 端口 |
| `EVOL_CHROMA_COLLECTION` | `evo_memory` | Collection 名稱 |
| `EVOL_CHROMA_DIR` | `backend/data/chroma` | 本地持久目錄 |
| `EVOL_SEARCH_CACHE_SIZE` | `128` | 檢索快取大小 |
| `EVOL_SIMILARITY_THRESHOLD` | `1.2` | 靜態相似度門檻 |
| `EVOL_THRESHOLD_PERCENTILE` | `75` | 自適應門檻百分位 |

### Redis

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `REDIS_URL` | — | Redis 連線。Compose 會要求 `REDIS_PASSWORD`，URL 需帶同一組密碼 |
| `REDIS_PASSWORD` | 必填（Compose） | Redis `requirepass`。使用 URL 安全字元 |

### 狀態存儲

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_STATE_BACKEND` | `auto` | 存儲後端（`redis` / `jsonl` / `memory` / `auto`） |
| `EVOL_STATE_DIR` | `backend/data/state` | JSONL 存儲目錄 |

### OPC 工業整合

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `OPC_INTERNAL_TOKEN` | 必填（Compose） | 後端呼叫 OPC 讀寫時帶的內部權杖。未設定時 OPC 拒絕健康檢查以外的路由 |
| `OPC_SIM_ENABLED` | `false` | 啟用模擬 OPC 伺服器。正式 Compose 維持關閉 |
| `OPC_WRITE_WHITELIST` | — | 寫入白名單（逗號分隔） |
| `OPC_STAGE_TIMEOUT` | `30` | 每級超時（秒） |
| `OPC_ACT_HUMAN_CONFIRM` | `false` | 執行級人工確認 |

### 預算管控

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `EVOL_MODEL_COSTS_PATH` | — | 模型價格配置文件路徑 |

### Docker

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `DOCKER_COMPOSE_PROJECT` | — | Docker Compose 項目名 |

## 模型價格配置

文件路徑：`backend/config/model_costs.json`

```json
{
  "gpt-4o": [2.50, 10.00],
  "gpt-4o-mini": [0.15, 0.60],
  "deepseek-v4-flash": [0.22, 0.66],
  "deepseek-v4-pro": [0.66, 1.98],
  "deepseek-v4-flash-vision-exp": [0.22, 0.66],
  "qwen-turbo": [0.05, 0.20]
}
```

格式：`[input_cost_per_1M_tokens, output_cost_per_1M_tokens]`

支持運行時熱更新：
```python
from backend.company.budget import reload_model_costs
reload_model_costs()
```

## .env.example

```bash
# 必填
OPENAI_API_KEY=sk-your-key-here
# OPENAI_API_BASE=https://api.deepseek.com

# 模型（會被模型池 clamp）
EVOL_MODEL=gpt-5.6-luna

# 模型池運維
EVOL_LLM_OPS_ENABLED=true
EVOL_LLM_OPS_INTERVAL_SEC=300

# 反思閉環
EVOL_PASS_THRESHOLD=8
EVOL_MAX_ITERATIONS=3

# Redis
REDIS_PASSWORD=replace-with-a-long-random-string
REDIS_URL=redis://:replace-with-a-long-random-string@localhost:6379/0
OPC_INTERNAL_TOKEN=replace-with-another-random-string
LINKIN_GATE_ID=your-gate-id
LINKIN_GATE_SECRET=your-gate-secret

# ChromaDB
CHROMA_HOST=localhost
CHROMA_PORT=8100

# OPC
OPC_SIM_ENABLED=true
```
