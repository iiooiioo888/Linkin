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
| 型別 | `mypy backend/ opc_service/` | Success: no issues found（669 source files） |
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
| `backend/company/orchestrator.py` | 2,411 行 | 8 檔套件／2,753 行（最大 622）＝ 第三輪 |
| `frontend/src/components/LiveBoard.tsx` | 1,169 行 | **8 行 barrel** ＋ `liveboard/` 8 檔（最大 297）＝ 第三輪 |
| `frontend/src/components/ContextPanel.tsx` | 994 行 | **6 行 barrel** ＋ `contextpanel/` 8 檔（最大 293）＝ 第三輪 |
| `frontend/src/components/SkillsMcpPanel.tsx` | 1,149 行 | **7 行 barrel** ＋ `skills-mcp/` 9 檔（最大 379）＝ 第三輪 |
| `backend/services/task_manager.py` | 1,539 行 | 9 檔套件／1,946 行（最大 332）＝ 第四輪 |
| `backend/billing/pool_store.py` | 1,960 行 | 9 檔套件／2,135 行（最大 376）＝ 第四輪 |
| `backend/company/quant_tools.py` | 3,303 行 | 10 檔套件／3,574 行（最大 554）＝ 第四輪 |
| `frontend/src/components/SidePanel.tsx` | 905 行 | **7 行 barrel** ＋ `sidepanel/` 9 檔（最大 227）＝ 第四輪 |
| `frontend/src/components/DockerView.tsx` | 713 行 | **13 行 barrel** ＋ `dockerview/` 5 檔（最大 362）＝ 第四輪 |
| `backend/services/commander.py` | 1,559 行 | 9 檔套件／1,753 行（最大 375）＝ 第五輪 |
| `backend/services/auditor.py` | 1,418 行 | 9 檔套件／1,782 行（最大 430）＝ 第五輪 |
| `backend/core/provider_pool.py` | 1,229 行 | 6 檔套件／1,437 行（最大 323）＝ 第五輪 |
| `frontend/src/components/ApiRoutesEditor.tsx` | 774 行 | **9 行 barrel** ＋ `apiroutes-editor/` 7 檔（最大 316）＝ 第五輪 |
| `frontend/src/components/RoleDeskLayout.tsx` | 742 行 | **14 行 barrel** ＋ `roledesk/` 8 檔（最大 190）＝ 第五輪 |
| `backend/company/roles.py` | 1,905 行 | 8 檔套件／2,389 行（最大 479）＝ 第六輪 |
| `backend/company/role_catalog.py` | 1,218 行 | 8 檔套件／1,501 行（最大 463）＝ 第六輪 |
| `backend/services/agent_monitor.py` | 1,302 行 | 7 檔套件／1,468 行（最大 453）＝ 第六輪 |
| `frontend/src/components/ChatView.tsx` | 646 行 | **7 行 barrel** ＋ `chatview/` 6 檔（最大 375）＝ 第六輪 |
| `frontend/src/components/LabPanel.tsx` | 681 行 | **6 行 barrel** ＋ `labpanel/` 9 檔（最大 346）＝ 第六輪 |
| `backend/company/raho/inspector.py` | 954 行 | 7 檔套件／1,177 行（最大 446）＝ 第七輪 |
| `backend/core/api_router.py` | 938 行 | 6 檔套件／1,163 行（最大 312）＝ 第七輪 |
| `backend/company/decomposer.py` | 743 行 | 5 檔套件／836 行（最大 657）＝ 第七輪 |
| `frontend/src/components/IntegrationsPanel.tsx` | 699 行 | **7 行 barrel** ＋ `integrations/` 8 檔（最大 187）＝ 第七輪 |
| `frontend/src/components/AgentsMonitorPanel.tsx` | 664 行 | **8 行 barrel** ＋ `agentsmonitor/` 4 檔（最大 355）＝ 第七輪 |
| `backend/services/trace_logger.py` | 857 行 | 6 檔套件／953 行（最大 318）＝ 第八輪 |
| `backend/company/rate_card.py` | 781 行 | 5 檔套件／880 行（最大 464）＝ 第八輪 |
| `backend/services/context_insight.py` | 768 行 | 4 檔套件／825 行（最大 442）＝ 第八輪 |
| `frontend/src/types/monitor.ts` | 683 行 | **8 行 barrel** ＋ `monitor/` 4 檔（最大 297）＝ 第八輪 |
| `frontend/src/components/TaskPanel.tsx` | 625 行 | **14 行 barrel** ＋ `taskpanel/` 9 檔（最大 347）＝ 第八輪 |
| `backend/tools/server_admin.py` | 732 行 | 5 檔套件／912 行（最大 302）＝ 第九輪 |
| `backend/linkin/server_admin.py` | 729 行 | 5 檔套件／898 行（最大 325）＝ 第九輪 |
| `backend/company/quant_strategy_maps.py` | 773 行 | 4 檔套件／850 行（最大 352）＝ 第九輪 |
| `frontend/src/lib/chatWorkspace.ts` | 635 行 | **15 行 barrel** ＋ `lib/chatWorkspace/` 9 檔（最大 152）＝ 第九輪 |
| `frontend/src/components/ui/ConsoleLayout.tsx` | 629 行 | **45 行 barrel** ＋ `ui/consolelayout/` 10 檔（最大 172）＝ 第九輪 |
| `backend/company/state.py` | 709 行 | 8 檔套件／809 行（最大 332）＝ 第十輪 |
| `backend/hub/service.py` | 696 行 | 7 檔套件／937 行（最大 292）＝ 第十輪 |
| `backend/company/raho/protocol.py` | 613 行 | 7 檔套件／797 行（最大 209）＝ 第十輪 |
| `frontend/src/lib/monitorTabs.ts` | 575 行 | **16 行 barrel** ＋ `lib/monitorTabs/` 7 檔（最大 186）＝ 第十輪 |
| `frontend/src/components/SystemMetricsPanel.tsx` | 538 行 | **8 行 barrel** ＋ `systemmetrics/` 6 檔（最大 230）＝ 第十輪 |
| `backend/core/llm.py` | 713 行 | 9 檔套件／984 行（最大 259）＝ 第十一輪 |
| `backend/company/prompts.py` | 634 行 | 6 檔套件／727 行（最大 237）＝ 第十一輪 |
| `backend/company/mcp_clients.py` | 609 行 | 5 檔套件／712 行（最大 362）＝ 第十一輪 |
| `backend/services/docker_manager.py` | 606 行 | 8 檔套件／737 行（最大 219）＝ 第十一輪 |
| `frontend/src/components/RoleV3Desk.tsx` | 538 行 | **8 行 barrel** ＋ `roledesk-v3/` 7 檔（最大 196）＝ 第十一輪 |
| `backend/company/archify_compile.py` | 604 行 | 6 檔套件／718 行（最大 212）＝ 第十二輪 |
| `backend/company/budget.py` | 598 行 | 5 檔套件／651 行（最大 482）＝ 第十二輪 |
| `backend/company/quant_strategy_catalog.py` | 586 行 | 4 檔套件／617 行（最大 350）＝ 第十二輪 |
| `backend/linkin/api.py` | 582 行 | 11 檔套件／811 行（最大 171）＝ 第十二輪 |
| `backend/company/quant_capital_flow_maps.py` | 579 行 | 5 檔套件／620 行（最大 212）＝ 第十二輪 |

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

