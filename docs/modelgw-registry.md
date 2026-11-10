# ModelGW Registry 持久化（P1／#130）

將 Registry 從進程內 InMemory 升級為 **SQL 狀態權威**（本波 SQLite 過渡；權威目標 Postgres），並提供部署完成回調寫入 READY／FAILED。

**本項不改 `MODELGW_WIRE_MODE`／不切 enforce。**

## 環境變數

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `MODELGW_REGISTRY_BACKEND` | `memory` | `memory`｜`sql`／`sqlite`。未設但有 `MODELGW_DATABASE_URL` 時自動用 sql。 |
| `MODELGW_DATABASE_URL` | （空） | 例：`sqlite:////opt/linkin/data/modelgw.sqlite3`。Postgres URL 本波尚未掛驅動。 |
| `MODELGW_REGISTRY_SEED` | `seeds/demo_registry.json` | **冷啟動／fixture**：僅當 `(tenant_id, model_id)` 不存在時灌入；不覆蓋回調列。 |
| `MODELGW_CALLBACK_HMAC_KEY` | （空） | 回調 HMAC 服務金鑰（**獨立**；勿輪換 `LINKIN_GUARDRAIL_HMAC_KEY`／用戶側 HMAC）。 |

既有 `MODELGW_WIRE_MODE`／`MODELGW_RETRY_AFTER` 語意不變，見 [modelgw-wire.md](./modelgw-wire.md)。

## Schema

獨立表（勿併 Hub catalog）：

- `modelgw_models` — PK `(tenant_id, model_id)`；`tenant_id` 預設 `""`；七態 CHECK
- `modelgw_deploy_callbacks` — 冪等日誌；UNIQUE `(tenant_id, idempotency_key)`

DDL：`backend/modelgw/migrations/001_modelgw_schema.sql`（啟動 `ensure_schema`）。

## 回調

`POST /modelgw/internal/v1/deploy-callback`

Headers：

- `X-ModelGW-Signature: sha256=<hex>`（**必填**）
- `Idempotency-Key`（**必填**）
- 可選 `X-ModelGW-Timestamp`／`X-ModelGW-Nonce`

簽名訊息：有 timestamp 時為 `{ts}\n{nonce}\n` + raw body；否則純 body。  
同鍵同 hash → 重放首次 snapshot；同鍵異 hash → **409**。

## 硬門

- 不切 WIRE／enforce；不碰 `TOOL_DUAL_RUN`；不輪換用戶側 HMAC
- admit／chat／`call_llm` precheck **只讀** Registry
- 不 `import hub.circuit`／不讀 `HUB_CATALOG`
