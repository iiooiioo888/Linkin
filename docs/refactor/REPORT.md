# 重構報告：Linkin 專案結構（2026-11-11）

> 分支：`refactor/project-structure`（自 `master` 切出，未動 `master`）
> 原則：**行為不變**。所有端點／公開 export 與重構前逐一比對，以測試與 OpenAPI 作為驗收。

## 1. 為什麼重構

重構前三個檔案同時承担「入口／領域邏輯／型別契約」三種職責，任何人改一個端點都要在數千行檔案裡捲動：

| 檔案 | 行數 | 問題 |
|------|-----:|------|
| `backend/main.py` | 3,176 | app 組裝、middleware、121 個 HTTP 端點、2 個 WebSocket、40+ 請求模型全混在一起 |
| `frontend/src/api/client.ts` | 2,575 | 212 個 export（聊天、任務、監控、Docker、計費、Lab、MCP…） |
| `frontend/src/types.ts` | 1,951 | 118 個型別／常數，全部領域共用一個檔案 |

## 2. 做了什麼

### 2.1 後端：抽出 API 路由層 `backend/api/`

```
backend/
├── main.py                     # 315 行：app 組裝（lifespan／middleware／例外處理／include_router）
├── api/
│   ├── __init__.py
│   ├── security.py             # _TRUSTED_PROXY_NETS、_is_local_peer、_client_identity、_set_gate_cookie
│   └── routers/
│       ├── health_auth.py      # /health、/auth/*
│       ├── raho_auditor.py     # /raho/*、/auditor/*
│       ├── config.py           # /config/*、/monitor/llm-ops|optimization|hub-snapshot、/feedback*
│       ├── chat.py             # /chat、/chat/stream、/routing/preview（含 SSE 串流 helper）
│       ├── tasks.py            # /tasks*、/traces、/checkpoints、/context、2 個 WebSocket
│       ├── memories.py         # /memories*
│       ├── monitor.py          # /dashboard、/monitor/opc|hub|agents*|raho/*
│       ├── docker_cloud.py     # /docker/*、/system/resources、/cloud/*
│       ├── lab.py              # /lab/*（Firecrawl／Prompt／Ponytail／Archify／Quant）
│       ├── skills_mcp.py       # /skills*、/mcp*
│       └── db_admin.py         # /admin/db/*
```

- 端點 handler 與請求模型**原樣搬移**，只改 decorator（`@app.*` → `@router.*`）與 import；
  每個模組自帶 `APIRouter`，main.py 以 `app.include_router(...)` 裝配（共 11 個 router）。
- 迴圈依賴同時解掉：全域公司預算狀態搬到 `backend/services/company_budget.py`，
  `company/orchestrator.py` 不再反向 `from backend.main import ...`。
- `main.py` 仍保留 `_client_identity`／`nodes` 的向後相容 re-export，既有測試與外部程式不受影響。

### 2.2 前端：API client 與型別按領域拆包（對外 import 路徑不變）

- `frontend/src/api/client.ts` → `frontend/src/api/client/` 套件（16 檔）：
  `http.ts`（base URL／fetch 核心／共用錯誤）＋ `chat / config / raho / tasks / monitor / docker / billing / media / cloud / hub / db / lab / skills / mcp`。
  `index.ts` 以 `export *` 轉出，**公開 API 與拆前 212 個 export 完全一致**（4 個新增 helper 留在 `http.ts` 不對外）。
- `frontend/src/types.ts` → `frontend/src/types/` 套件（9 檔）：`billing / task / raho / chat / dashboard / docker / cloud / monitor + index.ts`，
  118 個 export 全數保留（含值匯出 `COMPANY_TEMPLATES`、`OPC_PHASES`、`usesIndustrialStages`）。
- 兩個套件都靠 `moduleResolution=bundler` 的目錄 index 解析，**消費端 import 一行都不用改**。

### 2.3 附帶修復（阻擋驗證的既有問題）

| 問題 | 修法 |
|------|------|
| 全量 pytest 在 `test_company.py` 卡死 | RAHO 升級到 L5 時會真的阻塞 `EVOL_RAHO_DECISION_TTL`（預設 60 秒）等用戶點選，且 `_ask_layer` 走函式內 import 的 `call_llm` 攔不到 patch。`backend/tests/conftest.py` 新增 autouse `_isolate_raho_superior_llm`：TTL=0、L3/L4 裁決改離線 stub |
| `npm run build` 在 Windows 失敗 | prebuild 只找系統 `python`（缺 litellm）。改為優先找 `../.venv/Scripts/python.exe`／`../.venv/bin/python`（或 `PYTHON` 環境變數） |
| Ruff 3 條既有違規 | `cli_runtimes.py` UP035（collections.abc）、`manager_briefing.py` PYI041／FLY002 |
| 測試殘留 `backend/data/role_catalog/` | 加入 `.gitignore`（租戶角色目錄快取） |
| 測試 patch 目標 | `backend.main.call_llm_stream` → `backend.api.routers.chat.call_llm_stream`；`backend.main.task_manager` → `backend.api.routers.tasks.task_manager`（`backend.main.nodes.*` 因 re-export 不用改） |