## 11. 第五輪：orchestrator 與三個前端大面板（round3，2026-11-11）

### 11.1 後端：CompanyOrchestrator 2,411 行 → 套件化 mixin

| 檔案 | 行數 | 內容 |
|------|-----:|------|
| `orchestrator/__init__.py` | 70 | 組合類 `CompanyOrchestrator(StateMixin, ExecutionMixin, ItemMixin, ToolLoopMixin, ReviewMixin)`、`call_llm` patch 表面、`from_checkpoint`、`__all__` |
| `_base.py` | 237 | `_llm_thread`＋屬性宣告與方法介面 stub（供 mypy 跨 mixin 解析） |
| `state.py` / `execution.py` / `item.py` / `tool_loop.py` / `review.py` | 469／517／583／238／622 | 取消與檢查點／執行迴圈／單項執行／工具閉環／審查與整合 |
| `_compat.py` | 17 | `call_llm` 延遲解析代理 |

- 外部 `from backend.company.orchestrator import CompanyOrchestrator`（40+ 處）一行未改；`patch("backend.company.orchestrator.call_llm")`（18+ 處）仍生效。
- AST 逐方法比對：41/41 方法與原檔**逐字元相同**；未改任何測試檔。

### 11.2 前端：三個大面板 → 薄 barrel + 子元件套件

