# AI Hub 多模型編排系統 — 系統詳細設計說明書

> **文件定位：** Hub 專用契約（探針／熔斷／目錄／`/api/v1/*`）。  
> **路徑請勿隨意搬移**——`backend/hub/`、`backend/tests/test_hub_catalog.py` 會依此路徑對齊。  
> 產品總覽請看 [架構總覽](architecture/overview.md)；前端視覺 Token 在根目錄 `DESIGN.md`（非本文件）。  
> 知識庫索引：[README.md](README.md)

| 項目 | 內容 |
| :--- | :--- |
| 文件版本 | 1.5.0 |
| 文件狀態 | Draft / Contract-First |
| 適用範圍 | EvoLoop 之上新增的 OpenAI 相容推論面與 Hermes Agent 編排層 |
| 模型池原則 | **僅允許第一章目錄內 9 個模型 ID**；目錄外一律 `400 UNSUPPORTED_MODEL`，不向任何未列廠商發請求 |
| **禁止供應商** | **Anthropic / Claude 全系列（Opus / Sonnet / Haiku / Fable 及任何後續代稱）一律不進目錄、不進 Failover、不進 preferred_models、不進探針** |
| 智能與 Agent 主力 | GPT-5.6 Sol（智能與 Agent 綜合最強；輸出 $30/M；52 tok/s；Agent 指數 80） |
| 多模態主力 | Gemini 3.1 Pro（2M 上下文；圖像 / 影片 / 音訊 / PDF） |
| 編寫日期 | 2026-08-26 |
| 修訂 | 1.5.0：補齊五倉工具契約（StocksX / LittleCrawler / StoryForge / PysdnOPC / UI-web）、意圖自動掛載、Agent 不再硬編碼 `symbol`。1.4.0：落地探針、熔斷接入 Failover、同步競速、Agent 雙步工具流、`GET /api/v1/catalog`、前端 Hub 操作台、Vite `/api/v1` 不剝前綴。1.3.0：落地 `backend/hub/` 公開面與 HUB-R1–R9 契約測試；Nginx `/api/v1/` 最長前綴。1.2.0：凍結「零 Claude」契約。1.1.0：模型池改 GPT-5.6 Sol / Gemini 3.1 Pro 為西方旗艦 |

---

## 與現有 EvoLoop 的契約對齊（實施前必讀）

本文件定義的是 **AI Hub 新增面**，不得破壞現有產品契約。衝突檢查結果如下：

| 現況 | 衝突點 | 本設計的處理 |
| :--- | :--- | :--- |
| 根目錄 `DESIGN.md` 為 Linear 風格 **前端視覺 Token**，非系統設計 | 不可覆寫 | 本文件落在 `docs/AI_HUB_DETAILED_DESIGN.md` |
| `POST /chat`、`POST /chat/stream`、`POST /tasks` 為反思閉環產品 API | 路徑語意不同 | Hub 使用全新前綴 `POST /api/v1/*`，**不取代** 舊路徑 |
| `frontend/nginx.conf` 的 `location /api/` 會 **剝除 `/api` 前綴** 轉發到 backend | `/api/v1/chat/completions` 會被轉成 `/v1/chat/completions` | 見 1.5 節：Kong 接管 `/api/v1/`，Nginx 僅保留 SPA 與舊 `/api/chat` |
| `AGENTS.md`：所有 LLM 必須經 `backend.core.llm.call_llm` | Hermes 若直連廠商 SDK 即違規 | Hermes 叢集 **只打 LiteLLM OpenAI 相容端點**，節點模組禁止 `import openai` 等 SDK |
| `opc_service/guard.py` 為 OPC 寫入唯一護欄 | PysdnOPC 工具若直寫標籤即違規 | 工具執行層只呼叫 `opc_service` REST，禁止繞過護欄 |
| Redis 已用於任務持久化（TTL 7 天） | Key 碰撞 | Hub 使用獨立前綴 `hub:` / `semantic:` / `provider:` / `budget:` |
| `backend/company/budget.py` 的 `_MODEL_COST_PER_1M_TOKENS` 原僅覆蓋 gpt-4o 家族與舊 DeepSeek | 與 Hub 九模型目錄不一致，未知模型會落入保守單價 (1.0, 4.0) | Hub 使用獨立價目表（§1.6）；公司運行時價目表已同步補上 Hub 九模型單價（**不含任何 Claude ID**），LangGraph 預設仍走 `gpt-4o` / `gpt-4o-mini`，兩邊計數器不共用 |
| `backend/tests/test_architecture.py` 已禁止節點模組 `import anthropic` | Hub 若直連 Anthropic SDK 會被架構測試擋下 | Hermes 只打 LiteLLM；Hub 目錄校驗額外拒絕 Claude 字串 |
| 現有基礎設施僅 Redis + ChromaDB，無 PostgreSQL / Kong / Jaeger | 新元件 | 以獨立 Compose 服務新增，不改現有 `evoloop-backend` 容器職責 |

---

# 第一章：整體架構分層與部署拓撲

## 1.1 系統上下文（C4 Level 1）

```mermaid
C4Context
    title AI Hub 系統上下文
    Person(user, "API 呼叫端", "終端使用者 / 內部服務 / 前端 SPA")
    System(hub, "AI Hub", "多模型編排、預算攔截、故障轉移、Agent 任務")
    System_Ext(openai, "OpenAI 相容上游", "GPT-5.6 Sol")
    System_Ext(google, "Google AI", "Gemini 3.1 Pro")
    System_Ext(cn, "中國區上游", "DeepSeek V4 Flash / Qwen3.5-Max / MiMo-V2.5-Pro")
    System_Ext(speed, "極速上游", "Mercury 2 / Nemotron 3.5 Lightning")
    System_Ext(oss, "開源備援", "GLM-5.2 / Kimi K3")
    System_Ext(tools, "GitHub 微服務", "StocksX / LittleCrawler / StoryForge / PysdnOPC / UI-web")
    Rel(user, hub, "HTTPS JSON", "HTTP/2")
    Rel(hub, openai, "Chat Completions", "HTTPS JSON")
    Rel(hub, google, "多模態推論", "HTTPS JSON")
    Rel(hub, cn, "屬地優先路由", "HTTPS JSON")
    Rel(hub, speed, "競速 / 低延遲", "HTTPS JSON / SSE")
    Rel(hub, oss, "熔斷降級", "HTTPS JSON")
    Rel(hub, tools, "RPC over HTTP + JWT", "HTTP/1.1 JSON")
```

## 1.2 六層部署拓撲（C4 Level 2 / Container）

```mermaid
flowchart TB
    subgraph L1["L1 接入層 Load Balancer"]
        NLB["雲端 NLB / L4<br/>TCP 443 · PROXY protocol<br/>健康檢查: GET /healthz"]
    end

    subgraph L2["L2 網關層 Kong 3.x + 既有 Nginx"]
        KONG["Kong Gateway<br/>JWT 鑑權 · 限流 · WAF<br/>OpenTelemetry 注入 traceparent"]
        NGX["evoloop-frontend Nginx<br/>僅 SPA + 舊 /api/chat|/api/tasks"]
    end

    subgraph L3["L3 業務編排層 AI Hub Core"]
        CORE["ai-hub-core :8080<br/>FastAPI · 預算攔截 · 語義快取<br/>內容安全 · 審計"]
        EVO["evoloop-backend :8000<br/>LangGraph 反思閉環（既有）"]
    end

    subgraph L4["L4 多方路由層 Hermes Agent Cluster"]
        HA["Hermes Agent × N<br/>gRPC 內部 · OpenAI Chat 相容<br/>子代理 · 動態權重 · Failover"]
        LLM["LiteLLM 適配器<br/>唯一對外模型出口"]
    end

    subgraph L5["L5 工具執行層 GitHub 微服務"]
        SX["StocksX :9101 量化"]
        LC["LittleCrawler :9102 爬蟲"]
        SF["StoryForge :9103 創意"]
        OPC["PysdnOPC Adapter :9104<br/>→ opc_service :8001 + guard.py"]
        WEB["UI/web :80 前端"]
    end

    subgraph L6["L6 基礎設施層"]
        PG[("PostgreSQL 16<br/>users / call_logs")]
        RD[("Redis 7<br/>maxmemory-policy=allkeys-lru")]
        CH[("ChromaDB<br/>語義摘要向量")]
        JGR["Jaeger Collector :4317<br/>OTLP gRPC"]
    end

    NLB -->|HTTP/2 TLS JSON| KONG
    NLB -->|HTTP/1.1 TLS| NGX
    KONG -->|HTTP/2 JSON /api/v1/*| CORE
    NGX -->|HTTP/1.1 剝除 /api 前綴| EVO
    CORE -->|gRPC Protobuf internal.hub.v1| HA
    CORE -.->|只讀對齊會話| EVO
    HA -->|HTTP/1.1 JSON OpenAI Chat| LLM
    HA -->|HTTP/1.1 JSON + JWT| SX
    HA -->|HTTP/1.1 JSON + JWT| LC
    HA -->|HTTP/1.1 JSON + JWT| SF
    HA -->|HTTP/1.1 JSON + JWT| OPC
    CORE -->|SQL/5432| PG
    CORE -->|RESP Redis Protocol| RD
    CORE -->|HTTP JSON| CH
    CORE -->|OTLP gRPC| JGR
    HA -->|OTLP gRPC| JGR
```

## 1.3 分層職責、協定與資料格式

| 層 | 元件 | 對上一層協定 | 資料格式 | 對下一層協定 | 逾時 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| L1 接入 | NLB | TLS 1.3 / HTTP/2 | 透傳 | TCP 443 | 空閒 350s |
| L2 網關 | Kong | HTTP/2 | JSON；錯誤體 RFC 7807 `application/problem+json` | HTTP/2 → Core | 連線 25s / 讀取 120s（與路由引擎一致） |
| L2 網關 | Nginx（既有） | HTTP/1.1 | JSON / SSE | HTTP/1.1 → evoloop-backend | `proxy_read_timeout 600s`（公司模式長任務，**不可套用到 Hub 推論**） |
| L3 編排 | AI Hub Core | HTTP/2 | JSON UTF-8；SSE `text/event-stream` | gRPC → Hermes | Unary 120s；Streaming 600s |
| L4 路由 | Hermes Cluster | gRPC | Protobuf `hub.v1.RouteRequest` | HTTP/1.1 JSON → LiteLLM | connect=25s, read=120s |
| L4 路由 | LiteLLM | HTTP/1.1 | OpenAI Chat Completions JSON | HTTPS → 各廠商 | 繼承 x-failover-config |
| L5 工具 | 微服務 | HTTP/1.1 JSON + JWT | JSON；錯誤 RFC 7807 | StocksX / Crawler / StoryForge：HTTP/1.1；PysdnOPC 訂閱：WebSocket `wss://opc_service:8001/opc/ws`（只讀） | 工具 RPC 8s（硬上限 15s）；WS 心跳 15s |
| L6 基礎 | PG / Redis / Chroma / Jaeger | — | SQL / RESP / HTTP JSON / OTLP | — | PG 2s；Redis 50ms；Chroma 200ms |

