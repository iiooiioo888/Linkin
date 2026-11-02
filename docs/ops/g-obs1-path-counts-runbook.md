# G-OBS1｜path_counts 運維 Runbook（L2 碼面）

**契約／票：** G-OBS1 L2 · 談票 `g-obs1-l2-talk-ticket-20261102`  
**性質：** 正式 ops runbook（與行為碼同 PR）  
**WIRE：** 本文件 **不**授權改 `MODELGW_WIRE_MODE`（產線維持 **enforce**；`wire_change=none`）  
**旗標：** `ready_to_merge=false` · `l1_continue=true` · `l1_closed=false` · `path_counts_ne_closed=true` · `l0_ne_l1_ne_l2=true`

> **硬口徑：** 進程內 `path_counts`（含 0/0/0／重啟歸零）**≠** L1 已關 **≠** L2 已關 **≠** G-OBS1 已關。  
> L0 ≠ L1 ≠ L2。本 runbook **不得**被當成合並／部署／改閘／關 L1／回滾授權。

---

## 1. 指標語義

| 鍵 | 意義 |
| :--- | :--- |
| `via` | 經 ModelGW `precheck_model`（WIRE≠off） |
| `bypass` | WIRE=`off`，未走準入 |
| `would_block` | 若為 enforce 會阻擋的準入失敗／未映射（shadow 亦累計） |
| `scope` | 讀點回傳固定 `since_process_start`（自本 PID 啟動起） |
| `wire_mode` | 當前 `MODELGW_WIRE_MODE` 正規化值 |

**enforce 形狀（產線）：** 多數流量應為 `via`；`bypass` 持續非 0＝異常（WIRE 漂或誤設）。  
`would_block` **無**絕對紅線（路徑 B sunset／未映射殘量可預期）；勿單鍵否定產關。  
**≠** 把「有數字／沒數字／歸零」說成統一健康證明。

結構化 log 標記：`MODELGW g_obs1_path_event=1 path=<via|bypass|would_block> ...`（可 grep；重啟後仍可重建**趨勢**）。

---

## 2. 如何讀

### 2.1 受控內部讀點（C2）

```http
GET /api/internal/modelgw/path-counts
```

- **預設：** 僅 **loopback**（`127.0.0.1`／`::1`）可讀。  
- **可選：** `MODELGW_PATH_COUNTS_ALLOW_PRIVATE=1` 放行 RFC1918；或設 `MODELGW_PATH_COUNTS_TOKEN`＋請求頭 `X-ModelGW-Internal-Token`。  
- **公網無 token：必須 403**（禁裸洩）。  
- **不**信任 `X-Forwarded-For` 做放行（防偽造）。  
- 回應含：`via`／`bypass`／`would_block`／`pid`／`started_at`／`wire_mode`／`scope`／`multi_worker_incomplete`／`workers_hint`。  
- **禁止**在讀點內呼叫 `reset_path_counts`。  
- hub `GET /metrics` **≠** 本讀點；勿混用。

本機例：

```bash
curl -sS http://127.0.0.1:8000/api/internal/modelgw/path-counts
```

### 2.2 Log 聚合（C1；重啟不丟趨勢）

進程計數重啟歸零屬預期。24h／7d **趨勢**從 journal／檔案 log 重建：

```bash
# 例：systemd journal（依實際 unit 名調整）
journalctl -u linkin-api --since "24 hours ago" \
  | grep 'g_obs1_path_event=1' \
  | tee /tmp/g-obs1-24h.log

# 倉庫腳本（stdin 或檔案）
python backend/scripts/aggregate_g_obs1_path_counts.py /tmp/g-obs1-24h.log
```

日報須區分：**進程快照** vs **聚合窗**；禁把「部署後 0/0/0」當健康／已關證明。

### 2.3 重啟效應

- 部署／crash／手動重啟 → 記憶體計數歸零；`started_at`／`pid` 更新。  
- L1 日報標「自上次重啟起」；歸零＝**事件窗**，寫進 daily，**不**寫 `l1_closed=true`。

---

## 3. 誰讀／節奏

| 角色 | 節奏 |
| :--- | :--- |
| Ops | 日看讀點或聚合；異常記 L1 daily／alerts |
| Analyst | 異常形狀／趨勢判讀；code-gap／recheck |
| PM | 匯報用戶；不自行改閘／關窗 |
| 用戶 | 唯一可授合並／部署／改 WIRE／關 L1／回滾 |

異常升級：Ops → Analyst → PM → 用戶。

---

## 4. 告警門檻（紙面沿用 L0；建議非自動殺閘）

| 條件 | 建議 |
| :--- | :--- |
| `bypass` 在 enforce 產線持續非 0 | 告警；查 WIRE／掛載 |
| `wire_mode` 非預期（漂離 enforce） | 告警；**不**本文件授權切回 |
| 對外健康非 200（`/`／`/api/health`／`/health`） | 既有健康告警 |
| `would_block` | **無**絕對紅線；趨勢異常再討論 |
| 讀點公網可裸讀 | **P0**：立即堵（nginx／防火牆／撤暴露） |

---

## 5. 與 rollback 關係

- 觀測／碼面異常 → 可**觸發討論**是否走 P2／既有回滾敘事。  
- **執行**回滾：僅用戶原話＋P2／#131 路徑。  
- 本 runbook／L2 碼關 **≠** 必須回滾；**≠** 禁止回滾。  
- `does_not_authorize_rollback=true`。

---

## 6. 與 L1 關係（不得自動關 L1）

- L1 觀測窗繼續至約定日（可滾）；`l1_closed=false`。  
- L2 碼落地／部署日＝L1 **事件窗**（可能重啟歸零）→ 寫 daily，**不得**自動 `l1_closed=true`。  
- 關 L1：僅用戶**另句**。  
- 產線 **禁止** `reset_path_counts` 假關窗。

---

## 7. 單 worker 明示（C3）

**寫死：**

- 產線若維持 **`--workers 1`**（或等價單進程），本讀點 `path_counts`＝**全站**計數。  
- 若改為 **N>1** 且尚無跨 worker 匯總策略：必須視讀點為**不完整**，且回應／日報標 `multi_worker_incomplete=true`；**不可**宣稱已正確匯總或 L2 碼關。  
- 匯總策略（共享 store／log 加總／metrics 多進程）屬未來另票；本波不 silently 假匯總。

`workers_hint` 僅來自 env 提示（`MODELGW_WORKERS_HINT`／`WEB_CONCURRENCY`／`UVICORN_WORKERS`），**非**權威發現；以實際啟動參數為準。

---

## 8. 不做／禁

合並／部署／改 WIRE／HMAC／sql／TOOL_DUAL／nginx／.env／關 L1／路徑 A／Fusion／LangGraph 宿主替換／無防護公網 metrics／讀點內 reset。

---

*runbook_for=G-OBS1-L2 · path_counts · written with code PR*
