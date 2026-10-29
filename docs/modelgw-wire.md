# ModelGW 掛載（WIRE）

將純庫 `backend/modelgw`（#128）掛入 FastAPI 與 `call_llm` 熱路徑。  
**預設關閉**，不影響既有 Hub／產品行為。

## 環境變數

| 變數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `MODELGW_WIRE_MODE` | `off` | `off`：不介入 `call_llm`。`shadow`：準入並打 log，不阻擋。`enforce`：硬閘（未 READY／O18 拒則拋 `ModelGWError`）。 |
| `MODELGW_REGISTRY_SEED` | `backend/modelgw/seeds/demo_registry.json` | Registry JSON seed（冷啟動／fixture；見 [modelgw-registry.md](./modelgw-registry.md)）。 |
| `MODELGW_RETRY_AFTER` | `30` | `PROVISIONING` → HTTP 503 時的 `Retry-After` 秒數。 |

別名：`enforce` 亦可寫 `on`／`true`／`1`；`shadow` 亦可寫 `observe`／`log`。

## HTTP

前綴 `/modelgw`（**不**改 `/api/v1` Hub）：

- `GET /modelgw/healthz`
- `GET /modelgw/registry`
- `POST /modelgw/v1/admit` — body `{ "model_id": "..." }`
- `POST /modelgw/v1/chat/completions` — OpenAI 風格薄包裝
- `POST /modelgw/internal/v1/deploy-callback` — 部署完成回調（HMAC＋冪等；見 registry 文檔）

錯誤映射（Core §8.1）：

- `PROVISIONING` → **503** + `code=PROVISIONING`（可選 Retry-After）
- `UNSUPPORTED_MODEL`／`ADMISSION_REJECTED`／`MODEL_NOT_READY` → **400**

## 邊界

- 不讀 `HUB_CATALOG`、不 `import hub.circuit`
- 不改 Hub 公開 API 行為
- 純庫 `admit`／`service` 契約不變
- 反思 DAG／UI／部署／合併不在本 PR