| 原檔 | 重構後 |
|------|--------|
| `LiveBoard.tsx` 1,169 行 | 8 行 barrel ＋ `liveboard/` 8 檔（types／focus／cards／integrations／rails／kpis／center／主體，最大 297） |
| `ContextPanel.tsx` 994 行 | 6 行 barrel ＋ `contextpanel/` 8 檔（utils／composition／charts／panes／sections／header／主體，最大 293） |
| `SkillsMcpPanel.tsx` 1,149 行 | 7 行 barrel ＋ `skills-mcp/` 9 檔（Skills／Mcp／Cli／VizPlugins／shared／styles／tiers，最大 379） |

三者 default export 與既有 import 路徑（`lazy(() => import('./LiveBoard'))` 等）完全不變；抽取以逐行等價稽核（非空 body 行 multiset／LCS）確認 JSX 與邏輯未變。

### 11.3 第五輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 35 秒） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（496 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（41 個既有 warnings） |

## 12. 第六輪：task_manager／pool_store／quant_tools／SidePanel／DockerView（round4，2026-11-12）

### 12.1 後端三個大檔 → 套件（import 路徑與測試 patch 語意不變）

| 原檔 | 重構後 |
|------|--------|
| `services/task_manager.py` 1,539 行 | 9 檔／1,946 行：`models`／`store`／`lifecycle`／`budget`／`runtime`／`company_runtime`／`_base`／`_compat`／`__init__`；singleton 與 `TraceLogger`／checkpoint patch 表面保留（`_compat` 延遲解析）；49/49 方法 AST 逐字相同 |
| `billing/pool_store.py` 1,960 行 | 9 檔／2,135 行：`schema`／`schema_sql`（352 行 DDL）／`pricing`／`pools`／`task_billing`／`keys`／`misc`／`installments`／`__init__`；69/69 方法 AST 逐字相同、25 個 re-export 符號與 `_DEFAULT_DB` 路徑不變 |
| `company/quant_tools.py` 3,303 行 | 10 檔／3,574 行：`data`／`indicators`／`strategies`／`strategies_advanced`／`backtest`／`analysis`／`portfolio`／`tools`／`constants`／`__init__`；37 個公開名稱不變；102/102 函式 AST 相同；3 個測試檔的 `_http_get_json`／`_http_get_text` patch 目標改指 `quant_tools.data`；`pyproject` 的 mypy override 擴為 `backend.company.quant_tools.*` |

### 12.2 前端兩個面板 → 薄 barrel + 子元件套件

| 原檔 | 重構後 |
|------|--------|
| `SidePanel.tsx` 905 行 | 7 行 barrel ＋ `sidepanel/` 9 檔（types／shared／SessionList／AgentRoster／ApiRouteRoster／TaskRoster／LabSidebar／MonitorSidebar／主體，最大 227） |
| `DockerView.tsx` 713 行 | 13 行 barrel ＋ `dockerview/` 5 檔（ContainerCard／HealthBar／LogModal／shared／主體，最大 362） |

兩者 default export 與既有 import 路徑不變；抽取以逐行等價稽核（非空 body 行 multiset）確認 JSX／邏輯未變。

### 12.3 第六輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 33 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（521 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（41 個既有 warnings） |

文件同步：`backend/README.md`、`docs/structure.md`、`docs/company/quant-tools.md`、`docs/architecture/company-runtime.md`、`reflection-loop.md`、`optimization-roadmap.md` 的舊檔案路徑已更新為套件路徑。

## 13. 第七輪：commander／auditor／provider_pool／ApiRoutesEditor／RoleDeskLayout（round5，2026-11-12）

### 13.1 後端三個服務檔案 → 套件（import 路徑與測試 patch 語意不變）