**禁止事項（契約）**

- L4 **不得** 直接 `import openai` / Google GenAI SDK；一律經 LiteLLM。
- L5 PysdnOPC **不得** 直連 OPC UA 寫入；必須 `POST http://opc_service:8001/opc/write`，由 `guard.py` 做白名單與數值邊界。
- L3 **不得** 修改編譯後的 `evoloop_graph`；Hub 是旁路服務，不注入 LangGraph 節點。

## 1.4 部署單元與副本策略

| 服務 | 映像建議 | CPU / MEM | 副本 | 親和性 |
| :--- | :--- | :--- | :--- | :--- |
| kong | `kong:3.8` | 1 vCPU / 1Gi | 2 | 跨 AZ |
| ai-hub-core | 內部 `ai-hub-core:1.0` | 2 vCPU / 2Gi | 3 | PDB minAvailable=2 |
| hermes-agent | 內部 `hermes-agent:1.0` | 2 vCPU / 4Gi | 3–8 HPA（CPU 65%） | 反親和 |
| postgres | `postgres:16-alpine` | 2 vCPU / 4Gi | 1 主 + 異步備 | 獨立 PV 100Gi gp3 |
| redis | 既有 `evoloop-redis` **或** 新 `redis-hub` | 1 vCPU / 2Gi | 1 | `maxmemory 1536mb`，`maxmemory-policy allkeys-lru` |
| jaeger | `jaegertracing/all-in-one:1.62` | 1 vCPU / 1Gi | 1（開發）；生產改 Collector + Tempo | — |

Hub Redis 建議 **獨立實例 `redis-hub`**，避免與既有任務 TTL 7 天的 keyspace 互相 LRU 驅逐。若必須共用 `evoloop-redis`，則 Hub 全部 key 加前綴且 `maxmemory-policy` 維持 `allkeys-lru`，語義快取 TTL=86400 由應用層保證。

## 1.5 網關路由表（解決 Nginx 前綴衝突）

現有 `frontend/nginx.conf`：

```nginx
location /api/ {
    proxy_pass http://backend:8000/;
}
```

會把 `/api/v1/chat/completions` 變成 `backend:8000/v1/chat/completions`，與既有 `/chat` 體系錯位。實施時 **Kong 必須搶先匹配更長前綴**：

| Kong Route | Methods | Upstream | Strip Path |
| :--- | :--- | :--- | :--- |
| `/api/v1` | POST GET | `ai-hub-core:8080` | 否（Core 路由即 `/api/v1/...`） |
| `/healthz` | GET | `ai-hub-core:8080` | 否 |
| `/metrics` | GET | `ai-hub-core:8080` | 否（僅內網 ACL） |

Nginx **維持原樣**，只服務 SPA 與舊產品 API。兩邊路徑集合不相交。

## 1.6 模型池（運行時目錄，白名單封閉）

| 角色 | 模型 ID（`model` 欄位） | 廠商代碼 `provider` | 輸入單價 USD/1M | 輸出單價 USD/1M | 標稱速度 tok/s | 上下文 | 能力標籤 |
| :--- | :--- | :--- | ---: | ---: | ---: | :--- | :--- |
| 智能 / Agent 雙旗艦 | `gpt-5.6-sol` | `openai` | 3.00 | 30.00 | 52 | 依供應商契約 | `intelligence,agent`；Agent 指數 80 |
| 多模態旗艦 | `gemini-3.1-pro` | `google` | 1.25 | 12.00 | — | 2,097,152 | `vision,video,audio,pdf` |
| 性價比中國主力 | `mimo-v2.5-pro` | `mimo` | 0.21 | 0.83 | — | — | `agent`（Agent 能力第 3） |
| 長文本中國主力 | `deepseek-v4-flash` | `deepseek` | 0.22 | 0.66 | — | 1,310,720 | `longctx,moe-284b` |
| 開源衍生中國主力 | `qwen3.5-max` | `qwen` | 0.30 | 1.20 | — | 151,000+ | `cn,open-derivative` |
| 極速 | `mercury-2` | `inception` | 0.50 | 2.00 | 938 | — | `speed` |
| 極速免費 | `nemotron-3.5-lightning` | `nvidia` | 0.00 | 0.00 | ~670 | — | `speed,free` |
| 開源備援 | `glm-5.2` | `zhipu` | 0.10 | 0.40 | — | — | `oss,mit,no-geo-lock`；HF 開源榜 85 |
| 開源最大 | `kimi-k3` | `moonshot` | 0.40 | 1.50 | — | — | `oss,2.8t-params` |

目錄為**封閉白名單**：`model` / `preferred_models[]` / `x-failover-config.model_whitelist[]` 的合法集合必須與此表 9 個 ID 完全一致。探針可覆寫單價與延遲，**不得**動態新增模型 ID。

**零 Claude 凍結（硬契約，程式碼與設定雙重攔截）：**

| 攔截點 | 規則 |
| :--- | :--- |
| Hub Core 目錄校驗 | `model` / whitelist / `preferred_models` 字串若匹配 `(?i)claude\|anthropic\|opus-|sonnet-|haiku-|fable` → `400 UNSUPPORTED_MODEL`，**零上游請求** |
| LiteLLM 適配器 | 禁止配置 `anthropic/` 供應商前綴；啟動時若環境變數出現 `ANTHROPIC_API_KEY` 僅記錄 P3，**不得**註冊為可路由供應商 |
| Failover / Race | 鏈與競速配對寫死為本表 ID；單元測試 `test_hub_catalog_excludes_claude` 斷言目錄、OpenAPI enum、Router `INTEL` 三集合相等且不含 Claude |
| 錯誤文案 | 使用者訊息不得出現「已切換至 Claude」等歷史文案 |

**屬地合規硬規則：** 若 `X-Client-Region` 或 GeoIP 判定為 `CN`（中國大陸），路由引擎 **強制優先且僅允許** 將候選集限制為 `{deepseek-v4-flash, qwen3.5-max, mimo-v2.5-pro}`（DeepSeek / Qwen 為合規主力，MiMo 為同屬中國區性價比備援），禁止將 prompt / 檔案發往 `openai` / `google` / `inception` / `nvidia` 境外端點。`glm-5.2` 僅在 CN 候選全部熔斷後、且使用者 `data_egress_ack=true` 時才允許（預設 false）。

---

# 第二章：核心 API 介面定義（OpenAPI 3.0 / JSON Schema）

Base URL（對外公網）：`https://hub.example.com`

共通 Request Header：

| Header | 型別 | 必填 | 長度 / 格式 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| `Authorization` | string | 是 | `Bearer ` + 43–128 字元 API Key | 對應 `users.api_key_hash`（SHA-256） |
| `Content-Type` | string | 是 | 精確 `application/json; charset=utf-8` | 其他值 → 415 |
| `X-Request-Id` | string (uuid v4) | 否 | 36 字元 | 缺省由網關生成；寫入 Jaeger `trace_id` 關聯 |
| `X-Client-Region` | string | 否 | ISO 3166-1 alpha-2，長度=2 | 若缺，以 Cloudflare `CF-IPCountry` 或 MaxMind 補齊 |
| `Idempotency-Key` | string | 非同步任務建議 | 8–64，`[A-Za-z0-9_-]+` | 24h 內相同 Key 回傳同一 `task_id` |

共通 Response Header：

| Header | 型別 | 說明 |
| :--- | :--- | :--- |
| `X-Request-Id` | uuid | 回顯 |
| `X-Trace-Id` | 32 hex | Jaeger trace id |
| `X-RateLimit-Remaining` | int32 | 目前視窗剩餘次數 |
| `X-Hub-Cache` | enum `HIT`/`MISS`/`BYPASS` | 語義快取結果 |

## 2.1 同步推論 `POST /api/v1/chat/completions`

### 2.1.1 擴展 Request Header

| Header | 型別 | 必填 | 枚舉 / 約束 | 預設 |
| :--- | :--- | :--- | :--- | :--- |
| `x-routing-strategy` | string | 否 | `cost_first` \| `speed_first` \| `quality_first` \| `manual` | `quality_first` |
| `x-failover-config` | string (JSON) | 否 | 見下方 Schema；原始長度 ≤ 2048 bytes | 系統預設 |

