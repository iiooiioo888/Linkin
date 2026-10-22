# 服務器運維智能體（AIOps）

「AI 服務器管理員」是 Linkin 的 **Level 4 Support** 席位（`server_admin`，稟報 `tech_lead`），
把健康檢查、智慧清理、自動修復、性能診斷、增量備份與自然語言問答收進一條受控管線。
設計哲學與 Minecraft MCP 相同：**LLM 只能提議，執行永遠經護欄與人工批准**。

## 架構（三層）

```
backend/tools/server_admin.py    底層橋接：psutil / docker SDK / systemd(argv) + 護欄 + 乾跑 + JSONL 審計
backend/linkin/server_admin.py   域層：批准隊列、LLM 規劃（關鍵詞兜底）、巡檢、日報、公司工具掛載
backend/linkin/api.py            REST：/linkin/server/*（health / ask / approvals / patrol / report / audit）
backend/company/role_catalog.py  席位預設 server_admin（tools_allowed 12 個 server_* 工具）
```

## 具名工具（唯一執行面，絕無自由 shell）

| 工具 | 讀/寫 | 說明 |
|------|:---:|------|
| `get_disk_usage` | 讀 | 磁盤使用率（存儲根或子目錄） |
| `get_system_load` | 讀 | CPU／內存／load average（psutil 缺失時降級） |
| `get_memory_usage` | 讀 | 內存使用 |
| `get_docker_status` | 讀 | 容器狀態（daemon 不可達時 `available: false` 降級） |
| `check_service` | 讀 | systemd 服務狀態（僅白名單服務；無 systemctl 時降級） |
| `analyze_disk_growth` | 讀 | 「磁盤為什麼漲得這麼快」：各目錄佔用、近 N 天增長來源、最大新文件 |
| `tail_log` | 讀 | `logs/` 內日誌或審計日誌尾部（僅文件名，無路徑） |
| `clean_old_packages` | 寫 | 清理 `packages/` 超過 N 天的 `.zip`（單次 ≤ 5000 文件） |
| `clean_temp_files` | 寫 | 清理 `temp/` 超過 N 天的文件 |
| `rotate_logs` | 寫 | gzip 輪轉 `logs/` 超過 N MB 的 `.log`（原文件清空保留 inode） |
| `restart_service` | 寫 | `systemctl restart`（argv 列表、無 shell、60s 超時、僅白名單服務） |
| `backup_incremental` | 寫 | 增量備份 `assets`／`schematics` 等（size+mtime 未變則跳過，單次 ≤ 2GiB） |

公司 `tool_registry` 中對應 `server_*` 12 個工具：讀工具對所有角色開放；
寫工具 `allowed_roles = [manager, devops, sre, server_admin]`（`custom_server_admin` 前綴自動剝除匹配）。

## 安全護欄（多層防禦）

1. **具名工具白名單**——`execute_named_tool` 是唯一入口；不存在任何「執行任意命令」的工具
2. **危險輸入兜底**——所有參數遞歸掃描 `rm -rf /`、`mkfs`、`dd if=`、fork bomb、`shutdown`、`format c:` 等模式 → `dangerous_input`
3. **路徑牢籠**——一切文件操作 `_resolve_under_root` 鎖定在 `EVOL_SA_STORAGE_ROOT` 內 → 越界 `path_denied`
4. **服務白名單**——`EVOL_SA_SERVICES` + 名稱正則 → `service_denied` / `invalid_service`
5. **confirm 矩陣**——寫操作三態：未確認 → `pending_confirmation`（僅無副作用預覽）；確認 + 乾跑 → `simulated`（`would_*` 預告）；確認 + `EVOL_SA_ENABLED=true` → `executed`
6. **人工批准隊列**——寫操作經域層一律先建 `pending_approval`（JSON 持久化、TTL 30 分鐘過期作廢）；`auto_approve` 需 API 參數 **且** `EVOL_SA_AUTO_APPROVE=true` 雙重開關
7. **JSONL 審計**——每次工具調用落盤（ts／tool／status／dry_run／釋放字節數），`GET /linkin/server/audit` 可查
8. **subprocess 紀律**——僅 `systemctl`，argv 列表傳參（無 `shell=True`）、60 秒超時、乾跑與無 systemctl 環境絕不觸發

