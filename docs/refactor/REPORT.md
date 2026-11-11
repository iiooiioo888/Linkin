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
│       ├── chat/               # /chat、/chat/stream、/routing/preview（第二輪再拆成 7 檔套件，見 §8）
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
| 測試 patch 目標 | `backend.main.call_llm_stream` → `backend.api.routers.chat.streaming.call_llm_stream`（第二輪再移到 `chat.streaming`）；`backend.main.task_manager` → `backend.api.routers.tasks.task_manager`（`backend.main.nodes.*` 因 re-export 不用改） |

## 3. 行為不變的證據

| 驗證 | 結果 |
|------|------|
| OpenAPI（重構前 vs 重構後，同一份 main.py 前後載入比較） | **323 個 operation 完全相同**：path／method／operationId／requestBody／responses／components 全部一致，0 missing、0 extra |
| 後端路由數 | 各 router：health_auth 4、raho_auditor 14、config 18、chat 3、tasks 13、memories 3、monitor 11、docker_cloud 19、db_admin 4、lab 16、skills_mcp 16（共 123 條，含 2 WebSocket） |
| 後端 AST 比對（隊友獨立執行） | 搬移的 handler body／模型／docstring 逐一定義比對；唯一差異是 inline import 提頂與 `_company_budget_state` → `get_company_budget_state()` |
| 前端 export 比對 | client：212/212 名稱一致；types：118/118 宣告文字一致、0 duplicate／0 missing |
| 前後端測試 | 見 §4 |

## 4. 驗收結果（合併上游後最終樹，2026-11-11）