`x-failover-config` JSON Schema：

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://hub.example.com/schemas/failover-config.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "connect_timeout_ms": { "type": "integer", "minimum": 1000, "maximum": 60000, "default": 25000 },
    "read_timeout_ms": { "type": "integer", "minimum": 1000, "maximum": 180000, "default": 120000 },
    "max_retries": { "type": "integer", "minimum": 0, "maximum": 5, "default": 3 },
    "backoff_base": { "type": "number", "minimum": 1.5, "maximum": 4, "default": 2 },
    "model_whitelist": {
      "type": "array",
      "minItems": 1,
      "maxItems": 8,
      "items": {
        "type": "string",
        "enum": [
          "gpt-5.6-sol",
          "gemini-3.1-pro",
          "mimo-v2.5-pro",
          "deepseek-v4-flash",
          "qwen3.5-max",
          "mercury-2",
          "nemotron-3.5-lightning",
          "glm-5.2",
          "kimi-k3"
        ]
      }
    },
    "enable_race": { "type": "boolean", "default": false }
  }
}
```

`manual` 策略下 Body `model` 必填，且必須落在 `model_whitelist`（若有）與屬地允許集的交集。

### 2.1.2 Request Body

| 欄位 | 型別 | 必填 | 約束 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| `model` | string | `manual` 時必填 | 枚舉同白名單；長度 ≤ 64 | 其他策略可省略，由路由器選定 |
| `messages` | array | 是 | 1–200 則 | OpenAI Chat 格式 |
| `messages[].role` | string | 是 | `system` \| `user` \| `assistant` \| `tool` | — |
| `messages[].content` | string \| array | 是 | 單則 UTF-8 長度 ≤ 1,048,576；全對話合計 token 預估 ≤ 模型上下文 × 0.85 | 多模態時為 part 陣列（`text`/`image_url`/`input_audio`/`file`） |
| `temperature` | number | 否 | 0.0–2.0，步進 0.01 | 預設 0.7 |
| `max_tokens` | integer | 否 | 1–32768 | 缺省 2048；用於成本預估的「期望輸出 Token 數」 |
| `stream` | boolean | 否 | — | 預設 false；true 時改 SSE |
| `user` | string | 否 | 1–64，`[A-Za-z0-9_-]+` | 終端使用者穩定 ID，寫入 `call_logs.session_id` 輔助欄 |
| `metadata.session_id` | string | 否 | 8–64 | 對齊 EvoLoop session |

**邊界**

- `messages` 空陣列 → 400 `EMPTY_MESSAGES`
- 單則 content 全空白（trim 後 length=0）→ 400 `BLANK_CONTENT`
- 含 `image_url` / `input_audio` / `file` 時，若路由器選中無多模態標籤的模型，必須改選 `gemini-3.1-pro`（CN 屬地則 400 `MODALITY_NOT_ALLOWED_IN_REGION`）

### 2.1.3 成功 Response 200

Header 外加：`X-Chosen-Provider`、`X-Cost-Usd`、`X-Latency-Ms`（與 Body 同源，便於網關日誌）。

Body：

| 欄位 | 型別 | 約束 | 說明 |
| :--- | :--- | :--- | :--- |
| `id` | string | `chatcmpl-` + 26 字元 | 對應 `call_logs.id` |
| `object` | string | 常數 `chat.completion` | 相容 OpenAI |
| `created` | integer | Unix epoch 秒 | UTC |
| `model` | string | 實際模型 ID | 可能與請求不同（Failover 後） |
| `chosen_provider` | string | 枚舉見模型表 `provider` | **實際**打到的廠商 |
| `cost_usd` | number | ≥ 0，小數 6 位 | 本次預估費用（含 1.2 係數前的實際 token 計價，見第六章；此欄為 **實際** 非預估） |
| `latency_ms` | integer | ≥ 0 | TTFB 到完整 Body 關閉 |
| `routing_strategy` | string | 回顯 | — |
| `failover_hops` | integer | 0–5 | 切換次數 |
| `cache` | string | `HIT` \| `MISS` \| `BYPASS` | — |
| `choices` | array | 長度 1（本版不支援 n>1） | — |
| `choices[].index` | integer | 0 | — |
| `choices[].finish_reason` | string | `stop` \| `length` \| `content_filter` \| `tool_calls` | — |
| `choices[].message.role` | string | `assistant` | — |
| `choices[].message.content` | string | UTF-8，長度 ≤ 512KiB | 敏感詞截斷後可能為空字串 |
| `usage.prompt_tokens` | integer | ≥ 0 | — |
| `usage.completion_tokens` | integer | ≥ 0 | — |
| `usage.total_tokens` | integer | = 兩者之和 | — |

### 2.1.4 公開面 HTTP 報文示例（同步推論）

```http
POST /api/v1/chat/completions HTTP/1.1
Host: hub.example.com
Authorization: Bearer ak_live_7f3c9e2a1b8d4f06c5a0e91d
Content-Type: application/json; charset=utf-8
X-Request-Id: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d
X-Client-Region: TW
x-routing-strategy: quality_first
x-failover-config: {"connect_timeout_ms":25000,"read_timeout_ms":120000,"max_retries":3,"backoff_base":2,"model_whitelist":["gpt-5.6-sol","gemini-3.1-pro","deepseek-v4-flash","glm-5.2"],"enable_race":false}

{
  "model": "gpt-5.6-sol",
  "temperature": 0.2,
  "max_tokens": 2048,
  "stream": false,
  "messages": [
    {"role": "user", "content": "用三句話說明動態權重路由與競速的差異"}
  ]
}
```

成功回應 Header + Body：

```http
HTTP/1.1 200 OK
Content-Type: application/json; charset=utf-8
X-Request-Id: 9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d
X-Trace-Id: 4bf92f3577b34da6a3ce929d0e0e4736
X-Chosen-Provider: openai
X-Cost-Usd: 0.042180
X-Latency-Ms: 1864
X-Hub-Cache: MISS
X-RateLimit-Remaining: 47
```

非串流成功示例外殼：

```json
{
  "id": "chatcmpl-01JABCD2EFGH3IJKL4MNOPQRST",
  "object": "chat.completion",
  "created": 1787731200,
  "model": "gpt-5.6-sol",
  "chosen_provider": "openai",
  "cost_usd": 0.042180,
  "latency_ms": 1864,
  "routing_strategy": "quality_first",
  "failover_hops": 0,
  "cache": "MISS",
  "choices": [
    {
      "index": 0,
      "finish_reason": "stop",
      "message": { "role": "assistant", "content": "……投資建議正文……" }
    }
  ],
  "usage": { "prompt_tokens": 812, "completion_tokens": 640, "total_tokens": 1452 }
}
```

### 2.1.5 錯誤 Body（RFC 7807）

| HTTP | `code` | 何時 |
| :--- | :--- | :--- |
| 400 | `BAD_REQUEST` / `CONTENT_FILTER` / `MODALITY_NOT_ALLOWED_IN_REGION` | 欄位 / 敏感詞 / 屬地×模態 |
| 401 | `UNAUTHORIZED` | API Key 缺失或雜湊不匹配 |
| 403 | `BUDGET_EXCEEDED` | 日預算攔截（第六章） |
| 409 | `IDEMPOTENCY_CONFLICT` | 相同 Idempotency-Key 不同 Body |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Content-Type 不符 |
| 429 | `RATE_LIMITED` | Kong 或使用者 RPM |
| 503 | `ALL_PROVIDERS_UNAVAILABLE` | 白名單模型全部熔斷 |
| 504 | `UPSTREAM_TIMEOUT` | 主模型 >120s 且 Failover 仍失敗 |

## 2.2 非同步 Agent 任務 `POST /api/v1/agent/tasks`

用於 Hermes 子代理多步驟工具呼叫（例：「分析股市並寫報告」）。

### 2.2.1 Request Body

| 欄位 | 型別 | 必填 | 約束 |
| :--- | :--- | :--- | :--- |
| `input` | string | 是 | 1–8000 字元 |
| `tools` | array[string] | 否 | 枚舉 `StocksX_get_price` \| `StocksX_get_fundamentals` \| `LittleCrawler_fetch` \| `StoryForge_draft` \| `PysdnOPC_read` \| `PysdnOPC_write`；最多 16 個；預設依意圖自動掛載 |
| `routing_strategy` | string | 否 | 同 `x-routing-strategy`；Header 優先於 Body |
| `callback_url` | uri | 否 | 僅 https，主機必須在 `hub.callback_hosts` 白名單；長度 ≤ 512 |
| `timeout_seconds` | integer | 否 | 30–1800，預設 300 |
| `metadata.session_id` | string | 否 | 8–64 |

`x-failover-config` 同樣適用於此端點（Header）。

### 2.2.1.1 公開面 HTTP 報文示例（建立任務）

```http
POST /api/v1/agent/tasks HTTP/1.1
Host: hub.example.com
Authorization: Bearer ak_live_7f3c9e2a1b8d4f06c5a0e91d
Content-Type: application/json; charset=utf-8
Idempotency-Key: moutai-valuation-20260826-01
X-Client-Region: TW
x-routing-strategy: quality_first

{
  "input": "分析茅台當前估值",
  "tools": ["StocksX_get_price", "StocksX_get_fundamentals"],
  "timeout_seconds": 300,
  "metadata": { "session_id": "sess_8f3a1c" }
}
```

### 2.2.2 Response 202 Accepted

| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| `task_id` | string | `agt_` + 26 字元 Crockford Base32 |
| `status` | string | 建立當下必為 `queued` |
| `poll_url` | string | `/api/v1/agent/tasks/{task_id}` |
| `eta_ms` | integer | 粗估，預設 15000 |

狀態機：`queued` → `running` → `succeeded` \| `failed` \| `cancelled`。合法轉換不可回跳。

## 2.3 任務輪詢 `GET /api/v1/agent/tasks/{task_id}`

| 項 | 約束 |
| :--- | :--- |
| `task_id` path | `^agt_[0-9A-HJKMNP-TV-Z]{26}$` |
| 輪詢建議 | 首 10s 每 500ms；之後每 2s；超過 `timeout_seconds` 後任務標記 `failed` / `AGENT_TIMEOUT` |
| 授權 | 僅建立者 `user_id` 可讀，否則 404（防枚舉） |

Response 200 Body：

| 欄位 | 型別 | 說明 |
| :--- | :--- | :--- |
| `task_id` | string | — |
| `status` | enum | 見上 |
| `progress_pct` | integer | 0–100 |
| `chosen_provider` | string \| null | 最後一次模型呼叫的廠商 |
| `cost_usd` | number | 累計實際費用 |
| `latency_ms` | integer \| null | 從 queued 到終態 |
| `result.content` | string \| null | 成功時最終報告 |
| `result.tool_traces` | array | `{tool, latency_ms, http_status}`，不含完整上游原文（審計另存） |
| `error.code` | string \| null | 失敗時 |
| `trace_id` | string | Jaeger |

輪詢示例：

```http
GET /api/v1/agent/tasks/agt_01KFAKEEXAMPLE00000000001 HTTP/1.1
Host: hub.example.com
Authorization: Bearer ak_live_7f3c9e2a1b8d4f06c5a0e91d
```

## 2.4 模型目錄 `GET /api/v1/catalog`

回傳封閉九模型目錄（含 `provider`、智能分、單價、`cn_allowed`）、策略枚舉、`default_chain`、`race_pair`。需 Bearer。`models[].id` 必須與 §1.6 完全一致，不得含任何 Claude / Anthropic ID。

## 2.5 OpenAPI 3.0（完整 schemas，可直接 codegen）

```yaml
openapi: 3.0.3
info:
  title: AI Hub API
  version: 1.2.0
  description: >
    多模型編排公開契約。model enum 為封閉白名單，不含任何 Claude / Anthropic ID。
servers:
  - url: https://hub.example.com
tags:
  - name: Chat
  - name: Agent
