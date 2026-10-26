# 服務契約（階段 0）

> 對齊日期：2026-10-26。這是內網拆分的凍結契約，還沒有把單體拆開。
> 執行路徑仍由 `backend/core/execution_path.py` 的 `resolve_execution_path` 決定。

## 鎖定的預設

- 僅內網：內網 Ingress，服務間 mTLS，NetworkPolicy。
- NATS JetStream 傳事件；Redis 只做快取與會話；Postgres 存任務、席位、審批與審計索引；Chroma 獨立 StatefulSet。
- 延遲：路由預覽 P95 < 300ms；SSE 首 token < 1s；公司任務受理 < 500ms、計畫生成 < 5s；OPC 讀 < 500ms；OPC 寫受理 < 2s，執行可異步並經人工確認。
- 同步呼叫鏈最多 3 跳。`context-service` 對記憶與 OPC 讀數是平行扇出，帶逾時與快取，不計成第四跳。
- 預設 12 個服務，加 `frontend` 共 13 個映像。團隊小於 5 人時，`context-service` 併入 `route-service`，`reflection-service` 併入 `company-orchestrator`。
- OPC 寫入必須人工審批，審批在 `guardrail-service`。
- Minecraft 多會話先走單一 `minecraft-gateway`，再按會話數擴展。
- 租戶識別放在 `api-gateway`。
- 公司任務與席位可異步；simple 路徑的反思同步返回。
- 第一刀再抽 `tool-gateway` 與 `guardrail-service`。本檔只凍結契約。

## 模組

| 服務 | 職責 |
|------|------|
| `api-gateway` | 對話、任務、路由預覽、監控聚合；鑑權、租戶、限流、請求 ID、SSE。不含業務規則 |
| `route-service` | auto / manual / cost_speed，意圖標籤，規則鏈，路由決定 |
| `context-service` | 組上下文；平行讀記憶與 OPC 摘要，逾時降級 |
| `reflection-service` | 評分、批評、改進、終止。simple 同步，公司路徑可異步 |
| `company-orchestrator` | 任務分析、里程碑、席位註冊、狀態機；發出 `seat.task.created` |
| `seat-executor` | 領任務、執行、回傳。只經 `tool-gateway` 叫工具 |
| `tool-gateway` | 工具 schema、校驗、路由、限流、審計。工具呼叫的唯一入口 |
| `guardrail-service` | 寫入護欄、靈境鐵律、OPC 寫與危險 Minecraft 動作的審批 |
| `opc-service` | OPC UA 連線、讀、訂閱。寫入必須帶護欄決策，不對外直接開寫入口 |
| `minecraft-gateway` | MineMCP。危險動作的鐵律結果必須來自 guardrail |
| `memory-service` | 記憶與 Chroma，按租戶／會話隔離 |
| `observability-collector` | OTel、指標、追蹤、審計。異步，不擋住主鏈 |
| `frontend` | 對話、任務、監控、靜態預覽。一個映像 |

## HTTP

主體在 `/api/v1`。舊的 `/chat`、`/chat/stream`、`/tasks`、`/tasks/{id}` 標成相容入口，由閘道轉發。AI Hub 的 `/api/v1/chat/completions` 是另一條契約。

| 方法 | 路徑 | 可見性 |
|------|------|--------|
| POST | `/api/v1/route-preview` | 公開。回 `path`、`reason`、`rule_hit`、`version` |
| POST | `/api/v1/chat/stream` | 公開。SSE |
| POST | `/api/v1/tasks` | 公開。回 `task_id` |
| GET | `/api/v1/tasks/{id}` | 公開 |
| POST | `/api/v1/tools/{tool}/invoke` | 僅內部 |
| POST | `/api/v1/guardrail/check` | 僅內部 |
| POST | `/api/v1/guardrail/approve` | 僅內部 |
| GET | `/api/v1/opc/read` | 僅內部 |
| POST | `/api/v1/opc/write-request` | 僅內部。必須帶護欄決策 |
| POST | `/api/v1/minecraft/action` | 僅內部。`place_block`、`pose_block`、`break_block`、`fill_block`、`execute_command` 必須帶護欄決策 |

草案：`linkin_core/contracts/openapi.json`。

規則鏈（`manual`、`simple`、`company` 在鏈之前結束）：

`industrial` → `linkin_complex` → `mine_multi_step` → `mine_single_step` → `cost_speed` → `company_keyword` → `length` → `fallback_simple`。

現行 `is_complex_task` 仍把關鍵詞與長度一起判斷。契約把兩段拆開，留給階段 2 的 `route-service`。舊路徑名 `opc` 在契約裡收成 `company`。

## 事件

NATS JetStream。每則含 `schema_version`、`trace_id`、`tenant_id`。

- `seat.task.created`
- `seat.task.completed`
- `reflection.requested`
- `guardrail.decision`
- `audit.event`
- `opc.write.requested`

任務推送另有頻道 `tasks/{task_id}/stream`。草案：`linkin_core/contracts/asyncapi.json`。

## 同步鏈

| 名稱 | 鏈 | 跳數 |
|------|----|------|
| 路由預覽 | gateway → route → context | 3 |
| simple 對話 | gateway → route → reflection | 3 |
| 任務受理 | gateway → company-orchestrator | 2 |
| 工具呼叫 | seat-executor → tool-gateway → guardrail | 3 |
| OPC 寫受理 | guardrail → opc-service | 2 |

席位不能直連 OPC 或 Minecraft。

## 骨架

`deploy/k8s/linkin/`。內網 Ingress 類名 `nginx-internal`，主機 `linkin.internal`。Istio STRICT 與 KEDA 檔案要等 CRD 再套用。

階段 1 把工具呼叫收進 `services/tool-gateway` 與 `services/guardrail-service`。預設 `TOOL_DUAL_RUN=shadow`：舊結果回傳，普通工具抽樣 10%，敏感工具 100%。`guardrail.decision` 用 `LINKIN_GUARDRAIL_HMAC_KEY` 簽名；沒有金鑰時敏感動作拒絕。OPC 寫入埠是 `opc_service/write_port.py`（對應 8081），沒有有效簽章就拒絕。切到 `disabled` 後只走新路徑。