| 原檔 | 重構後 |
|------|--------|
| `services/commander.py` 1,559 行 | 9 檔／1,753 行：`prompts`／`templates`／`ticket`／`rules`／`grill`／`planner`／`plan`／`commander`／`__init__`；`__all__` 40 個名稱不變，80/80 頂層節點 AST 逐字相同 |
| `services/auditor.py` 1,418 行 | 9 檔／1,782 行：`constants`／`bank`／`questions`／`scoring`／`scenario`／`ticket`／`service`／`auditor`／`__init__`；`__all__` 102 個名稱、94/94 定義 AST 相同；`_llm_question` patch 目標改指 `auditor.service`（4 處測試） |
| `core/provider_pool.py` 1,229 行 | 6 檔／1,437 行：`constants`／`helpers`／`catalog`／`health`／`registry`／`__init__`；46 個公開名稱、46/46 函式與 15/15 常數 AST 相同；18 處 `_http_get_json` patch 目標改指 `provider_pool.catalog` |

### 13.2 前端兩個面板 → 薄 barrel + 子元件套件

| 原檔 | 重構後 |
|------|--------|
| `ApiRoutesEditor.tsx` 774 行 | 9 行 barrel ＋ `apiroutes-editor/` 7 檔（presets／types／shared／RouteForm／RouteList／StrategyBar／主體，最大 316） |
| `RoleDeskLayout.tsx` 742 行 | 14 行 barrel ＋ `roledesk/` 8 檔（types／shared／Header／StatsStrip／OrgReportTree／TaskBlocks／MonitorBlocks／RightPanel，最大 190） |

公開 export（含 `PROVIDER_PRESETS`／`ProviderValue` 與 roledesk 13 個 named export）與既有 import 路徑不變；抽取以逐行等價稽核確認 JSX／邏輯未變。

### 13.3 第七輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 34 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（542 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（41 個既有 warnings） |

文件同步：`backend/README.md`、`docs/structure.md`、`docs/architecture/overview.md`、`docs/development/guide.md`、`docs/architecture/optimization-roadmap.md`、`frontend/src/components/taskdetail/labels.ts` 的舊檔案路徑已更新。

## 14. 第八輪：roles／role_catalog／agent_monitor／ChatView／LabPanel（round6，2026-11-12）

### 14.1 後端三個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `company/roles.py` 1,905 行 | 8 檔／2,389 行：`definitions_leadership`／`engineering`／`specialist`／`support`／`exec`＋`templates`（STANDARD_ROLES）＋`teams`（8 個 create_*＋BUILTIN_TEMPLATES）＋`__init__`；公開名稱 95/95 一致、91/91 頂層節點 AST 逐字相同、22 條段落註解保留 |
| `company/role_catalog.py` 1,218 行 | 8 檔／1,501 行：`constants`／`store`／`normalize`／`builtins`／`snapshots`／`query`／`service`／`__init__`；`dir()` 公開名 47/47、59/59 模組層定義 AST 相同；套件層 patch `resolve_runtime` 仍生效（未改測試）；24 個行為 probe 與 HEAD 一致 |
| `services/agent_monitor.py` 1,302 行 | 7 檔／1,468 行：`common`／`events`／`items`／`costs`／`roster`／`aggregate`／`__init__`；29 個公開名稱、32/32 函式與 11/11 常數 AST 相同；`_finalize_agent`／`_allocate_cloud_costs` patch 目標改指 `costs` 子模組 |

### 14.2 前端兩個面板 → 薄 barrel + 子元件套件

| 原檔 | 重構後 |
|------|--------|
| `ChatView.tsx` 646 行 | 7 行 barrel ＋ `chatview/` 6 檔（ChatConfirmPanel／ChatMonitorSide／ChatNav／ChatNotices／types／主體，最大 375）；hooks 順序與 confirm 跨任務 state 語意保留 |
| `LabPanel.tsx` 681 行 | 6 行 barrel ＋ `labpanel/` 9 檔（六個分頁子元件＋constants＋主體，最大 346）；state／effects 留在主體，切換分頁不流失輸入 |

### 14.3 第八輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（3 分 00 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（562 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（41 個既有 warnings） |

文件同步：`docs/company/roles.md`、`docs/structure.md`、`docs/development/guide.md` 舊路徑已更新。測試整合：`test_linkin_role_budgets.py`（收斂到 `agent_monitor.costs`）與 `test_aliyun_budget.py`（收斂到 `agent_monitor.aggregate`／`costs` 呼叫端）。