paths:
  /api/v1/chat/completions:
    post:
      tags: [Chat]
      operationId: createChatCompletion
      security: [{ bearerAuth: [] }]
      parameters:
        - $ref: '#/components/parameters/XRequestId'
        - $ref: '#/components/parameters/XClientRegion'
        - $ref: '#/components/parameters/RoutingStrategy'
        - $ref: '#/components/parameters/FailoverConfig'
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/ChatCompletionRequest' }
      responses:
        '200':
          description: OK
          headers:
            X-Request-Id: { schema: { type: string, format: uuid } }
            X-Trace-Id: { schema: { type: string, pattern: '^[0-9a-f]{32}$' } }
            X-Chosen-Provider: { schema: { $ref: '#/components/schemas/ProviderCode' } }
            X-Cost-Usd: { schema: { type: string } }
            X-Latency-Ms: { schema: { type: integer, minimum: 0 } }
            X-Hub-Cache: { schema: { type: string, enum: [HIT, MISS, BYPASS] } }
          content:
            application/json:
              schema: { $ref: '#/components/schemas/ChatCompletionResponse' }
        '400': { $ref: '#/components/responses/BadRequest' }
        '401': { $ref: '#/components/responses/Unauthorized' }
        '403': { $ref: '#/components/responses/BudgetExceeded' }
        '415': { $ref: '#/components/responses/UnsupportedMedia' }
        '429': { $ref: '#/components/responses/RateLimited' }
        '503': { $ref: '#/components/responses/AllProvidersUnavailable' }
        '504': { $ref: '#/components/responses/UpstreamTimeout' }
  /api/v1/agent/tasks:
    post:
      tags: [Agent]
      operationId: createAgentTask
      security: [{ bearerAuth: [] }]
      parameters:
        - $ref: '#/components/parameters/XRequestId'
        - $ref: '#/components/parameters/XClientRegion'
        - $ref: '#/components/parameters/RoutingStrategy'
        - $ref: '#/components/parameters/FailoverConfig'
        - in: header
          name: Idempotency-Key
          schema: { type: string, minLength: 8, maxLength: 64, pattern: '^[A-Za-z0-9_-]+$' }
      requestBody:
        required: true
        content:
          application/json:
            schema: { $ref: '#/components/schemas/AgentTaskCreateRequest' }
      responses:
        '202':
          description: Accepted
          content:
            application/json:
              schema: { $ref: '#/components/schemas/AgentTaskCreateResponse' }
        '403': { $ref: '#/components/responses/BudgetExceeded' }
  /api/v1/agent/tasks/{task_id}:
    get:
      tags: [Agent]
      operationId: getAgentTask
      security: [{ bearerAuth: [] }]
      parameters:
        - in: path
          name: task_id
          required: true
          schema: { type: string, pattern: '^agt_[0-9A-HJKMNP-TV-Z]{26}$' }
      responses:
        '200':
          content:
            application/json:
              schema: { $ref: '#/components/schemas/AgentTaskStatus' }
        '404':
          description: 不存在或非建立者（防枚舉，兩者皆 404）
components:
  securitySchemes:
    bearerAuth: { type: http, scheme: bearer, bearerFormat: API-Key }
  parameters:
    XRequestId:
      in: header
      name: X-Request-Id
      schema: { type: string, format: uuid }
    XClientRegion:
      in: header
      name: X-Client-Region
      schema: { type: string, minLength: 2, maxLength: 2, pattern: '^[A-Z]{2}$' }
    RoutingStrategy:
      in: header
      name: x-routing-strategy
      schema:
        type: string
        enum: [cost_first, speed_first, quality_first, manual]
        default: quality_first
    FailoverConfig:
      in: header
      name: x-failover-config
      description: JSON 字串，長度 ≤ 2048；schema 見 FailoverConfigObject
      schema: { type: string, maxLength: 2048 }
  schemas:
    ModelId:
      type: string
      enum:
        - gpt-5.6-sol
        - gemini-3.1-pro
        - mimo-v2.5-pro
        - deepseek-v4-flash
        - qwen3.5-max
        - mercury-2
        - nemotron-3.5-lightning
        - glm-5.2
        - kimi-k3
    ProviderCode:
      type: string
      enum: [openai, google, mimo, deepseek, qwen, inception, nvidia, zhipu, moonshot, cache]
    FailoverConfigObject:
      type: object
      additionalProperties: false
      properties:
        connect_timeout_ms: { type: integer, minimum: 1000, maximum: 60000, default: 25000 }
        read_timeout_ms: { type: integer, minimum: 1000, maximum: 180000, default: 120000 }
        max_retries: { type: integer, minimum: 0, maximum: 5, default: 3 }
        backoff_base: { type: number, minimum: 1.5, maximum: 4, default: 2 }
        model_whitelist:
          type: array
          minItems: 1
          maxItems: 8
          items: { $ref: '#/components/schemas/ModelId' }
        enable_race: { type: boolean, default: false }
    ChatMessage:
      type: object
      required: [role, content]
      additionalProperties: false
      properties:
        role: { type: string, enum: [system, user, assistant, tool] }
        content:
          oneOf:
            - { type: string, minLength: 1, maxLength: 1048576 }
            - { type: array, minItems: 1 }
        tool_call_id: { type: string, maxLength: 64 }
        name: { type: string, maxLength: 64 }
    ChatCompletionRequest:
      type: object
      required: [messages]
      additionalProperties: false
      properties:
        model: { $ref: '#/components/schemas/ModelId' }
        messages:
          type: array
          minItems: 1
          maxItems: 200
          items: { $ref: '#/components/schemas/ChatMessage' }
        temperature: { type: number, minimum: 0, maximum: 2, multipleOf: 0.01, default: 0.7 }
        max_tokens: { type: integer, minimum: 1, maximum: 32768, default: 2048 }
        stream: { type: boolean, default: false }
        user: { type: string, minLength: 1, maxLength: 64, pattern: '^[A-Za-z0-9_-]+$' }
        metadata:
          type: object
          properties:
            session_id: { type: string, minLength: 8, maxLength: 64 }
    ChatCompletionResponse:
      type: object
      required: [id, object, created, model, chosen_provider, cost_usd, latency_ms, choices, usage]
      properties:
        id: { type: string, pattern: '^chatcmpl-[A-Za-z0-9]{26}$' }
        object: { type: string, enum: [chat.completion] }
        created: { type: integer, minimum: 0 }
        model: { $ref: '#/components/schemas/ModelId' }
        chosen_provider: { $ref: '#/components/schemas/ProviderCode' }
        cost_usd: { type: number, minimum: 0, multipleOf: 0.000001 }
        latency_ms: { type: integer, minimum: 0 }
        routing_strategy: { type: string, enum: [cost_first, speed_first, quality_first, manual] }
        failover_hops: { type: integer, minimum: 0, maximum: 5 }
        cache: { type: string, enum: [HIT, MISS, BYPASS] }
        choices:
          type: array
          minItems: 1
          maxItems: 1
          items:
            type: object
            required: [index, finish_reason, message]
            properties:
              index: { type: integer, enum: [0] }
              finish_reason: { type: string, enum: [stop, length, content_filter, tool_calls] }
              message:
                type: object
                required: [role]
                properties:
                  role: { type: string, enum: [assistant] }
                  content: { type: string, maxLength: 524288 }
        usage:
          type: object
          required: [prompt_tokens, completion_tokens, total_tokens]
          properties:
            prompt_tokens: { type: integer, minimum: 0 }
            completion_tokens: { type: integer, minimum: 0 }
            total_tokens: { type: integer, minimum: 0 }
    AgentTaskCreateRequest:
      type: object
      required: [input]
      additionalProperties: false
      properties:
        input: { type: string, minLength: 1, maxLength: 8000 }
        tools:
          type: array
          maxItems: 16
          items:
            type: string
            enum:
              - StocksX_get_price
              - StocksX_get_fundamentals
              - LittleCrawler_fetch
              - StoryForge_draft
              - PysdnOPC_read
              - PysdnOPC_write
        routing_strategy:
          type: string
          enum: [cost_first, speed_first, quality_first, manual]
        callback_url: { type: string, format: uri, maxLength: 512 }
        timeout_seconds: { type: integer, minimum: 30, maximum: 1800, default: 300 }
        metadata:
          type: object
          properties:
            session_id: { type: string, minLength: 8, maxLength: 64 }
    AgentTaskCreateResponse:
      type: object
      required: [task_id, status, poll_url]
      properties:
        task_id: { type: string, pattern: '^agt_[0-9A-HJKMNP-TV-Z]{26}$' }
        status: { type: string, enum: [queued] }
        poll_url: { type: string }
        eta_ms: { type: integer, minimum: 0 }
    AgentTaskStatus:
      type: object
      required: [task_id, status]
      properties:
        task_id: { type: string }
        status: { type: string, enum: [queued, running, succeeded, failed, cancelled] }
        progress_pct: { type: integer, minimum: 0, maximum: 100 }
        chosen_provider: { $ref: '#/components/schemas/ProviderCode' }
        cost_usd: { type: number, minimum: 0 }
        latency_ms: { type: integer, minimum: 0 }
        result:
          type: object
          properties:
            content: { type: string }
            tool_traces:
              type: array
              items:
                type: object
                properties:
                  tool: { type: string }
                  latency_ms: { type: integer }
                  http_status: { type: integer }
        error:
          type: object
          properties:
            code: { type: string }
        trace_id: { type: string, pattern: '^[0-9a-f]{32}$' }
    Problem:
      type: object
      required: [type, title, status, code]
      properties:
        type: { type: string, format: uri }
        title: { type: string }
        status: { type: integer }
        code: { type: string }
        detail: { type: string, maxLength: 80 }
  responses:
    BadRequest:
      description: 欄位 / 敏感詞 / 屬地×模態 / 目錄外模型
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    Unauthorized:
      description: API Key 無效
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    BudgetExceeded:
      description: 日預算攔截，零上游請求
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    UnsupportedMedia:
      description: Content-Type 必須為 application/json; charset=utf-8
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    RateLimited:
      description: Kong 或使用者 RPM
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    AllProvidersUnavailable:
      description: 白名單模型全部熔斷
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
    UpstreamTimeout:
      description: 主模型 >120s 且 Failover 仍失敗
      content:
        application/problem+json:
          schema: { $ref: '#/components/schemas/Problem' }
