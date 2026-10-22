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
| POST | `/linkin/buildings/generate` | 風格須匹配區域；單次 ≤ 5000 方塊；**LLM 可用時由 LLM 理解需求設計 3D 模型**，否則程序化生成；產出 **Sponge Schematic v3**（`.schem`） |
| GET | `/linkin/buildings` | 已規劃建築方案 |
| GET | `/linkin/buildings/{id}` | 單一方案（必要時補生成 schematic） |
| GET | `/linkin/buildings/{id}/preview` | Three.js 體素預覽（調色板＋座標，不含空氣） |
| GET | `/linkin/buildings/{id}/schematic` | 下載 `.schem`（Gzip NBT，Version 3） |
| POST | `/linkin/buildings/import` | 上傳 `.schem` / `.nbt`；讀取 v1／v2／v3，儲存時升級為 v3 |
| DELETE | `/linkin/buildings/{id}` | 刪除建築方案與對應 `.schem` |
| POST | `/linkin/items` | 稀有度區間校驗；名稱重複回 409 |
| GET | `/linkin/items` | 道具列表 |
| DELETE | `/linkin/items/{id}` | 刪除道具 |
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

## 服務器運維（AIOps）

詳見 [服務器運維智能體](server-admin.md)。讀操作即問即答；寫操作一律產生 `pending_approval`，批准後才執行。

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/linkin/server/health` | 健康快照：磁盤／CPU／內存／Docker／白名單服務 → `ok\|warn\|critical` |
| POST | `/linkin/server/ask` | `{question, auto_approve?, role?}` 自然語言運維問答（LLM 規劃，關鍵詞兜底） |
| GET | `/linkin/server/approvals` | 待批准隊列（`?include_done=true` 含已處理） |
| POST | `/linkin/server/approvals/{id}/confirm` | 批准並執行；過期 409、不存在 404、重複確認 409 |
| POST | `/linkin/server/approvals/{id}/cancel` | 取消批准請求 |
| POST | `/linkin/server/patrol` | 主動巡檢：快照 + 規則提案（清理／輪轉／重啟 → 批准隊列） |
| GET | `/linkin/server/report` | Markdown 每日報告 |
| GET | `/linkin/server/audit` | JSONL 審計日誌尾部（`?limit=1..1000`） |

## 工具鐵律（所有寫入共用）

- 單次響應只准一個工具
- 禁止命令鏈 `&&`、`;`、`|`
- 風格與區域文化不符 → `style_mismatch`
- 方塊超限 → `block_limit`
- 未確認的踢人／封禁／停服 → `needs_confirmation`
- Admin.execute 通過後會轉發 Minecraft MCP `execute_command`（未設定 Token 則乾跑）
- 單次 fill 超過憲法／`EVOL_MC_MCP_MAX_FILL` → `block_limit`

## LLM 建築設計

`POST /linkin/buildings/generate` 在 LLM 可用時（`EVOL_LINKIN_LLM_DESIGN` 未關閉且有 API 金鑰），
由 `backend/linkin/design_llm.py` 把自然語言需求交給 LLM，輸出一套**受約束的建築 DSL**，
後端嚴格校驗後編譯成體素模型——LLM 真正「聽懂」需求（例如「拱形橋體與燈柱」會對應到
`arch` op 與 `column`＋發光方塊）。

```
需求 prompt ──▶ call_llm（DSL 說明 + 風格調色盤 + 材質白名單）
          ──▶ parse_design（嚴格校驗）──▶ compile_design（VoxelGrid + 預算裁剪）──▶ .schem v3
任一環節失敗 ──▶ 自動降級程序化生成（generate_structure），永遠有可用產出
```

DSL op 目錄（`y=0` 為地面；後面的 op 覆蓋前面的；`air` 可鏤空門窗）：

| op | 參數 | 用途 |
|----|------|------|
| `cuboid` | `x,y,z,w,h,d,material[,hollow]` | 實心／僅外殼長方體（地板、牆體） |
| `line` | `x1,y1,z1,x2,y2,z2,material` | 直線（橋面、樑、欄杆） |
| `column` | `x,y,z,height,material[,radius]` | 垂直圓柱（燈柱、塔柱） |
| `arch` | `x,y,z,span,height,material[,axis]` | 半圓拱（拱形橋體、門洞），`axis=x\|z` |
| `pyramid` | `x,y,z,w,d,height,material` | 階梯金字塔（神殿頂） |
| `gable` | `x,y,z,w,d,height,material` | 人字屋頂（脊沿 x） |

護欄（全部在編譯前強制）：

- op ≤ 48 個；畫布每軸 ≤ 64、體積 ≤ 65536；單 op 影響格數 ≤ 65536
- 材質白名單：風格調色盤角色名（`primary/secondary/accent/roof/floor/trim/fill`）∪ 已知方塊表；非法 op 跳過並記入 `warnings`，全部非法則整個設計作廢
- 非空氣方塊超預算 → 確定性裁剪（同種子可重現）
- 回應的建築紀錄含 `generator`（`llm`／`procedural`）與 `design`（op 序列，可重現／審計）

環境變數：`EVOL_LINKIN_LLM_DESIGN`（預設 `true`）、`EVOL_LINKIN_NO_LLM`（強制關閉一切靈境 LLM）。

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
