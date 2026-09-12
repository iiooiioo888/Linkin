# 靈境 REST API

Base URL 與主應用相同：`http://localhost:8000`

前端封裝：`frontend/src/api/linkin.ts`（開發時經 Vite `/api` 代理）。

## 憲法

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/linkin/constitution` | 讀取世界觀憲法 |
| PUT | `/linkin/constitution` | 部分更新；`replace: true` 則整份覆寫 |

## NPC

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/linkin/npcs` | 角色卡列表 |
| POST | `/linkin/npcs` | 建立（背景故事必填，寫入前四維 ≥80） |
| PUT | `/linkin/npcs/{id}` | 更新 |
| DELETE | `/linkin/npcs/{id}` | 刪除 |
| POST | `/linkin/npcs/{id}/dialogue` | RAG 檢索後對白；無可用 LLM 金鑰時回退模板句 |

## 任務／建築／道具

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/linkin/quests/generate` | 先檢索世界觀再生成；有 LLM 則結構化標題／描述 |
| GET | `/linkin/quests` | 任務列表 |
| DELETE | `/linkin/quests/{id}` | 刪除任務 |
| POST | `/linkin/buildings/generate` | 風格須匹配區域；單次 ≤ 5000 方塊；產出 **Sponge Schematic v3**（`.schem`） |
| GET | `/linkin/buildings` | 已規劃建築方案 |
| GET | `/linkin/buildings/{id}` | 單一方案（必要時補生成 schematic） |
| GET | `/linkin/buildings/{id}/preview` | Three.js 體素預覽（調色板＋座標，不含空氣） |
| GET | `/linkin/buildings/{id}/schematic` | 下載 `.schem`（Gzip NBT，Version 3） |
| POST | `/linkin/buildings/import` | 上傳 `.schem` / `.nbt`；讀取 v1／v2／v3，儲存時升級為 v3 |
| DELETE | `/linkin/buildings/{id}` | 刪除建築方案與對應 `.schem` |
| POST | `/linkin/items` | 稀有度區間校驗；名稱重複回 409 |
| GET | `/linkin/items` | 道具列表 |
| DELETE | `/linkin/items/{id}` | 刪除道具 |

## 敘事草稿工作區（Phase 0）

詳見 [narrative-workspace.md](./narrative-workspace.md)。

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/linkin/narrative/workspaces` | 建立工作區 |
| POST | `/linkin/narrative/workspaces/{id}/starter-pack` | 一鍵草案（不 auto-commit） |
| POST | `/linkin/narrative/workspaces/{id}/commit` | 提交至 Linkin 實體 |
| GET | `/linkin/events` | 歷史事件（RAG 事件庫） |
| GET | `/linkin/minecraft/status` | MineMCP 橋接狀態、乾跑、最近審計 |
| POST | `/linkin/minecraft/probe` | `tools/list` 探測（乾跑不發 HTTP） |
| POST | `/linkin/minecraft/call` | `{tool, arguments}`；鐵律與方塊上限與公司工具相同 |
| POST | `/linkin/buildings/{id}/dispatch` | 在方案錨點放置標記方塊（不一次填滿） |

## 管理與總覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/linkin/admin/execute` | 敏感指令需 `confirmed: true`，否則 409 |
| GET | `/linkin/overview` | NPC／任務／事件計數與合規狀態 |
| GET | `/linkin/server/health` | 伺服器健康快照 |
| POST | `/linkin/server/ask` | 運維問答（寫操作轉批准） |
| GET | `/linkin/server/approvals` | 批准隊列 |
| POST | `/linkin/server/approvals/{id}/confirm` | 批准 |
| POST | `/linkin/server/approvals/{id}/cancel` | 取消 |
| POST | `/linkin/server/patrol` | 巡檢（破壞性操作預設轉批准） |
| GET | `/linkin/server/report` | 日報 |
| GET | `/linkin/server/audit` | 運維審計尾部 |

## 統一模組目錄

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/modules` | 已註冊世界／整合模組清單（含 pages） |
| GET | `/modules/{id}` | 模組契約（導航、capabilities、pages、api_prefix） |
| GET | `/modules/{id}/pages` | 扁平頁面目錄（鍵、能力、API 前綴與路由） |
| GET | `/modules/{id}/pages/{page}` | 單一頁面契約 |
| GET | `/modules/{id}/health` | 模組健康（Minecraft 含世界／橋接／Admin） |
| GET | `/modules/{id}/capabilities` | 能力清單（api_prefix／routes） |
| ANY | `/modules/{id}/api/{path}` | 統一業務閘道；Minecraft 轉發 `/linkin/{path}`，寫入仍經護欄 |

新模組：註冊 `ModuleSpec`（nav／capabilities／health／page_aliases）+ 把實作掛在 `api_prefix`，前端 `createModuleClient(id)` 只打 `/modules/{id}/api/...`。`/linkin/*` 仍保留給既有測試與內部轉發。前端宿主在 `frontend/src/modules/`，控制台不含這些頁。

## 工具鐵律（所有寫入共用）

- 單次響應只准一個工具
- 禁止命令鏈 `&&`、`;`、`|`
- 風格與區域文化不符 → `style_mismatch`
- 方塊超限 → `block_limit`
- 未確認的踢人／封禁／停服 → `needs_confirmation`
- Admin.execute 通過後會轉發 Minecraft MCP `execute_command`（未設定 Token 則乾跑）
- 單次 fill 超過憲法／`EVOL_MC_MCP_MAX_FILL` → `block_limit`

## Sponge Schematic

建築方案以 **Sponge Schematic Version 3** 落地（副檔名 `.schem`）：Gzip NBT，根複合標籤內嵌 `Schematic`。

| 欄位 | 說明 |
|------|------|
| `Version` | `3` |
| `DataVersion` | Minecraft 資料版本（預設 1.21.x `3955`） |
| `Width` / `Height` / `Length` | `TAG_Short` 尺寸 |
| `Blocks.Palette` | 方塊狀態字串 → 索引（保留 `[facing=east]` 等狀態） |
| `Blocks.Data` | YZX VarInt 索引，`index = (y * length + z) * width + x` |
| `Blocks.BlockEntities` | `Pos` + `Id` + `Data` |
| `Biomes.Palette` / `Biomes.Data` | **3D** 生物群系，體積與方塊相同 |
| `Entities` | `Pos`（double×3）+ `Id` + `Data` |

仍可匯入 Version 1／2（根層 `Palette` + `BlockData`，v2 的 2D `BiomeData` 會展開成 3D）。Web 監控「建築」分頁用 Three.js 顯示 `preview` 體素。

詳見 [Minecraft MCP 整合](minecraft-mcp.md)。