## 15. 第九輪：inspector／api_router／decomposer／IntegrationsPanel／AgentsMonitorPanel（round7，2026-11-12）

### 15.1 後端三個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `company/raho/inspector.py` 954 行 | 7 檔／1,177 行：`constants`／`models`／`similarity`／`schema`／`service`／`gate`／`__init__`；公開名稱 55/55、63/63 頂層節點 AST 逐字相同（含 `__all__` 與 CONSTITUTION_LAYER 全文） |
| `core/api_router.py` 938 行 | 6 檔／1,163 行：`models`／`presets`／`routes`／`selection`／`state`／`__init__`；`dir()` 公開名 51/51、52/52 定義 AST 相同；33 個行為 probe 與舊模組一致；無測試 patch 需調整 |
| `company/decomposer.py` 743 行 | 5 檔／836 行：`types`／`llm`／`service`／`_compat`／`__init__`；28 個公開名稱、AST 相同；`backend.company.decomposer.call_llm` 的 3 處既有 patch 經 `_compat` 延遲解析維持有效（測試零修改） |

### 15.2 前端兩個面板 → 薄 barrel + 子元件套件

| 原檔 | 重構後 |
|------|--------|
| `IntegrationsPanel.tsx` 699 行 | 7 行 barrel ＋ `integrations/` 8 檔（IntegrationCard／三組 Actions／RecallWorkbench／shared／helpers／主體，最大 187）；body 624/624 行逐字保留 |
| `AgentsMonitorPanel.tsx` 664 行 | 8 行 barrel ＋ `agentsmonitor/` 4 檔（RoleDeskPanes／RoleMonitorExtras／RoleDeepMonitor／主體，最大 355）；state／effects／handlers 留在主體，hooks 順序不變 |

### 15.3 第九輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 30 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（577 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（41 個既有 warnings） |

文件同步：`AGENTS.md`、`backend/README.md`、`docs/structure.md`、`docs/architecture/optimization-roadmap.md` 舊路徑已更新。

## 16. 第十輪：trace_logger／rate_card／context_insight／monitor types／TaskPanel（round8，2026-11-12）

### 16.1 後端三個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `services/trace_logger.py` 857 行 | 6 檔／953 行：`paths`／`logger`（TraceLogger）／`checkpoints`／`traces`／`stats`／`__init__`；公開名稱 28/28、23/23 頂層節點 AST 相同；預設目錄常數改 `parents[2]`（值逐字驗證相同） |
| `company/rate_card.py` 781 行 | 5 檔／880 行：`fields`／`cards`（54 個 model 費率表逐字保留）／`parsing`／`service`／`__init__`；`dir()` 公開名 17/17、費率資料 deep-equality 與 hash 相同 |
| `services/context_insight.py` 768 行 | 4 檔／825 行：`composition`／`insight`（419 行主聚合原樣）／`browser`／`__init__`；公開名稱 10/10、14/14 函式與 4/4 常數 AST 相同 |

### 16.2 前端型別與面板

| 原檔 | 重構後 |
|------|--------|
| `types/monitor.ts` 683 行 | 8 行 barrel ＋ `types/monitor/` 4 檔（opc 42／hub 89／agent 297／llmops 260）；types 對外 export 118 不變、monitor 26/26 宣告逐字相同 |
| `TaskPanel.tsx` 625 行 | 14 行 barrel ＋ `components/taskpanel/` 9 檔（roleMeta／phases／types／RoleIcon／PhaseProgress／KanbanBoard／TimelineBlock／主體，最大 347）；12 個公開 export 不變 |

### 16.3 第十輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 29 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（589 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（37 個既有 warnings） |

文件同步：`backend/README.md`、`docs/structure.md`、`docs/architecture/optimization-roadmap.md` 舊路徑已更新。

## 17. 第十一輪：server_admin（tools／linkin）／quant_strategy_maps／chatWorkspace／ConsoleLayout（round9，2026-11-12）

