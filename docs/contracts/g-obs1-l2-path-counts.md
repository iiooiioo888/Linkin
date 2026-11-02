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
| C2 | 可匯出／內部讀點 | `GET /api/internal/modelgw/path-counts`（loopback／token；禁 reset；≠ hub `/metrics`） |
| C3 | 多 worker 或單 worker 明示 | runbook §7；快照 `multi_worker_incomplete` |
| C4 | 正式 runbook | `docs/ops/g-obs1-path-counts-runbook.md` |

## 碼錨

| 檔 | 符號／路由 |
| :--- | :--- |
| `backend/modelgw/runtime.py` | `_path_counts`／`path_counts`／`path_counts_snapshot`／`_bump`／`reset_path_counts`（測試 only） |
| `backend/modelgw/api.py` | `internal_path_counts`／`_is_path_counts_client_allowed` |
| `docs/ops/g-obs1-path-counts-runbook.md` | 指標／讀法／告警／rollback／L1／單 worker |

## 旗標

`ready_to_merge=false` · `wire_change=none` · `steal=false` · `l1_continue=true` · `l1_closed=false` · `path_counts_ne_closed=true` · `l0_ne_l1_ne_l2=true` · `path_a_this_round=false` · `does_not_authorize_merge/deploy/wire/rollback=true`

## 明確不做

合並／部署／改 WIRE／HMAC／map／sql／TOOL_DUAL／nginx／關 L1／路徑 A／Fusion／LangGraph／無防護公網 metrics／讀點內 `reset_path_counts`。
