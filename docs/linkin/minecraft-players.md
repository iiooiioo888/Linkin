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

```json
POST /linkin/minecraft/players/ingest
{
  "action": "chat",
  "player": "Steve",
  "message": "hello",
  "summary": "Steve: hello"
}
```

允許的 `action`：`join`、`quit`、`move`、`chat`、`death`、`inventory`、`teleport`、`pickup`、`drop`、`block_break`、`block_place`。

## AI 可觀測性

- `GET /linkin/minecraft/ai/snapshot` → `players` 區塊（在線列表 + 近期活動）
- `GET /linkin/minecraft/ai/context` → Markdown 段落「玩家現場」
- 公司工具 `minecraft_server_state` 與 `enhance_with_linkin_context` 均會帶入上述摘要

查詢含「玩家／背包／在線」等關鍵字時也會注入 observability context。

## 前端

Minecraft 頂部選單 **玩家／現場 → 玩家現場**（`#/modules/minecraft/player_presence`）。

監控總覽 KPI 含「在線玩家」並連至本頁。

## 隱私

聊天 ingest 可能含 PII；營運面板如實顯示，請限制面板存取。Linkin 不記錄密碼或 Token。