### 17.1 後端三個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `tools/server_admin.py` 732 行 | 5 檔／912 行：`config`／`guards`／`system`（psutil 軟依賴）／`operations`／`__init__`；公開名稱 47/47、39/39 頂層節點 AST 相同 |
| `linkin/server_admin.py` 729 行 | 5 檔／898 行：`config`／`pending`／`tools`／`agent`／`__init__`；`dir()` 公開名 33/33；`_llm_ready`／`call_llm` 的動態 monkeypatch 以 `_package_attr` 延遲解析維持有效（測試零修改） |
| `company/quant_strategy_maps.py` 773 行 | 4 檔／850 行：`ir`／`overview`／`strategies`／`__init__`；公開名稱 17/17＋私有 `_find_item`／`_listing`、18/18 函式 AST 相同 |

### 17.2 前端 lib 與 UI 元件

| 原檔 | 重構後 |
|------|--------|
| `lib/chatWorkspace.ts` 635 行 | 15 行 barrel ＋ `lib/chatWorkspace/` 9 檔（eventLog／kanban／taskView／files／code／types／status／query／metrics，最大 152）；38 個公開 export 不變、`chatWorkspace.test.ts` 4 tests 綠 |
| `ui/ConsoleLayout.tsx` 629 行 | 45 行 barrel ＋ `ui/consolelayout/` 10 檔（Shell／Rails／Sections／Kpi／Cards／SectionNav／hooks／types／cn／tokens，最大 172）；35 個公開 export 不變 |

### 17.3 第十一輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 59 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（600 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（37 個既有 warnings） |

其他：`pyproject` 的 mypy override 擴充 `backend.company.quant_strategy_maps.*` 並移除子模組 inline disable；`docs/company/quant-tools.md` 舊路徑更新。所有本地分支（含各輪 refactor 分支、backup、wip）已推上 GitHub。

## 18. 第十二輪：state／hub service／raho protocol／monitorTabs／SystemMetricsPanel（round10，2026-11-12）

### 18.1 後端三個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `company/state.py` 709 行 | 8 檔／809 行：`enums`／`role_types`／`role`／`budget`／`models`／`config`／`run_state`／`__init__`；公開名稱 24/24、16/16 頂層節點 AST 相同、27/27 段落註解保留；`CompanyRunState` 置於 `run_state` 以避循環 |
| `hub/service.py` 696 行 | 7 檔／937 行：`failover`／`probe`／`complete`／`agents`／`auth`／`_compat`／`__init__`；`dir()` 公開名 55/55；`backend.hub.service.call_llm` 的 2 處 patch 經 `_compat` 延遲解析維持有效（測試零修改） |
| `company/raho/protocol.py` 613 行 | 7 檔／797 行：`layers`／`labels`／`roles`／`flags`／`edges`／`models`／`__init__`；公開名稱 61/61、24/24 函式與 5/5 類別、31/31 常數 AST 相同 |

### 18.2 前端 lib／面板

| 原檔 | 重構後 |
|------|--------|
| `lib/monitorTabs.ts` 575 行 | 16 行 barrel ＋ `lib/monitorTabs/` 7 檔（navGroups／tabs／navHelpers／activity／types／tabAliases／worldModuleBridge，最大 186）；56 個公開 export 不變 |
| `components/SystemMetricsPanel.tsx` 538 行 | 8 行 barrel ＋ `systemmetrics/` 6 檔（主體／metrics／MetricTable／ReflectionCyclesCard／StageRouterCard／RightRail，最大 230）；hooks 順序與 default export 不變 |

### 18.3 第十二輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 31 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（619 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（37 個既有 warnings） |

文件同步：`docs/contracts/g-gate1-dual-gate.md` 與 frontend 5 處註解舊路徑更新。

## 19. 第十三輪：core/llm／prompts／mcp_clients／docker_manager／RoleV3Desk（round11，2026-11-12）

### 19.1 後端四個模組 → 套件（最高風險：core/llm）

