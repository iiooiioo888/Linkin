# Minecraft 玩家現場

Linkin 透過 MineMCP 橋接（`get_online_players` / `get_player`）輪詢伺服器內**真實**玩家狀態，並以快照 diff 寫入 `minecraft_events`（`domain=player`）。人類面板與 AI snapshot/context 共用同一資料源。

## 橋接能力（已驗證）

| MineMCP 工具 | Linkin 用途 |
| --- | --- |
| `get_online_players` | 在線名單 |
| `get_player` | 座標、維度、生命、飽食、遊戲模式、背包／裝備（依插件回傳 JSON） |

**目前不支援（需 ingest 或日後擴充）：** 即時 chat 訂閱、方塊 break/place 推送、死亡事件推送。MineMCP 無 server-side event stream。

## 有橋接 vs 無橋接

| 狀態 | 面板行為 |
| --- | --- |
| `EVOL_MC_MCP_ENABLED=true` 且已連線 | 每 ~5s 輪詢；顯示在線玩家、背包、diff 產生的 join/move/inventory 事件 |
| 乾跑 / 離線 / 未設定 Token | **誠實 empty UI**；不捏造位置或物品；仍顯示經 `ingest` 寫入的事件 |

## REST API

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| GET | `/linkin/minecraft/players?sync=true` | 在線列表 + 摘要 |
| GET | `/linkin/minecraft/players/{id}?sync=false` | 詳情 + 背包 grid |
| GET | `/linkin/minecraft/players/events` | 活動 feed（`player_id`、`action` 可篩） |
| POST | `/linkin/minecraft/players/ingest` | 外部插件 webhook（chat/death/block 等） |

模組閘道：`GET /modules/minecraft/api/minecraft/players` …

### Ingest 範例

模組閘道（同源）：`POST /modules/minecraft/api/minecraft/players/ingest`  
直連 Linkin API：`POST /linkin/minecraft/players/ingest`

**聊天**

```json
{
  "action": "chat",
  "player": "Steve",
  "message": "大家好！",
  "summary": "Steve: 大家好！"
}
```

**死亡**

```json
{
  "action": "death",
  "player": "Alex",
  "summary": "Alex 被殭屍擊敗",
  "cause": "zombie",
  "position": { "x": 120, "y": 64, "z": -30 }
}
```

**破壞／放置方塊**

```json
{
  "action": "block_break",
  "player": "Steve",
  "block": "DIAMOND_ORE",
  "summary": "Steve 破壞了鑽石礦",
  "position": { "x": 50, "y": 12, "z": 80 }
}
```

```json
{
  "action": "block_place",
  "player": "Alex",
  "block": "OAK_PLANKS",
  "summary": "Alex 放置了橡木木板",
  "position": { "x": 10, "y": 64, "z": 20 }
}
```

允許的 `action`：`join`、`quit`、`move`、`chat`、`death`、`inventory`、`teleport`、`pickup`、`drop`、`block_break`、`block_place`。

**驗證規則（400 由 `error` 欄位說明）：**

| 錯誤碼 | 條件 |
| --- | --- |
| `missing_action` | 未提供 `action` |
| `missing_player` | 未提供 `player`／`player_name`／`name` |
| `chat_requires_message` | `chat` 需 `message` 或 `summary` |
| `block_action_requires_block` | `block_break`／`block_place` 需 `block` |
| `death_requires_summary` | `death` 需 `summary` 或 `message` |

寫入事件會在 `details.source` 標記 `ingest`，面板以高亮顯示。

## AI 可觀測性

- `GET /linkin/minecraft/ai/snapshot` → `players` 區塊（在線列表 + 近期活動）
- `GET /linkin/minecraft/ai/context` → Markdown 段落「玩家現場」
- 公司工具 `minecraft_server_state` 與 `enhance_with_linkin_context` 均會帶入上述摘要

- 查詢含「玩家／背包／在線」等關鍵字時注入完整 observability context
- **Minecraft 模組會話**、**敘事／管線任務**（`story_studio`）在「有在線玩家或近期活動」時，即使未命中關鍵字也會注入精簡「玩家現場」段落（token 上限約 900 字）

## 布局預覽疊加

`GET /linkin/minecraft/layout-preview` 回應新增：

- `players[]`：在線玩家 XZ 座標、維度、背包摘要（需橋接有資料）
- `players_live`：`online_count`、`bridge_offline`、`hint`（橋接離線時「等待橋接／玩家」）

前端 `LayoutPreviewPanel` 以菱形標記疊加玩家，點選可跳轉玩家現場。

## 前端

Minecraft 頂部選單 **玩家／現場 → 玩家現場**（`#/modules/minecraft/player_presence`）。

空狀態文案為繁中「目前沒有玩家在線」；可設 `EVOL_MC_JOIN_ADDRESS`（或前端以站台 hostname:25565 推斷）顯示「加入伺服器」複製提示。

- **外部事件接入**：可複製 webhook 路徑與 chat／death／block JSON 範例
- 監控總覽 KPI 含「在線玩家」與 `players_live` 摘要，連至本頁

## 隱私

聊天 ingest 可能含 PII；營運面板如實顯示，請限制面板存取。Linkin 不記錄密碼或 Token。

## 解析注意

MineMCP `get_online_players` 若回傳英文空狀態句（如 `No players are currently online.`），必須視為空名單，**不可**拆成玩家名；否則 Monitor Hub KPI 會顯示在線 1，玩家現場列表則出現該英文句。