## 自然語言問答（`POST /linkin/server/ask`）

```
question ──▶ LLM 規劃（call_llm：工具目錄 + 輸出 JSON {"tool","params","analysis"}）
        │      參數消毒：只保留文檔鍵、int 收斂、幻覺鍵丟棄
        └─ 無金鑰／失敗／輸出無效 ──▶ 關鍵詞路由兜底（磁盤→analyze_disk_growth、重啟→restart_service、…）
讀工具 ──▶ 立即執行，即問即答（"磁盤為什麼漲得這麼快？" → 增長分析 + 最大新文件）
寫工具 ──▶ pending_approval（附預覽："將刪除 3 個 ZIP 包，釋放 1.2GB，請確認"）──▶ 管理員 confirm ──▶ 執行
```

LLM 經 `backend.core.llm.call_llm`（AGENTS.md #1，無供應商 SDK）；規劃模型 `EVOL_SA_MODEL`
（預設走 stage_router 的 generate 層級；席位 `preferred_model` 為 `qwen-max`）。

## 巡檢與日報

- `POST /linkin/server/patrol`：健康快照 + 規則提案——磁盤 ≥ `EVOL_SA_DISK_WARN`(80%) → 提案清理 ZIP/temp；
  服務 `failed/inactive` → 提案重啟；日誌 > 100MB → 提案輪轉。提案預設**全部轉批准隊列**，不自動執行。
- `GET /linkin/server/report`：Markdown 日報（整體狀態、各檢查項、24h 工具調用統計、釋放空間、待批准清單）。
- 定時巡檢用主機 crontab（不引入 Celery 依賴）：

```cron
# 每小時巡檢一次、每天 09:00 產日報（提案進批准隊列，等人確認）
0 * * * * curl -sS -X POST http://127.0.0.1:8000/linkin/server/patrol -H 'Content-Type: application/json' -d '{}'
0 9 * * * curl -sS http://127.0.0.1:8000/linkin/server/report >> /var/log/linkin-daily-report.log
```

## 環境變數

見 [.env.example](../../.env.example)「服務器運維智能體」區塊：`EVOL_SA_ENABLED`、`EVOL_SA_STORAGE_ROOT`、
`EVOL_SA_BACKUP_DIR`、`EVOL_SA_AUDIT_PATH`、`EVOL_SA_PENDING_PATH`、`EVOL_SA_PENDING_TTL_MIN`、
`EVOL_SA_AUTO_APPROVE`、`EVOL_SA_SERVICES`、`EVOL_SA_NO_LLM`、`EVOL_SA_MODEL`、`EVOL_SA_DISK_WARN`。

## 部署形態

- **生產（阿里雲 Ubuntu 22.04）**：Linkin 後端與被管服務同機部署，`EVOL_SA_ENABLED=true` +
  `EVOL_SA_STORAGE_ROOT=/data/mmorpg`，智能體管理的是**本機**（systemctl/docker/磁盤都是本地調用）。
- **開發／Windows／CI**：預設乾跑——psutil 讀本機真實指標；systemctl/docker 不可用時各工具优雅降級
  （`available: false` + 原因），寫操作全部只模擬。測試 43 條全 monkeypatch 隔離，無需金鑰與真實服務。

## REST API

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/linkin/server/health` | 健康快照 |
| POST | `/linkin/server/ask` | 自然語言問答 |
| GET | `/linkin/server/approvals?include_done=` | 批准隊列 |
| POST | `/linkin/server/approvals/{id}/confirm` | 批准執行（過期/重複 → 409，不存在 → 404） |
| POST | `/linkin/server/approvals/{id}/cancel` | 取消 |
| POST | `/linkin/server/patrol` | 主動巡檢 |
| GET | `/linkin/server/report` | 每日報告 |
| GET | `/linkin/server/audit?limit=` | 審計日誌 |

錯誤碼 → HTTP：`unknown_tool/invalid/invalid_service` → 400；`path_denied/service_denied/dangerous_input` → 403；
`expired/invalid_state/needs_confirmation` → 409。