## 3. 行為不變的證據

| 驗證 | 結果 |
|------|------|
| OpenAPI（重構前 vs 重構後，同一份 main.py 前後載入比較） | **323 個 operation 完全相同**：path／method／operationId／requestBody／responses／components 全部一致，0 missing、0 extra |
| 後端路由數 | 各 router：health_auth 4、raho_auditor 14、config 18、chat 3、tasks 13、memories 3、monitor 11、docker_cloud 19、db_admin 4、lab 16、skills_mcp 16（共 123 條，含 2 WebSocket） |
| 後端 AST 比對（隊友獨立執行） | 搬移的 handler body／模型／docstring 逐一定義比對；唯一差異是 inline import 提頂與 `_company_budget_state` → `get_company_budget_state()` |
| 前端 export 比對 | client：212/212 名稱一致；types：118/118 宣告文字一致、0 duplicate／0 missing |
| 前後端測試 | 見 §4 |

## 4. 驗收結果（重構後最終樹）

| 檢查 | 指令 | 結果 |
|------|------|------|
| 後端測試 | `pytest backend/tests/` | **1291 passed / 3 failed / 1 skipped**（2 分 25 秒；3 個失敗皆為重構前既有，見 §6） |
| Lint | `ruff check backend/ opc_service/` | All checks passed |
| 型別 | `mypy backend/ opc_service/` | Success: no issues found（435 source files） |
| 前端型別 | `npx tsc -p tsconfig.app.json --noEmit --incremental false` | 0 error |
| 前端單元測試 | `npx vitest run` | 11 files / 39 tests passed |
| 前端建置 | `npm run build`（tsc -b ＋ vite build ＋ verify-ux-bundle） | BUILD_EXIT=0 |

執行環境：Windows 11／Python 3.13（專案 venv）／Node 24。
另有 OpenAPI 對照（§3）與 24 條端點 smoke（重構後皆回預期狀態碼，無 404／500）。

## 5. 檔案規模變化

| 項目 | 重構前 | 重構後 |
|------|-------:|-------:|
| `backend/main.py` | 3,176 行 | **315 行** |
| 後端最短／最長 router | — | 42 行（db_admin）／753 行（chat） |
| `frontend/src/api/client.ts` | 2,575 行 | 16 檔／2,707 行（含檔頭與 import） |
| `frontend/src/types.ts` | 1,951 行 | 10 檔／2,087 行 |

## 6. 已知限制與後續建議

1. **分支落後 `origin/master` 40 個 commit**（本地另有 4 個 commit 未推）。本次重構基於本地 `master`，
   合併上游時 `backend/api/` 與前端 client/types 套件會是主要衝突面；建議先把上游合併回本地後再重放本次 commit，
   或先用 `git rebase --onto` 把 4 個本地 commit 疊到上游。
2. **3 個測試失敗在重構前即存在**（已用 `git worktree` 在未改動的 `master` 上逐一重現，非本次引入，未在本次修）：
   - `test_company.py::TestRoles::test_standard_roles_have_all_types`：本地 `STANDARD_ROLES` 缺 `RoleType.REQUIREMENT_AUDITOR`（本地落後上游 40 個 commit 的角色表差異）。
   - `test_contracts.py::test_contract_c_seat_003_l0_has_no_tools_or_plugins`：本地席位表缺 `ENVIRONMENT_KERNEL`（L0）席位。
   - `test_lab_tools.py::test_lab_api_endpoints`：`/lab/archify/system-flows/raho` 標題是「任務經理」，測試期待含「RAHO」（本地 system-flows 資料與測試不同步）。
3. Windows 開發機需自行安裝 `tzdata`（`pip install tzdata`）才會有 IANA 時區資料；
   否則 `routing_feedback` 相關 16 個測試會因 `ZoneInfoNotFoundError: Asia/Taipei` 失敗（CI Linux 不受影響）。
   建議後續在 `requirements.txt` 加 `tzdata; sys_platform == "win32"`
3. `frontend/src/App.tsx`（1,132 行）、`components/RoleSettingsPanel.tsx`（1,226 行）仍是大型元件，
   下一輪可依「路由殼／面板 hook／子元件」再拆。
4. `chat.py`（753 行）仍偏大，若未來要再細分，建議把 SSE helper 獨立成 `api/streaming.py`。
5. logger 名稱由 `backend.main` 改為 `backend.api.routers.*`（訊息內容不變；若有 caplog 以 logger 名稱斷言的測試需注意）。

## 7. 如何審閱

1. `git diff --stat master` 先看刪除的 `main.py`／`client.ts`／`types.ts` 與新增的套件。
2. 每個 router 與 main.py 原區段一一對照（decorator 外無邏輯差異）。
3. 前端看 `api/client/index.ts` 與 `types/index.ts` 的 `export *` 清單即可知道公開 API 邊界。
4. 重跑 §4 的六條命令。