| 檢查 | 指令 | 結果 |
|------|------|------|
| 後端測試 | `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（3 分 15 秒；上游 #176 移除 Minecraft 組件後） |
| Lint | `ruff check backend/ opc_service/` | All checks passed |
| 型別 | `mypy backend/ opc_service/` | Success: no issues found（489 source files） |
| 前端型別 | `npx tsc -p tsconfig.app.json --noEmit --incremental false` | 0 error |
| 前端單元測試 | `npx vitest run` | 16 files / 66 tests passed |
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
| `backend/api/routers/chat.py` | 753 行 | 7 檔套件／812 行（最大 388 行）＝ 第二輪 |
| `frontend/src/App.tsx` | 1,205 行 | **282 行** ＋ `src/hooks/` 5 檔／1,252 行 ＝ 第二輪 |
| `frontend/src/components/RoleSettingsPanel.tsx` | 1,255 行 | **7 行 barrel** ＋ `components/role-settings/` 10 檔／1,374 行 ＝ 第二輪 |
| `backend/main.py`（合併上游後） | — | **373 行**（新增上游 app 級註冊／docs 開關／horizon router） |

## 6. 已知限制與後續建議

1. ✅ **已解決：上游 40 個 commit 已合併**（見 §9）。`master` 已同步上游並全綠（1572 passed），
   `refactor/project-structure` 再合併同步後的 `master`，兩條分支現在都包含上游全部變更；
   本地原有 4 個 commit 亦保留（master 相對 origin/master 僅多這 4 個 commit 的內容）。
2. **3 個測試失敗在重構前即存在**（已用 `git worktree` 在未改動的 `master` 上逐一重現，非本次引入，未在本次修）：
3. Windows 開發機需自行安裝 `tzdata`（`pip install tzdata`）才會有 IANA 時區資料；否則 `routing_feedback` 相關 16 個測試會因 `ZoneInfoNotFoundError: Asia/Taipei` 失敗（CI Linux 不受影響）。建議後續在 `requirements.txt` 加 `tzdata; sys_platform == "win32"`。
4. logger 名稱由 `backend.main` 改為 `backend.api.routers.*`（第二輪後再細分為 `chat.streaming` 等；訊息內容不變；若有 caplog 以 logger 名稱斷言的測試需注意）。
5. 前端 App 層目前沒有元件／行為測試（vitest 只覆蓋 `src/lib`）。第二輪 App 拆分以 tsc ＋「JSX 151/151 行逐字相同」＋「21 個 dependency array 內容一致」作為等價保護；建議後續補 ChatView／App 級測試（可用 Playwright）。
6. 第二輪新增 4 個 oxlint `exhaustive-deps` warning：因規則要求 dependency array 照舊，而 setter 現在是 props；runtime 等價，屬 repo 既有 warning 類別，不影響 build。
7. 第二輪 hooks 之間 effect 的相對執行順序與原單檔略有不同（彼此獨立、同 commit 執行，無可觀察差異），已列為第二輪最大風險面。

## 7. 如何審閱

1. `git log --oneline master..HEAD` 會看到兩個 commit：第一輪（main.py／client／types）、第二輪（App／RoleSettingsPanel／chat）。
2. 每個 router／hook 與原檔區段一一對照（除 import／decorator／參數化外無邏輯差異）。
3. 前端看 `api/client/index.ts`、`types/index.ts`、`components/RoleSettingsPanel.tsx` 的 barrel 即知公開 API 邊界。
4. 重跑 §4 的六條命令。

## 8. 第二輪（2026-11-11 續）

### 8.1 App.tsx → 5 個 hook（1,205 → 282 行）

| 檔案 | 行數 | 職責 |
|------|-----:|------|
| `src/App.tsx` | 282 | 只留組裝＋JSX（151 行 JSX 與重構前逐行相同） |
| `src/hooks/useAppRoute.ts` | 126 | route state／hash 同步／前後退／navigateRoute |
| `src/hooks/useChatSessions.ts` | 192 | sessions 持久化、active session、任務狀態 patch、決策阻塞 |
| `src/hooks/useChatSend.ts` | 320 | sendQuery（SSE＋建立任務）、handleRetry、handleSuggest |
| `src/hooks/useTaskProgressStream.ts` | 268 | 任務進度：applyProgress／pollProgress／TaskWebSocket 綁定 |
| `src/hooks/useWorkspaceNavigation.ts` | 346 | task detail、surface return、view／monitor／lab／focus／trace 切換 |

等價性：JSX 151/151 行相同；原檔第 67-1204 行每個非空行可在新檔逐字找到；useState/useRef 25/25、useEffect 11/11、21 個 dependency array 內容一致。

### 8.2 RoleSettingsPanel.tsx → role-settings 套件（1,255 → 7 行 barrel）

`types.ts`（194）、`fields.tsx`（91）、`sections/`（Identity 146／Model 234／Prompt 47／Runtime 59／Alerts 154）、`RoleSettingsPanel.tsx`（122，主面板）、`CreateRoleModal.tsx`（320）、`index.ts`（7）。
公開 API（default、`CreateRoleModal`、`draftFromAgent`、`draftToPayload`、`RoleSettingsDraft`）不變，唯一消費端 `AgentsMonitorPanel.tsx` 未改一行。

### 8.3 chat.py → chat/ 套件（753 行 → 7 檔／812 行）

`__init__.py`（16，維持原註冊順序）、`_router.py`（5，共用 APIRouter）、`models.py`（36）、`routes.py`（62）、`streaming.py`（388）、`company_stream.py`（239）、`minecraft_stream.py`（66）。
`main.py` 未改；4 個測試 patch 目標改為 `backend.api.routers.chat.streaming.call_llm_stream`；路由順序／paths／components／operationId 與舊版完全一致。

### 8.4 第二輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | 1291 passed／3 failed（同 §6 既有問題）／1 skipped、無 error |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（441 files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run`／`npm run build` | 39 passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（62 warnings；其中 4 個為本次 dependency array 照舊所致） |

## 9. 第三輪：合併上游 40 個 commit（2026-11-11）

### 9.1 兩段合併

