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
| POST | `/linkin/buildings/generate` | 風格須匹配區域；單次 ≤ 5000 方塊 |
| GET | `/linkin/buildings` | 已規劃建築方案 |
| POST | `/linkin/items` | 稀有度區間校驗；名稱重複回 409 |
| GET | `/linkin/items` | 道具列表 |

## 管理與總覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| POST | `/linkin/admin/execute` | 敏感指令需 `confirmed: true`，否則 409 |
| GET | `/linkin/overview` | NPC／任務／事件計數與合規狀態 |

## 工具鐵律（所有寫入共用）

- 單次響應只准一個工具
- 禁止命令鏈 `&&`、`;`、`|`
- 風格與區域文化不符 → `style_mismatch`
- 方塊超限 → `block_limit`
- 未確認的踢人／封禁／停服 → `needs_confirmation`
