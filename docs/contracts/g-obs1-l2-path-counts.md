# CONTRACT：G-OBS1 L2 — path_counts 碼面閉環（結構化 log／內部讀點／runbook）

> **狀態：** 開碼 PR（**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `G-OBS1-L2`  
> **談票錨：** `/workspace/linkin-audit/g-obs1-l2-talk-ticket-20261102.md`  
> **基線 HEAD：** `5a9b349`（G-GATE1 #154）  
> **WIRE：** 維持 **enforce**；`wire_change=none`

## 一句精神

落地談票 §3 四條件：**結構化 log 聚合**＋**受控內部讀點**＋**單 worker 明示**＋**正式 runbook**。  
開碼 ≠ 合並 ≠ 部署 ≠ 關 L1 ≠ G-OBS1 全關。`path_counts` ≠ 已關。

## 四條件落地

| # | 條件 | 落地 |
| :--- | :--- | :--- |
| C1 | 持久化或等價 log 聚合 | `runtime._bump` → `g_obs1_path_event=1`；`backend/scripts/aggregate_g_obs1_path_counts.py` |
| C2 | 可匯出／內部讀點 | `GET /api/internal/modelgw/path-counts`（AuthGate `_OPEN_EXACT` 放行＋L2 loopback／**反代必 token** 閘；禁 reset；≠ hub `/metrics`） |
| C3 | 多 worker 或單 worker 明示 | runbook §7；快照 `multi_worker_incomplete` |
| C4 | 正式 runbook | `docs/ops/g-obs1-path-counts-runbook.md` |

## 碼錨

| 檔 | 符號／路由 |
| :--- | :--- |
| `backend/modelgw/runtime.py` | `_path_counts`／`path_counts`／`path_counts_snapshot`／`_bump`／`reset_path_counts`（測試 only） |
| `backend/modelgw/api.py` | `internal_path_counts`／`_is_path_counts_client_allowed`／`_proxy_forward_signal` |
| `backend/middleware/auth_gate.py` | `_OPEN_EXACT` 含 path-counts（會話閘放行；L2 閘仍生效） |
| `frontend/nginx.conf` | `location = /api/internal/modelgw/path-counts` 保完整 path（於 `/api/` 前；不改全域剝前綴） |
| `docs/ops/snippets/nginx-path-counts-preserve.example.conf` | 產線 conf 參考（`127.0.0.1:8000`；**deploy 另授才改 live**） |
| `docs/ops/g-obs1-path-counts-runbook.md` | 指標／讀法／告警／rollback／L1／單 worker／反代必 token |

## 旗標

`ready_to_merge=false` · `wire_change=none` · `steal=false` · `l1_continue=true` · `l1_closed=false` · `path_counts_ne_closed=true` · `l0_ne_l1_ne_l2=true` · `path_a_this_round=false` · `does_not_modify_nginx_live=true` · `option=B` · `does_not_authorize_merge/deploy/wire/rollback=true`

## 反代／nginx（方案 B 補強）

- 通用 `location /api/` 剝 `/api` → AuthGate 全路徑不命中 → 外網 401（已知根因）。
- **精確** `location = /api/internal/modelgw/path-counts` 保路徑；**勿**只開 `_OPEN_EXACT` 剝前綴 path；**勿**改全域 `/api/` 剝前綴。
- L2：若請求帶 `X-Forwarded-For` 或 `X-Real-IP`（任一非空）→ **必須** `X-ModelGW-Internal-Token`（即使 peer loopback）；頭內容**不**當真實客戶端 IP 放行。
- 倉庫改 `frontend/nginx.conf`／example snippet **≠** 改產線 live nginx（`does_not_modify_nginx_live=true`；套用另授）。

## 明確不做

合並／部署／改 WIRE／HMAC／map／sql／TOOL_DUAL／改產線 live nginx／關 L1／路徑 A／Fusion／LangGraph／無防護公網 metrics／讀點內 `reset_path_counts`／只開 `_OPEN_EXACT` 剝前綴 path。