| 原檔 | 重構後 |
|------|--------|
| `core/llm.py` 713 行 | 9 檔／984 行：`params`／`usage`／`completion`／`core`／`roles`／`stream`／`json_text`／`_compat`／`__init__`；公開名稱 22/22；**14 個 patch 目標**（`call_llm`／`completion`／`clamp_model`／`_build_call_hops`／`_call_llm_on_route`／`_resolve_call_target`／`_llm_params`／`_ensure_provider_prefix`／`_openrouter_extra` 等）經 `_compat` 延遲解析全部維持有效，測試檔零修改 |
| `company/prompts.py` 634 行 | 6 檔／727 行：`manager`／`developer`／`reviewer`／`templates`／`config`／`__init__`；公開名稱 21/21；prompt 逐字保留（AST 無差異、sha256 全部相同） |
| `company/mcp_clients.py` 609 行 | 5 檔／712 行：`models`／`sessions`／`registry`／`_compat`／`__init__`；公開名稱 26/26；私有 `_make_session`／`probe_server` patch 以 `_compat` 維持有效 |
| `services/docker_manager.py` 606 行 | 8 檔／737 行：查詢／格式／控制 mixin＋metrics＋errors＋manager；公開名稱 16/16、`DockerManager` 公開方法不變、`DOCKER_AVAILABLE`／`docker`／`_docker_manager` patch 點相容 |

### 19.2 前端面板

| 原檔 | 重構後 |
|------|--------|
| `RoleV3Desk.tsx` 538 行 | 8 行 barrel ＋ `roledesk-v3/` 7 檔（主體 59／LeftRail 157／CenterColumn 196／RightRail 151／WorkKanbanCard 52／shared／types）；default＋`RoleV3DeskProps` 不變 |

### 19.3 其他
- `backend/scripts/lint_contracts.py` 的 `_SDK_ALLOWLIST` 改為支援套件前綴（`backend/core/llm/`），修復 LLM 套件化後 `no_direct_provider_sdk` 契約測試。
- 文件：`backend/README.md`、`docs/structure.md`、`docs/AI_HUB_DETAILED_DESIGN.md`、`docs/architecture/optimization-roadmap.md`、`docs/architecture/system-architecture-2026-09.md` 舊路徑更新。

### 19.4 第十三輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 28 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（643 source files） |
| `tsc -p tsconfig.app.json --noEmit` | 0 error |
| `vitest run` / `npm run build` | 16 檔／66 tests passed／BUILD_EXIT=0 |
| `oxlint src` | 0 errors（37 個既有 warnings） |

## 20. 第十四輪：archify_compile／budget／quant_strategy_catalog／linkin api／quant_capital_flow_maps（round12，2026-11-12）

### 20.1 後端五個模組 → 套件

| 原檔 | 重構後 |
|------|--------|
| `company/archify_compile.py` 604 行 | 6 檔／718 行：`labels`／`layout`／`ir`／`diagrams`／`compile`／`__init__`；公開名稱 25/25；`ROOT` 改 `parents[3]`（值已驗證等價） |
| `company/budget.py` 598 行 | 5 檔／651 行：`constants`／`costs`／`tiers`／`manager`／`__init__`；`dir()` 公開名 20/20、`__all__` 逐字保留、8 個行為 probe 相同 |
| `company/quant_strategy_catalog.py` 586 行 | 4 檔／617 行：`data`／`rows`（345 行目錄資料逐字）／`queries`／`__init__`；公開名稱 6/6、AST 相同 |
| `linkin/api.py` 582 行 | 11 檔／811 行：`router`／`shared`／`npcs`／`server_routes`／`quests`／`grill`／`items`／`overview`／`constitution_routes`／`events`；**29 條路由 (path, methods, endpoint) 集合完全相同**、公開名稱 63/63 |
| `company/quant_capital_flow_maps.py` 579 行 | 5 檔／620 行：`profiles`／`diagrams`／`timeline`／`ir`／`__init__`；公開名稱 3/3、IR／Mermaid 字串逐字保留 |

### 20.2 第十四輪驗收

| 檢查 | 結果 |
|------|------|
| `pytest backend/tests/` | **1397 passed / 1 skipped / 0 failed**（2 分 29 秒，與重構前一致） |
| `ruff check backend/ opc_service/` | All checks passed |
| `mypy backend/ opc_service/` | Success（669 source files） |
| `tsc` / `vitest run` / `npm run build` | 0 error／16 檔 66 tests passed／BUILD_EXIT=0 |

文件同步：`docs/structure.md`、`docs/AI_HUB_DETAILED_DESIGN.md`、`docs/architecture/optimization-roadmap.md`、`docs/architecture/credit-pools-lifecycle.md`、`docs/architecture/system-architecture-2026-09.md`、`docs/company/quant-tools.md`、`backend/linkin/server_admin/__init__.py` docstring。