| 步驟 | 內容 |
|------|------|
| 1) `master` ← `origin/master` | 40 個 commit、462 個檔案（+56,718/−3,944）。僅 2 個衝突：`backend/main.py`（我方 billing to_thread／身分信任 vs 上游 cookie 會話＋precheck 計費）、`backend/tests/test_auth_gate.py`（上游刪除舊 gate 測試、我方新增 identity 測試）。以「上游版 + 重放本地 4 commit 語意」解衝突，`pytest` 全量 **1572 passed / 1 skipped**，ruff／mypy 全綠 → merge commit `17c38fe` |
| 2) `refactor/project-structure` ← `master` | 5 個衝突檔：`backend/main.py`、`frontend/src/App.tsx`、`frontend/src/components/RoleSettingsPanel.tsx`、`frontend/src/api/client.ts`（modify/delete）、`frontend/src/types.ts`（modify/delete）。一律「保留重構結構、把上游 delta 移植進去」→ merge commit `fcd2c16` |

### 9.2 上游 delta 移植對照

| 上游變更 | 落點（重構後結構） |
|----------|------------------|
| auth cookie 化（login 只發 HttpOnly cookie、query token 失效、logout 清 cookie、docs 預設關閉） | `backend/api/security.py`、`routers/health_auth.py`、`main.py`（`LINKIN_ENABLE_DOCS`） |
| 任務 6 個新端點（budget/decision、budget/lines、confirmation-draft、seat-overrides、field-writes、narrative/commit）＋公司預算確認閘 | `routers/tasks.py`、`routers/chat/company_stream.py` |
| `/skills/cli-hub` | `routers/skills_mcp.py` |
| horizon 4 端點 | 新增 `routers/horizon.py`＋main.py include |
| settings 隔離／租戶記憶庫 | `routers/config.py`、`routers/memories.py` |
| client.ts +140 行（lab prefs／budget／confirmation／seat override／field writes／narrative／CLI hub） | `api/client/{config,tasks,skills}.ts`；公開 API 212 → **223** |
| types.ts TaskProgress 擴充（awaiting_confirmation／rejected／expired＋budget_plan） | `types/task.ts` |
| App.tsx worldModuleId／monitor tab 推導／終止狀態 | `hooks/useAppRoute.ts`、`useWorkspaceNavigation.ts`、`useTaskProgressStream.ts`、`App.tsx`（284 行） |
| RoleSettingsPanel sunset hub 攔截＋CSS 變數 | `components/role-settings/*` |

### 9.3 第三輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1572 passed / 1 skipped / 0 failed**（2 分 39 秒） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（538 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` | 17 files / 72 tests passed |
| `npm run build` | BUILD_EXIT=0 |
| `oxlint src` | 0 errors（67 warnings，既有類別） |

分支現狀：`master` = 上游 + 本地 4 commit；`refactor/project-structure` = 上述 + 三輪重構（4 個 commit）。

## 10. 第四輪：上游移除 Minecraft 組件（#176，2026-11-11）

| 步驟 | 內容 |
|------|------|
| `master` ← `origin/master` | 3 個新 commit（含 `eb14f83` 移除 Minecraft 組件：96 檔刪除、約 −30,729 行）。6 個衝突：`backend/main.py`、`frontend/src/App.tsx`（保留重構結構＋移植移除 delta）；`backend/linkin/minecraft.py`、`backend/tools/minecraft_mcp.py`、`backend/tests/test_minecraft_mcp.py`（接受上游刪除）；`frontend/src/types.ts`（接受我方刪除，`minecraft_ops` 值移植到 `types/task.ts` 移除） |
| 重構側調整 | 刪除 `backend/api/routers/chat/minecraft_stream.py`；`chat/streaming.py` 移除 minecraft_ops 分支；`types/task.ts` 的 `resolved_path`／`RoutingPath` 移除 `minecraft_ops` |

驗收：pytest **1397 passed / 1 skipped**、ruff All checks passed、mypy Success（489 files）、tsc 0 error、vitest **16 檔 / 66 tests**、npm build BUILD_EXIT=0 → merge commit `f5252f6`。
