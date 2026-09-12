# 敘事草稿工作區（Phase 0 / Phase 1）

> **北極星**：AI 生成完整 Minecraft RPG——故事、NPC、地圖、建築、道具等。  
> **本模組定位**：Phase 0「故事草稿工作區」＋ Phase 1「brief → AI 生成草案」，是完整管線的**草案桌**，不是終態。

## 管線概覽

```text
Phase 0  敘事工作區（本模組）  →  commit  →  Linkin 實體庫
Phase 1  任務／NPC／道具編排   →  既有 /linkin/* 與 RAG
Phase 2  建築／地圖意圖       →  build_briefs → Builder.generate → MineMCP dispatch
Phase 3  地圖生成／區域佈局   →  TODO：region map pipeline（未實作）
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

## 擴展點（TODO）

- **`build_brief` → 建築管線**：`backend/linkin/narrative_commit.py` 中 `_commit_build_brief` 標記 `status: pending_builder`；消費方應讀 `build_briefs` 並呼叫 `/linkin/buildings/generate`。
- **地圖／區域生成**：新增 `map_brief` 或擴展 `build_brief` 的 `region_layout` 欄位；實作放在獨立模組，勿寫入敘事工作區圖譜。
- **MineMCP 即時建造**：經 `backend/tools/minecraft_mcp.py` 護欄；不在 Phase 0 commit 路徑自動觸發。
- **一鍵草案 LLM**：`backend/linkin/narrative_starter.py`；無金鑰時使用 `fallback_starter_pack`。
- **brief AI 生成（Phase 1）**：`backend/linkin/narrative_generate.py`；`POST /generate` 接受 `{ brief, locale?, keys?, region?, theme? }`；成功時以 **replace-per-key** 覆寫所請求鍵，解析失敗時保留既有草稿；計量經 `call_llm`（`trace_label=narrative_generate`）。

## 前端

Minecraft 模組 → **敘事工作區**（`#/modules/minecraft/narrative`）  
面板：`frontend/src/modules/minecraft/NarrativeWorkspacePanel.tsx`