```

---

# 第三章：資料庫與快取詳細設計（ER 圖與 Schema）

## 3.1 ER 圖

```mermaid
erDiagram
    USERS ||--o{ CALL_LOGS : "user_id"
    USERS ||--o{ AGENT_TASKS : "user_id"
    AGENT_TASKS ||--o{ CALL_LOGS : "task_id nullable"
    USERS {
        uuid id PK
        varchar_64 name
        char_64 api_key_hash
        numeric_12_6 monthly_budget_limit_usd
        numeric_12_6 daily_budget_limit_usd
        jsonb preferred_models
        char_2 home_region
        boolean data_egress_ack
        timestamptz created_at
        timestamptz updated_at
    }
    CALL_LOGS {
        varchar_32 id PK
        uuid user_id FK
        varchar_64 session_id
        varchar_32 task_id
        varchar_16 provider
        varchar_64 model_name
        int prompt_tokens
        int completion_tokens
        numeric_12_6 cost_usd
        varchar_16 status
        int latency_ms
        varchar_64 error_code
        varchar_32 trace_id
        timestamptz create_time
    }
    AGENT_TASKS {
        varchar_32 task_id PK
        uuid user_id FK
        varchar_16 status
        text input
        jsonb tools
        numeric_12_6 cost_usd
        timestamptz created_at
        timestamptz finished_at
    }
```

## 3.2 PostgreSQL DDL

```sql
-- 編碼 / 時區
-- encoding UTF8, timezone UTC

CREATE TABLE users (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                        VARCHAR(64)  NOT NULL,
    api_key_hash                CHAR(64)     NOT NULL,           -- SHA-256 hex
    monthly_budget_limit_usd    NUMERIC(12,6) NOT NULL DEFAULT 100.000000
                                CHECK (monthly_budget_limit_usd >= 0),
    daily_budget_limit_usd      NUMERIC(12,6) NOT NULL DEFAULT 10.000000
                                CHECK (daily_budget_limit_usd >= 0),
    preferred_models            JSONB        NOT NULL DEFAULT '[]'::jsonb,
    home_region                 CHAR(2)      NOT NULL DEFAULT 'ZZ',
    data_egress_ack             BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_users_api_key_hash UNIQUE (api_key_hash),
    CONSTRAINT ck_users_name_len CHECK (char_length(name) BETWEEN 1 AND 64),
    CONSTRAINT ck_preferred_models_is_array CHECK (jsonb_typeof(preferred_models) = 'array')
);

COMMENT ON COLUMN users.preferred_models IS
    '字串陣列，元素必須為模型目錄 ID，最多 8 個；例 ["gpt-5.6-sol","deepseek-v4-flash"]';

-- preferred_models JSON Schema（應用層校驗，寫入前必須通過）
-- {
--   "type": "array",
--   "maxItems": 8,
--   "uniqueItems": true,
--   "items": { "enum": ["gpt-5.6-sol","gemini-3.1-pro","mimo-v2.5-pro",
--                       "deepseek-v4-flash","qwen3.5-max","mercury-2",
--                       "nemotron-3.5-lightning","glm-5.2","kimi-k3"] }
-- }

CREATE TABLE call_logs (
    id                  VARCHAR(32)  PRIMARY KEY,                -- chatcmpl-... 或 span id
    user_id             UUID         NOT NULL REFERENCES users(id),
    session_id          VARCHAR(64)  NOT NULL DEFAULT '',
    task_id             VARCHAR(32),                             -- 可空；Agent 任務關聯
    provider            VARCHAR(16)  NOT NULL,
    model_name          VARCHAR(64)  NOT NULL,
    prompt_tokens       INTEGER      NOT NULL DEFAULT 0 CHECK (prompt_tokens >= 0),
    completion_tokens   INTEGER      NOT NULL DEFAULT 0 CHECK (completion_tokens >= 0),
    cost_usd            NUMERIC(12,6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    status              VARCHAR(16)  NOT NULL,
    latency_ms          INTEGER      NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    error_code          VARCHAR(64)  NOT NULL DEFAULT '',
    trace_id            VARCHAR(32)  NOT NULL DEFAULT '',
    create_time         TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT ck_call_logs_status CHECK (
        status IN ('success','timeout','rate_limited','filtered','failed','budget_denied')
    )
);

-- 強制索引：使用者維度時間掃描（帳單、日預算聚合）
CREATE INDEX idx_call_logs_user_ctime
    ON call_logs (user_id, create_time DESC);

CREATE INDEX idx_call_logs_status_ctime
    ON call_logs (status, create_time DESC)
    WHERE status <> 'success';

CREATE INDEX idx_call_logs_task
    ON call_logs (task_id)
    WHERE task_id IS NOT NULL;

CREATE TABLE agent_tasks (
    task_id      VARCHAR(32) PRIMARY KEY,
    user_id      UUID        NOT NULL REFERENCES users(id),
    status       VARCHAR(16) NOT NULL,
    input        TEXT        NOT NULL,
    tools        JSONB       NOT NULL DEFAULT '[]'::jsonb,
    cost_usd     NUMERIC(12,6) NOT NULL DEFAULT 0,
    result       JSONB,
    error_code   VARCHAR(64) NOT NULL DEFAULT '',
    trace_id     VARCHAR(32) NOT NULL DEFAULT '',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    CONSTRAINT ck_agent_status CHECK (
        status IN ('queued','running','succeeded','failed','cancelled')
    )
);

CREATE INDEX idx_agent_tasks_user_created
    ON agent_tasks (user_id, created_at DESC);
```

`preferred_models` 應用層校驗：每個元素必須 ∈ §1.6 目錄（精確字串比對、大小寫敏感）。任一元素不在目錄 → **直接 400** `UNSUPPORTED_MODEL`，且 **不得** 把該字串轉發到 LiteLLM 或任何上游。

## 3.3 日預算聚合（避免全表掃）

不以每次 `SUM(call_logs)` 做熱路徑。寫入 `call_logs` 成功後，同步：

```
INCRBYFLOAT budget:daily:{user_id}:{YYYYMMDD} {cost_usd}
EXPIREAT 該 key 至次日 00:00 UTC + 86400s
```

日攔截讀 Redis，PostgreSQL 僅作對帳（每 5 分鐘 job 校正誤差 > $0.01）。

## 3.4 快取設計

### 3.4.1 Redis 實例參數（強制）

```conf
maxmemory 1536mb
maxmemory-policy allkeys-lru
tcp-backlog 511
timeout 0
hz 10
```

熱點 Key 另用 ZSET 記錄命中，供運維淘汰與命中率報表：

| Key | 型別 | Value | TTL |
| :--- | :--- | :--- | :--- |
| `semantic:{md5}` | STRING | 完整歷史回覆 JSON（ChatCompletionResponse 子集） | 86400s |
| `semantic:hot` | ZSET | member=`{md5}` score=命中次數 | 無（LRU 仍可能驅逐 member 對應 STRING） |
| `provider:metrics` | HASH | field=`{provider}:{model}` value=JSON `{latency_ewma_ms,price_out_per_1m,ts}` | 無（每 30s 覆寫） |
| `budget:daily:{uid}:{yyyymmdd}` | STRING | 浮點字串 | 至隔日 |
| `cb:{provider}:{model}` | HASH | `{state,fail_ratio,opened_at}` | 與熔斷器同位 |

語義快取 Key 算法（契約，不可改成「整段 prompt 的 md5」，以免溫度/無關空白導致命中率崩潰）：

1. 取最後一則 `user` content，NFKC 正規化、壓縮空白、小寫。
2. 截斷至 512 字元得到「意圖摘要」。
3. `key = "semantic:" + md5_hex(user_id + ":" + routing_strategy + ":" + 摘要)`。
4. `user_id` 納入 Key，禁止跨租戶命中。
5. `temperature>0.2` 或 `stream=true` 或含多模態 part → `BYPASS`（不讀不寫）。

**命中率 SLO：** 滾動 24h `HIT / (HIT+MISS)` **> 40%**。低於 35% 觸發 P3 告警；連續 2h < 30% 觸發 P2。實現：`INCR hub:metrics:cache:hit|miss`，Grafana 每分鐘寫 Prometheus。

熱點維護：每次 HIT 執行 `ZINCRBY semantic:hot 1 {md5}`；每日 03:00 UTC `ZREMRANGEBYRANK semantic:hot 0 -1001` 只留 Top 1000。

### 3.4.2 廠商價格 / 延遲探針

- 週期：每 **30 秒**，由 `ai-hub-core` 內 `ProbeScheduler`（單 Replica 用 Redis `SET probe:lock NX PX 25000` 選主）對每個模型發 **8 token** 的 `ping` completion。
- 連線逾時 2s、讀取逾時 5s；失敗則 `latency_ewma_ms=15000`（懲罰）且 `consecutive_fail+=1`。
- EWMA：`ewma = 0.7 * prev + 0.3 * sample`。
- HASH 欄位值示例：

```json
{
  "latency_ewma_ms": 412.5,
  "ttfb_ms": 186,
  "price_in_per_1m": 3.0,
  "price_out_per_1m": 30.0,
  "consecutive_fail": 0,
  "ts": 1787731210
}
```

ChromaDB 僅存意圖摘要向量（384 維），供「近義命中」二期使用；**一期語義快取只走 Redis 精確 md5**，避免與既有 EvoLoop 記憶集合混用。Hub collection 名稱固定 `hub_semantic_v1`。

---

# 第四章：多方智能路由引擎核心算法（含詳細偽代碼）

模組位置（規劃）：`backend/hub/router.py`。此模組 **只** 透過 `backend.core.llm.call_llm` / 串流變體發請求，滿足架構測試中的廠商 SDK 禁令。

## 4.0 智能分目錄（靜態，可由設定覆寫）

| model | intelligence_score（0–100） |
| :--- | ---: |
| gpt-5.6-sol | 96 |
| gemini-3.1-pro | 92 |
| mimo-v2.5-pro | 88 |
| qwen3.5-max | 86 |
| kimi-k3 | 85 |
| glm-5.2 | 85 |
| deepseek-v4-flash | 84 |
| mercury-2 | 78 |
| nemotron-3.5-lightning | 74 |

## 4.1 動態權重計算

公式（契約）：

```
Score = (intelligence_score * w_intel) - (latency_ms * 0.001) - (price_out_per_1m * 0.5)
```

`latency_ms`、`price_out_per_1m` 取自 `provider:metrics`；缺失時用目錄預設，並將 Score 再減 5（未知懲罰）。

`x-routing-strategy` → 係數：

| strategy | `w_intel` | 額外規則 |
| :--- | ---: | :--- |
| `quality_first` | 1.00 | 預設；CN 屬地仍先過濾境外模型 |
| `cost_first` | 0.25 | 另將 `price_out_per_1m * 0.5` 改為 `* 2.0` |
| `speed_first` | 0.40 | 另將 `latency_ms * 0.001` 改為 `* 0.008`；允許 Race |
| `manual` | — | 不計算 Score，使用 Body `model` |

CN 屬地：先 `candidates = candidates ∩ CN_SET`，若交集為空 → 403 `DATA_EGRESS_FORBIDDEN`。

```python
"""Router.py — 動態權重 + Failover + Race。禁止 import 廠商 SDK。"""
from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable

CN_SET = frozenset({"deepseek-v4-flash", "qwen3.5-max", "mimo-v2.5-pro"})
INTEL = {
    "gpt-5.6-sol": 96,
    "gemini-3.1-pro": 92,
    "mimo-v2.5-pro": 88,
    "qwen3.5-max": 86,
    "kimi-k3": 85,
    "glm-5.2": 85,
    "deepseek-v4-flash": 84,
    "mercury-2": 78,
    "nemotron-3.5-lightning": 74,
}
DEFAULT_CHAIN = ("gpt-5.6-sol", "gemini-3.1-pro", "deepseek-v4-flash", "glm-5.2")
CONNECT_TIMEOUT_S = 25.0
READ_TIMEOUT_S = 120.0
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


@dataclass
class Metrics:
    latency_ms: float
    price_out_per_1m: float


@dataclass
class RouteDecision:
    model: str
    provider: str
    score: float
    reason: str


def score_model(model: str, metrics: Metrics, strategy: str) -> float:
    w_intel = {"quality_first": 1.00, "cost_first": 0.25, "speed_first": 0.40}[strategy]
    lat_coef = 0.008 if strategy == "speed_first" else 0.001
    price_coef = 2.0 if strategy == "cost_first" else 0.5
    return (
        INTEL[model] * w_intel
        - metrics.latency_ms * lat_coef
        - metrics.price_out_per_1m * price_coef
    )


def filter_by_region(models: Iterable[str], region: str) -> list[str]:
    models = list(models)
    if region.upper() == "CN":
        return [m for m in models if m in CN_SET]
    return models


def pick_primary(
    strategy: str,
    region: str,
    whitelist: list[str] | None,
    metrics_by_model: dict[str, Metrics],
    manual_model: str | None,
) -> RouteDecision:
    if strategy == "manual":
        if not manual_model:
            raise ValueError("MANUAL_MODEL_REQUIRED")
        allowed = filter_by_region([manual_model], region)
        if not allowed:
            raise PermissionError("DATA_EGRESS_FORBIDDEN")
        return RouteDecision(manual_model, provider_of(manual_model), float("nan"), "manual")

    pool = list(whitelist or INTEL.keys())
    pool = filter_by_region(pool, region)
    if not pool:
        raise PermissionError("DATA_EGRESS_FORBIDDEN")

    ranked: list[RouteDecision] = []
    for m in pool:
        met = metrics_by_model.get(m) or Metrics(latency_ms=800.0, price_out_per_1m=4.0)
        s = score_model(m, met, strategy)
        if m not in metrics_by_model:
            s -= 5.0
        ranked.append(RouteDecision(m, provider_of(m), s, "weighted"))
    ranked.sort(key=lambda d: d.score, reverse=True)
    return ranked[0]


def provider_of(model: str) -> str:
    return {
        "gpt-5.6-sol": "openai",
        "gemini-3.1-pro": "google",
        "mimo-v2.5-pro": "mimo",
        "deepseek-v4-flash": "deepseek",
        "qwen3.5-max": "qwen",
        "mercury-2": "inception",
        "nemotron-3.5-lightning": "nvidia",
        "glm-5.2": "zhipu",
        "kimi-k3": "moonshot",
    }[model]
```

## 4.2 跨廠商故障轉移（Failover）鏈

- 標準逾時：**25s 連線 + 120s 讀取**（可被 `x-failover-config` 覆寫，但不得超過 Schema 上限）。
- 重試：指數退避，**基數 2**，**最多 3 次**（含首次共 4 次嘗試落在同一模型上，之後才切模型）。
- 等待秒數：`sleep = BACKOFF_BASE ** attempt + uniform(0, 0.2)`，attempt 從 0 起：1s、2s、4s。
- 切換條件：HTTP 429、503、連線失敗、讀取逾時、熔斷器 Open。
- 預設鏈（非 CN）：**gpt-5.6-sol → gemini-3.1-pro → deepseek-v4-flash → glm-5.2**。
- 若白名單不含下一跳，跳過該跳。
- CN：鏈為 **deepseek-v4-flash → qwen3.5-max → mimo-v2.5-pro**（無境外、無 glm 除非 `data_egress_ack`）。

```python
def backoff_sleep(attempt: int) -> float:
    return (BACKOFF_BASE ** attempt) + random.uniform(0.0, 0.2)


def failover_chain(primary: str, region: str, whitelist: list[str] | None) -> list[str]:
    if region.upper() == "CN":
        chain = ["deepseek-v4-flash", "qwen3.5-max", "mimo-v2.5-pro"]
    else:
        chain = list(DEFAULT_CHAIN)
        if primary in chain:
            chain.remove(primary)
        chain.insert(0, primary)
    if whitelist:
        allowed = set(whitelist)
        chain = [m for m in chain if m in allowed]
    return chain


def should_switch(exc: BaseException, status_code: int | None) -> bool:
    if status_code in {429, 503}:
        return True
    name = type(exc).__name__
    return name in {"TimeoutError", "ConnectTimeout", "ReadTimeout", "CircuitOpenError"}


def invoke_with_failover(
    call_llm: Callable[..., str],
    messages: list[dict],
    primary: str,
    region: str,
    whitelist: list[str] | None,
    connect_s: float = CONNECT_TIMEOUT_S,
    read_s: float = READ_TIMEOUT_S,
) -> tuple[str, str, int]:
    """回傳 (text, model, hops)。hops=切換次數。"""
    hops = 0
    last_err: Exception | None = None
    for model in failover_chain(primary, region, whitelist):
        for attempt in range(MAX_RETRIES + 1):
            t0 = time.monotonic()
            try:
                text = call_llm(
                    prompt=messages[-1]["content"],
                    system=_system_from(messages),
                    model=model,
                    timeout=connect_s + read_s,
                )
                return text, model, hops
            except Exception as exc:  # noqa: BLE001 — 路由層需分類後再拋
                last_err = exc
                status = getattr(exc, "status_code", None)
                if time.monotonic() - t0 > read_s or should_switch(exc, status):
                    if attempt < MAX_RETRIES and status not in {429, 503}:
                        time.sleep(backoff_sleep(attempt))
                        continue
                    hops += 1
                    break
                if attempt < MAX_RETRIES:
                    time.sleep(backoff_sleep(attempt))
                    continue
                hops += 1
                break
    raise TimeoutError("ALL_PROVIDERS_UNAVAILABLE") from last_err
```

與既有 `backend/core/llm.py` 的差異：現有 `call_llm` 已對 **同一模型** 做 3 次線性退避。Hub 路由器在切換模型前，應將 LiteLLM 層重試降為 1，避免 3×3 次放大延遲（實作時給 `call_llm` 增加 `max_retries=1` 參數，**預設保持 3 以不破壞既有反思閉環**）。

## 4.3 多方並發競速（Race to the Top）

觸發條件（全部滿足）：

1. `x-routing-strategy=speed_first` **或** `x-failover-config.enable_race=true`
2. 屬地 **不是** CN（CN 禁止同時打境外）
3. 任務非多步驟 Agent（Agent 走 Failover，避免雙倍工具副作用）

競速配對（契約）：**gemini-3.1-pro** 與 **mercury-2**。誰先產出有效串流首字節且 **TTFB < 200ms**，即 `aclose()` 另一路。若雙方 TTFB ≥ 200ms，改取較早的有效首字節者；若 2s 內無人產出有效 token，取消競速，落入 Failover 鏈（主模型 gpt-5.6-sol）。

「有效串流」定義：HTTP 200 + `data:` SSE 行可解析出 `choices[0].delta.content` 長度 ≥ 1，且不是心跳 `: ping`。

```python
import asyncio


async def race_to_the_top(
    stream_factory: Callable[[str], "AsyncIterator[bytes]"],
    ttfb_deadline_ms: int = 200,
) -> tuple[str, bytes]:
    models = ("gemini-3.1-pro", "mercury-2")
    winner: asyncio.Future = asyncio.get_event_loop().create_future()
    tasks: list[asyncio.Task] = []

    async def run(model: str) -> None:
        agen = stream_factory(model)
        t0 = time.monotonic()
        try:
            first = await asyncio.wait_for(agen.__anext__(), timeout=2.0)
        except Exception:
            return
        ttfb_ms = (time.monotonic() - t0) * 1000
        if not _is_valid_sse_first_byte(first):
            return
        if not winner.done():
            winner.set_result((model, first, ttfb_ms, agen))

    for m in models:
        tasks.append(asyncio.create_task(run(m)))

    done, _ = await asyncio.wait({winner, *tasks}, return_when=asyncio.FIRST_COMPLETED)
    if not winner.done():
        for t in tasks:
            t.cancel()
        raise TimeoutError("RACE_NO_VALID_TTFB")

    model, first, ttfb_ms, agen = winner.result()
    for t in tasks:
        t.cancel()
    # TTFB 門檻僅作為「優先採用」訊號；勝者已是第一個有效流
    _ = ttfb_deadline_ms
    # 呼叫端繼續迭代 agen，並在 finally 取消另一模型的 HTTP 連線
    return model, first
```

---

# 第五章：Hermes Agent 與 GitHub 倉庫集成時序圖（含報文示例）

場景：使用者輸入「分析茅台當前估值」。Tracing：`traceparent=00-{trace_id}-{span_id}-01`，本例 `trace_id=4bf92f3577b34da6a3ce929d0e0e4736`。

```mermaid
sequenceDiagram
    autonumber
    actor U as 使用者
    participant K as Kong
    participant H as AI Hub Core
    participant R as Redis
    participant A as Hermes Agent
    participant S as StocksX :9101
    participant L as LiteLLM
    participant G as GPT-5.6 Sol
    participant Q as Qwen3.5-Max
    participant J as Jaeger

    U->>K: POST /api/v1/agent/tasks<br/>Authorization: Bearer ak_live_...
    K->>K: JWT/API Key → user_id
    K->>H: 轉發 + traceparent
    H->>R: GET budget:daily:{uid}:{day}
    H-->>U: 202 {"task_id":"agt_01KFAKEEXAMPLE00000000001","status":"queued"}
    H->>A: gRPC StartTask
    A->>L: POST /v1/chat/completions tools=[StocksX_get_price]
    L->>G: 上游 Chat
    G-->>L: tool_calls StocksX_get_price
    L-->>A: assistant tool_call
    A->>S: POST /rpc/StocksX_get_price JWT
    S-->>A: {"current_price":1888,"pe_ratio":28.5}
    A->>L: 二次 completion messages+tool
    L->>G: 生成投資建議
    Note over L,G: 若 429/503 → 改打 Qwen3.5-Max
    G-->>L: 最終 content
    L-->>A: chat.completion
    A->>H: TaskSucceeded
    H->>J: OTLP span 樹
    U->>H: GET /api/v1/agent/tasks/agt_01KFAKEEXAMPLE00000000001
    H-->>U: status=succeeded + result
```

## 5.1 報文 ① Hub → Hermes（OpenAI Chat + tools）

`POST http://hermes-agent:11434/v1/chat/completions`

```http
POST /v1/chat/completions HTTP/1.1
Host: hermes-agent:11434
Content-Type: application/json; charset=utf-8
Authorization: Bearer hermes-internal-s2s
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
X-Hub-User-Id: 3f1a0c2e-7b44-4d91-9c2a-1b8e6d4f0a11
X-Client-Region: TW

{
  "model": "gpt-5.6-sol",
  "stream": false,
  "temperature": 0.2,
  "max_tokens": 1200,
  "messages": [
    {
      "role": "system",
      "content": "你是金融分析子代理。必須先呼叫 StocksX_get_price 再給估值結論。禁止臆造行情。"
    },
    {
      "role": "user",
      "content": "分析茅台當前估值"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "StocksX_get_price",
        "description": "取得 A 股即時價與估值指標",
        "parameters": {
          "type": "object",
          "additionalProperties": false,
          "required": ["symbol"],
          "properties": {
            "symbol": { "type": "string", "minLength": 1, "maxLength": 16, "pattern": "^[0-9A-Za-z\\.]+$" }
          }
        }
      }
    }
  ]
}
```

Hermes 回傳 tool_call（節錄）：

```json
{
  "choices": [{
    "finish_reason": "tool_calls",
    "message": {
      "role": "assistant",
      "tool_calls": [{
        "id": "call_8f3a1c",
        "type": "function",
        "function": {
          "name": "StocksX_get_price",
          "arguments": "{\"symbol\":\"600519.SH\"}"
        }
      }]
    }
  }]
}
```

## 5.2 報文 ② Hermes → StocksX（RPC over HTTP + JWT）

`POST http://stocksx:9101/rpc/StocksX_get_price`

JWT 聲明（HS256，TTL 60s）：`iss=ai-hub`，`aud=stocksx`，`sub={user_id}`，`scope=stocksx:read`，`jti` 一次性。StocksX 校驗 `aud` 與時鐘偏移 ≤ 30s。

```http
POST /rpc/StocksX_get_price HTTP/1.1
Host: stocksx:9101
Content-Type: application/json; charset=utf-8
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
Idempotency-Key: call_8f3a1c
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-1111111111111111-01
X-Timeout-Ms: 8000

{"symbol": "600519.SH"}
```

StocksX 200：

```json
{
  "symbol": "600519.SH",
  "name": "貴州茅台",
  "currency": "CNY",
  "current_price": 1888,
  "pe_ratio": 28.5,
  "as_of": "2026-08-26T06:00:00Z"
}
```

邊界：`symbol` 不匹配 pattern → 400；上游行情所逾時 → 504，Hermes **不得** 用過期快取冒充即時價（行情 Key `hub:quotes:` TTL 最多 15s，且 response 必須標 `stale=false`）。

## 5.3 報文 ③ 二次呼叫 GPT-5.6 Sol（tool 結果拼入 messages）

契約：工具 JSON **以 `role=tool` 訊息** 傳入，而不是覆寫 system prompt 全文。System 僅追加一行約束：「以下 tool 結果為唯一行情來源」。

```json
{
  "model": "gpt-5.6-sol",
  "messages": [
    { "role": "system", "content": "你是金融分析子代理。……以下 tool 結果為唯一行情來源。" },
    { "role": "user", "content": "分析茅台當前估值" },
    {
      "role": "assistant",
      "tool_calls": [{
        "id": "call_8f3a1c",
        "type": "function",
        "function": { "name": "StocksX_get_price", "arguments": "{\"symbol\":\"600519.SH\"}" }
      }]
    },
    {
      "role": "tool",
      "tool_call_id": "call_8f3a1c",
      "content": "{\"current_price\":1888,\"pe_ratio\":28.5}"
    }
  ]
}
```

**降級：** 若 GPT-5.6 Sol 回 429/503，同一 messages 改 `model=qwen3.5-max`（中國主力，長文本足夠承載 tool JSON）。記錄 `failover_hops=1`，`chosen_provider=qwen`。

## 5.4 回傳使用者 + Tracing

輪詢 200 節錄：

```json
{
  "task_id": "agt_01KFAKEEXAMPLE00000000001",
  "status": "succeeded",
  "chosen_provider": "openai",
  "cost_usd": 0.058140,
  "latency_ms": 4820,
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "result": {
    "content": "茅台現價 1888 元，PE 28.5……（完整投資建議）",
    "tool_traces": [
      { "tool": "StocksX_get_price", "latency_ms": 142, "http_status": 200 }
    ]
  }
}
```

Jaeger 必含 spans：`kong.request` → `hub.budget_guard` → `hermes.task` → `llm.gpt-5.6-sol#1` → `rpc.StocksX_get_price` → `llm.gpt-5.6-sol#2`（或 `llm.qwen3.5-max#2`）。每個 span 帶 `user.id`、`model`、`cost_usd`。

PysdnOPC 若被掛載：只允許 `PysdnOPC_read` 進入金融場景預設工具集；`PysdnOPC_write` 必須額外 `scope=opc:write` 且走 `opc_service` 護欄，本場景不得出現。

## 5.5 報文 ④ Hermes → LittleCrawler（白名單 URL）

`POST http://littlecrawler:9102/rpc/LittleCrawler_fetch`

JWT：`aud=littlecrawler`，`scope=crawler:read`。URL 必須 ∈ 白名單，否則 400，**零出站 HTTP**。

```http
POST /rpc/LittleCrawler_fetch HTTP/1.1
Host: littlecrawler:9102
Content-Type: application/json; charset=utf-8
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-2222222222222222-01
X-Timeout-Ms: 8000

{"url": "https://finance.example.com/600519", "max_chars": 4000}
```

```json
{
  "url": "https://finance.example.com/600519",
  "title": "貴州茅台估值快訊",
  "excerpt": "現價 1888 元，滾動 PE 28.5，成交量溫和放大。",
  "status": 200,
  "chars": 48,
  "stale": false
}
```

邊界：`max_chars` 1–4000；非 `https` → 400；白名單外 → 400 `URL 不在爬蟲白名單。`

## 5.6 報文 ⑤ Hermes → StoryForge（創意大綱，非最終正文）

`POST http://storyforge:9103/rpc/StoryForge_draft`

JWT：`aud=storyforge`，`scope=story:draft`。本工具只回結構大綱，最終敘事仍由 GPT-5.6 Sol（或 Qwen3.5-Max）合成，避免雙重計費與幻構事實。

```json
{
  "premise": "分析茅台當前估值",
  "genre": "literary",
  "max_tokens": 800
}
```

```json
{
  "title_candidates": ["分析茅台當前估值·序章", "分析茅台當前估值·迴聲"],
  "genre": "literary",
  "outline": [
    {"beat": 1, "summary": "建立衝突與視角人物"},
    {"beat": 2, "summary": "情報反轉，迫使選擇"},
    {"beat": 3, "summary": "收束主題並留下餘韻"}
  ],
  "constraints": {"max_tokens": 800, "must_not_fabricate_facts": true}
}
```

## 5.7 報文 ⑥ Hermes → PysdnOPC Adapter → opc_service（只讀）

契約：Adapter `:9104` **必須** 轉發 `POST http://opc_service:8001/opc/read`，請求體對齊 `opc_service.models.read.ReadRequest`。禁止 `asyncua` / 直連 UA。寫入路徑不存在於此工具；`PysdnOPC_write` → 400 `OPC_GUARD_REQUIRED`。

```http
POST /opc/read HTTP/1.1
Host: opc_service:8001
Content-Type: application/json; charset=utf-8
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
X-Timeout-Ms: 8000

{"tag_names": ["Temperature", "Pressure", "FlowRate"]}
```

```json
{
  "via": "opc_service",
  "endpoint": "POST /opc/read",
  "guard_bypassed": false,
  "tags": [
    {"tag_name": "Temperature", "value": 86.4, "data_type": "Double", "quality": "Good"},
    {"tag_name": "Pressure", "value": 2.1, "data_type": "Double", "quality": "Good"},
    {"tag_name": "FlowRate", "value": 12.8, "data_type": "Double", "quality": "Good"}
  ],
  "error": null
}
```

即時訂閱（非 Agent 熱路徑）：`WebSocket wss://opc_service:8001/opc/ws`，僅推送白名單標籤，心跳 15s。Hub Agent **不** 在工具呼叫中持有長連線。

`tag_names` 長度 1–50；未知標籤回 `quality=Bad`、`value=null`，不視為 5xx。

## 5.8 UI/web 操作台（非 RPC 工具）

`UI/web` 不是 Hermes `tools[]` 成員。它是既有 SPA（`frontend/src/components/HubView.tsx`）：

| 面 | 路徑 | 行為 |
| :--- | :--- | :--- |
| 同步推論 | `POST /api/v1/chat/completions` | 策略 / 屬地 / 手動模型 |
| Agent | `POST /api/v1/agent/tasks` + 輪詢 | 可多選 StocksX / Crawler / StoryForge / PysdnOPC_read |
| 目錄 | `GET /api/v1/catalog` | 九模型、零 Claude |

意圖自動掛載（Body 省略 `tools` 時）：含「茅台/估值/股市」→ `StocksX_get_price`；含 URL 或「爬」→ `LittleCrawler_fetch`；含「故事」→ `StoryForge_draft`；含「工業/OPC/溫度」→ `PysdnOPC_read`。

---

# 第六章：成本控制與熔斷降級具體配置

## 6.1 熔斷器（Resilience4j 風格）

每個 `{provider, model}` 一組實例。對應 Redis `cb:{provider}:{model}`，避免多副本狀態分裂。

| 參數 | 值 | 含義 |
| :--- | :--- | :--- |
| `slidingWindowType` | `COUNT_BASED` | — |
| `slidingWindowSize` | 20 | 最近 20 次呼叫 |
| `minimumNumberOfCalls` | 10 | 未滿 10 次不開閘 |
| `failureRateThreshold` | 50 | 錯誤率達 **50%** 開啟熔斷 |
| `slowCallDurationThreshold` | 10s | 慢呼叫計入失敗 |
| `slowCallRateThreshold` | 80 | — |
| `waitDurationInOpenState` | 10s | **熔斷後等 10 秒** 進入 HALF_OPEN |
| `permittedNumberOfCallsInHalfOpenState` | 2 | 半開放行 2 次 |
| `automaticTransitionFromOpenToHalfOpenEnabled` | true | — |
| `recordExceptions` | Timeout、429、5xx | 4xx（除 429）不計入失敗率 |

Open 態行為：該模型立即從候選集剔除，走 Failover 下一跳；**不** 向使用者回 503，除非鏈耗盡。

半開失敗 → 重新 Open，`waitDurationInOpenState` 仍為 10s（不做指數拉長，避免與 LLM 退避疊加過久）。連續 5 次 Open 週期失敗 → 該模型標記 `disabled_until=now+15min`，P2 告警。

## 6.2 每日預算攔截（呼叫前硬閘）

順序（必須在任何上游 I/O 之前）：

1. 以 `tiktoken` 或模型對應 tokenizer 估算 `input_tokens`；`expected_output_tokens = max_tokens`（請求未帶則 2048）。
2. 取即將選中的 **主模型** 目錄單價（尚未 Failover）。
3. 計算：

```
預估費用 = ((輸入 Token 數 × 輸入單價) + (期望輸出 Token 數 × 輸出單價)) × 1.2
```

單價單位：USD / 1M tokens。1.2 為預留係數（工具二次呼叫、重試、探針攤銷）。

4. 讀 `spent_today = GET budget:daily:{uid}:{yyyymmdd}`（無 Key 視作 0）。
5. 若 `spent_today + 預估費用 > users.daily_budget_limit_usd` → **不呼叫任何模型**，HTTP **403**，`code=BUDGET_EXCEEDED`。

使用者可見訊息（繁中，固定文案，長度 ≤ 80）：

> 今日預算不足，已攔截本次呼叫。請充值或將 x-routing-strategy 改為 cost_first 後重試。

運維：P4 審計日誌即可；同一 user 1h 內攔截 ≥ 20 次 → P3。

Agent 任務：建立時用 `expected_output_tokens=4096` 且再乘工具次數估計 `1 + len(tools)`，即：

```
預估費用_agent = 預估費用_單次 × (1 + len(tools)) × 1.2
```

（外層已有 1.2 時，實作注意 **不要雙重乘 1.2**。契約：Agent 僅在單次公式上改用 `(1+len(tools))` 取代額外 1.2，或明確 `buffer=1.2` 只乘一次。採用：**buffer 只乘一次**。）

## 6.3 與既有公司預算模組的邊界

| 模組 | 管什麼 | 不管什麼 |
| :--- | :--- | :--- |
| `backend/company/budget.py` `BudgetManager` | LangGraph 公司運行時的 task/session/month 限額 | Hub `/api/v1/*` |
| Hub `budget:daily:*` | Hub 日限額硬閘 | EvoLoop `/chat` |

兩者 **不共享計數器**，避免雙重 403。帳單產品若要合併，在報表層 `UNION`，不在熱路徑耦合。

## 6.4 成本優化落地（非空泛）

- 語義快取 HIT 時 `cost_usd=0`，仍寫 `call_logs.status=success`、`provider=cache`、`model_name=semantic-cache`，便於命中率對帳。
- `cost_first` 在非 CN 預設偏向 `deepseek-v4-flash`（$0.66/M 輸出 off-peak）而非旗艦。
- 探針使用 `nemotron-3.5-lightning`（$0）做延遲基準時，**不得** 把其 Score 用於 quality_first 主選（智能分過低），僅更新 `provider:metrics` 的跨廠比較需要時另計。

---

# 第七章：異常處理矩陣（Error Handling Matrix）

| 異常場景 | 狀態碼 | 系統自動處理動作 | 使用者看到的訊息 | 運維告警 |
| :--- | :--- | :--- | :--- | :--- |
| 主模型逾時（讀取 >120s） | 504（Failover 仍失敗時）或 200（切換成功） | 立即 Failover 至 Gemini 3.1 Pro 或 DeepSeek V4 Flash，再 GLM-5.2；寫 `failover_hops` | 切換成功：「當前高峰期，已為您切換至備用高速通道」。鏈耗盡：「上游回應逾時，請稍後重試。」 | P2（鏈耗盡）；P4（單跳成功） |
| 主模型 429 / 503 | 200 或 503 | 指數退避 3 次後切備援；熔斷器計入失敗 | 切換成功：同上「備用高速通道」。全部不可用：「模型服務暫時繁忙，請稍後再試。」 | P2 若單模型 Open ≥ 2 分鐘 |
| 返回內容涉及敏感詞 | 400 | 截斷 `choices[].message.content` 為空；`finish_reason=content_filter`；寫審計表 / `call_logs.status=filtered`；**不** 把原文送前端 | 「生成內容不符合社區規範，請修改問題」 | P3（同一 user 10min ≥ 5 次升 P2） |
| Hermes Agent 行程崩潰 | 503 對同步面；任務面 `status=running` 保持 | Kubernetes `restartPolicy=Always`；Pod 新啟動後從 Redis `hub:task:{id}` 恢復 cursor；會話 token 不落磁碟 | 輪詢端無感知（內部重試）。若 30s 未恢復：任務 `failed`，「代理服務重啟中，請重新提交任務。」 | P1（CrashLoopBackOff） |
| 日預算超限 | 403 | 不呼叫任何模型；不扣探針以外費用 | 「今日預算不足，已攔截本次呼叫。請充值或將 x-routing-strategy 改為 cost_first 後重試。」 | P4；高頻攔截 P3 |
| 中國大陸 IP 嘗試打境外旗艦 | 403 | 強制改走 DeepSeek/Qwen/MiMo；若使用者 `manual` 指定 gpt/gemini → 拒絕 | 「依資料合規要求，已限制為境內模型。請改用 DeepSeek 或 Qwen，或在允許出境的區域呼叫。」 | P3 合規審計 |
| 語義快取損壞（JSON 解析失敗） | 200 降級 | 刪除該 Redis Key；改打上游；`X-Hub-Cache=BYPASS` | 無感知 | P3 |
| StocksX JWT 失效 / 401 | 502（任務 `failed`） | 刷新 S2S token 重試 1 次；仍失敗則任務失敗，不改用幻構行情 | 「行情服務鑑權失敗，已中止以免提供過期數據。」 | P1 |
| StocksX 逾時 >8s | 504 任務失敗 | 不啟用跨工具猜測；記錄 tool_traces | 「行情服務逾時，請稍後重試。」 | P2 |
| LiteLLM / 客戶端帶入目錄外模型名 | 400 | 目錄校驗攔截於 Hub Core，**零上游請求** | 「不支援的模型。請改用 gpt-5.6-sol 或 gemini-3.1-pro。」 | P3（表示舊客戶端或錯誤配置） |
| PostgreSQL 不可用 | 503 | 讀路徑：API Key 允許 Redis 快取 60s 的 `user:{id}` 快照；寫路徑 `call_logs` 改寫 Redis Stream `hub:logs:offline`，恢復後 replay | 「帳務服務暫時不可用，請稍後再試。」（若快照命中則仍可推論） | P1 |
| Redis 不可用 | 503 或降級 | 語義快取關閉；日預算改查 PG `SUM`（有 200ms 超時）；熔斷器改進程內內存（副本間不一致可接受 ≤10s） | 多數無感知；預算查詢超時則 503「系統繁忙」 | P1 |
| 競速雙路均 TTFB ≥2s | 走 Failover，最終 200 或 504 | 取消兩條 stream；切 gpt-5.6-sol 鏈 | 成功則無感知 | P3 |
| 內容長度超過 512KiB | 200 + `finish_reason=length` | 截斷並記錄 | 正文截斷，無額外彈窗 | P4 |
| 探針連續失敗 3 輪（90s） | 不影響單次 HTTP | 該模型 `latency_ewma_ms=15000`；Score 自然下降 | 無感知 | P2 |
| opc_service 護欄拒絕寫入 | 400 任務失敗 | 不重試寫入；審計已由 guard 記錄 | 「工業寫入被安全護欄拒絕。」 | P2 |

告警通道：P1 電話 + 即時通訊；P2 即時通訊；P3 工單；P4 僅日誌。標籤必帶 `trace_id`。

---

## 附錄 A — 實施檢查清單（對齊現有倉庫）

- [x] 新增 `docs/` 本文件為單一真實來源；不修改根目錄 `DESIGN.md`
- [x] Kong 路由 `/api/v1` 與 Nginx `/api/chat` 路徑不相交（`frontend/nginx.conf` 已加最長前綴 `/api/v1/`）
- [x] `backend/hub/` 新套件：不在 `nodes.py` / `company_nodes.py` 引入廠商 SDK
- [x] `call_llm(..., max_retries=)` 向後相容，預設仍為 3
- [x] Hub Redis key 前綴與 EvoLoop 任務 key 分離（一期進程內 `semantic:` / `budget:daily:` / `provider:metrics`）
- [x] PysdnOPC 只打 `opc_service`，寫路徑必經 `guard.py`（Hub 工具層拒絕直寫，回 `OPC_GUARD_REQUIRED`）
- [x] 模型目錄、Failover 鏈、OpenAPI `enum`、Router 白名單四者字串集合完全相等（9 個 ID）
- [x] 九模型目錄、OpenAPI `ModelId`、`INTEL`、`budget.py` 價目表均 **不含** Claude / Anthropic ID；`test_hub_catalog_excludes_claude` 必須綠
- [x] `budget.py` 價目表已含 Hub 九模型單價；未知模型仍走保守估計，不得靜默映射到目錄外廠商
- [x] 公開面 `POST /api/v1/chat/completions`、`POST /api/v1/agent/tasks`、`GET /api/v1/agent/tasks/{task_id}` 已落地；契約測試 HUB-R1–R9
- [x] `GET /api/v1/catalog` 回傳九模型目錄；探針 `probe_once` 寫入 `provider:metrics` EWMA
- [x] Failover 跳過熔斷 Open 模型；`speed_first` 同步競速 Gemini × Mercury
- [x] Agent 雙步：規劃呼叫 → StocksX JWT RPC → GPT-5.6 Sol 合成（429 則 Qwen3.5-Max）
- [x] 前端 `HubView` 操作台；Vite `/api/v1` 代理不剝前綴（與 Nginx 最長前綴對齊）
- [x] 五倉工具 JSON 契約落地：StocksX 行情/基本面、LittleCrawler 白名單爬取、StoryForge 大綱、PysdnOPC 只讀經 `opc_service`；寫入 400 `OPC_GUARD_REQUIRED`
- [x] Agent `tool_arguments` 依工具推導，不再把所有工具硬編碼為 `symbol=600519.SH`

## 附錄 B — 驗收用例（契約測試）

| ID | 輸入 | 期望 |
| :--- | :--- | :--- |
| HUB-R1 | Header `X-Client-Region: CN` + `manual` + `model=gpt-5.6-sol` | 403 `DATA_EGRESS_FORBIDDEN` |
| HUB-R2 | `quality_first`、非 CN、探針顯示 Sol 健康 | `chosen_provider=openai`，`model=gpt-5.6-sol` |
| HUB-R3 | Sol 連續 429 | 最終 `gemini-3.1-pro` 或 `deepseek-v4-flash`，`failover_hops>=1` |
| HUB-R4 | `speed_first` + `enable_race=true` | 並發 Gemini 與 Mercury；敗者連線關閉 |
| HUB-R5 | `spent_today + estimate > daily_limit` | 403，零上游請求（用 mock 斷言） |
| HUB-R6 | 敏感詞 | 400，審計有、正文無 |
| HUB-R7 | `POST /api/v1/agent/tasks` 茅台 | 出現 StocksX RPC；二次模型為 Sol 或 Qwen3.5-Max |
| HUB-R8 | Body `model=not-in-catalog-xyz` 或任何非 §1.6 ID | 400 `UNSUPPORTED_MODEL`，零上游請求（mock 斷言無 HTTPS） |
| HUB-R9 | Body `model=claude-opus-5` / `claude-fable-5` / `anthropic/...` | 400 `UNSUPPORTED_MODEL`，零上游請求；回應不得建議切換至 Claude |
| HUB-R10 | Agent `tools=[LittleCrawler_fetch, PysdnOPC_read]` | 200 任務成功；crawler 白名單 JSON；OPC `via=opc_service` 且 `guard_bypassed=false` |
| HUB-R11 | Agent `tools=[PysdnOPC_write]` | 400 `OPC_GUARD_REQUIRED`，零上游請求 |

---

**文件結束。** 本說明書為 Contract-First 產物；任何實作偏離必須先改本文檔再改代碼。
