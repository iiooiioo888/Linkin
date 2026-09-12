# 敘事草稿工作區（Phase 0）

> **北極星**：AI 生成完整 Minecraft RPG——故事、NPC、地圖、建築、道具等。  
> **本模組定位**：Phase 0「故事草稿工作區」，是完整管線的**草案桌**，不是終態。

## 管線概覽

```text
Phase 0  敘事工作區（本模組）  →  commit  →  Linkin 實體庫
Phase 1  任務／NPC／道具編排   →  既有 /linkin/* 與 RAG
Phase 2  建築／地圖意圖       →  build_briefs → Builder.generate → MineMCP dispatch
Phase 3  （併入 Phase 4）區域佈局消費 build_brief／NPC 錨點
Phase 4  區域 map_plan        →  generate / preview / apply（confirm=true）
```

契約：**C-L0-004**（`backend/linkin/narrative_workspace.py`）——不得維護第二套可寫世界觀圖譜；落庫必經顯式 `commit` + 注入 writer。

## REST

Base：`/linkin/narrative/workspaces`（Minecraft 模組閘道：`/modules/minecraft/api/narrative/workspaces`）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/` | 建立工作區 `{ task_id, snapshot_id }` |
| GET | `/` | 列舉（可 `?task_id=`） |
| GET | `/{id}` | 狀態 + 草稿內容 |
| PUT | `/{id}/drafts/{key}` | 寫草稿 `{ value }` |
| POST | `/{id}/draft` | 寫草稿 `{ key, value }` |
| POST | `/{id}/starter-pack` | 一鍵草案（LLM 或模板），**不** auto-commit |
| POST | `/{id}/commit` | 提交至 Linkin 實體 |
| POST | `/{id}/confirm` | 快照衝突 `{ choice: rebind\|discard }` |
| POST | `/refresh-l0` | L0 刷新 `{ new_snapshot_id }` |

## Phase 4 區域 map_plan

Base：`/linkin/map`（Minecraft 模組閘道：`/modules/minecraft/api/map/*`）

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/generate` | 從 `workspace_id` 草稿或已提交實體 + `region`/`seed` 生成 map_plan（LLM 或 fallback） |
| POST | `/preview` | 預覽 bounds／plot 數／預估方塊／POI；**不**寫世界 |
| POST | `/apply` | 落地 markers／paths／terrain；**需** `{ confirm: true }`；bridge 關閉時 dry-run |

### Schema（map_plan v1）

見 `backend/linkin/map_plan.py` 的 `MAP_PLAN_SCHEMA_DOC` 與 `validate_map_plan()`。

硬限制：`plots ≤ 32`，預估方塊 `≤ 2000`，bounds 各軸跨度 `≤ 128`。

### 一致性選擇

- **409**：僅在缺少 `confirm: true` 時（回傳 preview 供 UI 二次確認）。
- **200 + partial**：個別 plot 落地失敗時回傳 `{ status: "partial", minecraft.errors[] }`（與 narrative commit 部分成功模式對齊；Phase 2 building dispatch 為單錨點故無 partial）。
- **413**：超限 plan（plot／block／axis）在 generate/preview 階段拒絕。

## Phase 0 草稿鍵

| 鍵 | 提交目標 | 後續管線 |
|----|----------|----------|
| `story_arc` | `story_arcs.json` + 世界觀 RAG | 主線編排 |
| `quest` | `quests.json` + 事件 | 任務面板／遊戲邏輯 |
| `npc` | Chroma NPC store | 對話／關係 |
| `item` | `items.json` + 世界觀 RAG | 道具平衡 |
| `build_brief` | `build_briefs.json` + 世界觀 RAG | **Phase 2**：`Builder.generate` + MineMCP |

## 擴展點（TODO）

- **`build_brief` → 建築管線**：`backend/linkin/narrative_commit.py` 中 `_commit_build_brief` 標記 `status: pending_builder`；消費方應讀 `build_briefs` 並呼叫 `/linkin/buildings/generate`。
- **Phase 4 區域 map_plan**：`backend/linkin/map_plan.py` + `map_api.py`；從 story_arc／build_brief／NPC 生成 plots；不在 commit 路徑自動 apply。
- **MineMCP 即時建造**：經 `backend/tools/minecraft_mcp.py` 護欄；不在 Phase 0 commit 路徑自動觸發。
- **一鍵草案 LLM**：`backend/linkin/narrative_starter.py`；無金鑰時使用 `fallback_starter_pack`。

## 前端

Minecraft 模組 → **敘事工作區**（`#/modules/minecraft/narrative`）  
面板：`frontend/src/modules/minecraft/NarrativeWorkspacePanel.tsx`（Phase 0 草案 + Phase 4 地圖 strip）
