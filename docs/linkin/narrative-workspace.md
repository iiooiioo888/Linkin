# 敘事草稿工作區（Phase 0 / Phase 1）

> **北極星**：AI 生成完整 Minecraft RPG——故事、NPC、地圖、建築、道具等。  
> **本模組定位**：Phase 0「故事草稿工作區」＋ Phase 1「brief → AI 生成草案」，是完整管線的**草案桌**，不是終態。

## 管線概覽

```text
Phase 0  敘事工作區（本模組）  →  commit  →  Linkin 實體庫
Phase 1  任務／NPC／道具編排   →  既有 /linkin/* 與 RAG
Phase 2  建築／地圖意圖       →  build_briefs → 使用者手動「落地建築」→ Builder.generate + place_block
Phase 3  NPC／任務／道具落地  →  world_status: pending_world → 使用者手動「落地」→ store + MineMCP 標記
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
| POST | `/{id}/generate` | Phase 1：依 `brief` LLM 生成草稿（**replace-per-key**），**不** auto-commit |
| POST | `/{id}/commit` | 提交至 Linkin 實體 |
| POST | `/{id}/confirm` | 快照衝突 `{ choice: rebind\|discard }` |
| POST | `/refresh-l0` | L0 刷新 `{ new_snapshot_id }` |

## Phase 0 草稿鍵

| 鍵 | 提交目標 | 後續管線 |
|----|----------|----------|
| `story_arc` | `story_arcs.json` + 世界觀 RAG | 主線編排 |
| `quest` | `quests.json` + 事件 | 任務面板／遊戲邏輯 |
| `npc` | Chroma NPC store | 對話／關係 |
| `item` | `items.json` + 世界觀 RAG | 道具平衡 |
| `build_brief` | `build_briefs.json` + 世界觀 RAG | **Phase 2**：`Builder.generate` + MineMCP |

## Phase 2：落地建築（build_brief → MineMCP）

Base：`/linkin/build-briefs`（Minecraft 模組閘道：`/modules/minecraft/api/build-briefs`）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/` | 列出已提交的 `build_briefs` |
| GET | `/{id}` | 單筆建築意圖 |
| POST | `/{id}/preview` 或 `/preview` | Dry-run：生成 schematic、估算方塊數與世界邊界 |
| POST | `/{id}/apply` 或 `/apply` | **需 `confirm: true`**：生成並以 `place_block` 落地 |
| GET | `/jobs/{job_id}` | 非同步落地任務狀態（`async: true`） |
| POST | `/jobs/{job_id}/cancel` | 取消進行中的落地任務 |

實作：`backend/linkin/build_brief_apply.py`、`backend/linkin/build_brief_api.py`。

安全契約：

- Phase 0 **commit 不會**自動觸發 MineMCP；僅 `POST .../apply` + `confirm: true` 才落地。
- 橋接已啟用但未連線時回傳 `bridge_offline`（409）。
- 單次實心方塊 ≤ 5000；schematic 單軸 ≤ 128；超出回傳 `block_limit` / `bounds_exceeded`。

前端：敘事工作區提交後顯示「落地建築」；建築面板列出 `pending_builder` 意圖。

## Phase 3：落地 NPC／任務／道具

Base：`/linkin/world-intents`（Minecraft 模組閘道：`/modules/minecraft/api/world-intents`）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/` | 列出 `world_status: pending_world` 的敘事意圖 |
| POST | `/preview` | Dry-run：估算生成點與 MineMCP 動作 |
| POST | `/apply` | **需 `confirm: true`**：更新 store 狀態並嘗試遊戲內標記 |

實作：`backend/linkin/narrative_world_apply.py`、`backend/linkin/narrative_world_api.py`。

安全契約：

- Phase 0 **commit** 寫入實體庫並標記 `world_status: pending_world`；**不會**自動 summon／公告。
- **apply** 更新 `world_status` 為 `applied` 或 `partial`；橋接未連線時仍更新 Linkin 資料並回傳 `partial`（不偽造 in-game 成功）。
- 已 `applied` 的實體在重複 apply 時略過（idempotent）。

前端：敘事工作區提交後顯示 Phase 3 條；NPC／任務／道具面板顯示待落地提示。

## 擴展點（TODO）

- **地圖／區域生成**：新增 `map_brief` 或擴展 `build_brief` 的 `region_layout` 欄位；實作放在獨立模組，勿寫入敘事工作區圖譜。
- **一鍵草案 LLM**：`backend/linkin/narrative_starter.py`；無金鑰時使用 `fallback_starter_pack`。
- **brief AI 生成（Phase 1）**：`backend/linkin/narrative_generate.py`；`POST /generate` 接受 `{ brief, locale?, keys?, region?, theme? }`；成功時以 **replace-per-key** 覆寫所請求鍵，解析失敗時保留既有草稿；計量經 `call_llm`（`trace_label=narrative_generate`）。

## 前端

Minecraft 模組 → **敘事工作區**（`#/modules/minecraft/narrative`）  
面板：`frontend/src/modules/minecraft/NarrativeWorkspacePanel.tsx`
