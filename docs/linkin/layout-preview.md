# 布局預覽（Layout Preview）

Linkin 原生 2D 俯視面板，在 **未配置 Dynmap／BlueMap** 或 **MineMCP 橋接關閉** 時，仍可視化：

- 最新 `map_plan`（plots、paths、terrain、landmarks）
- 待落地／已規劃的 `build_brief`（依 `block_count` 估算 footprint）
- 敘事世界意圖 NPC（可解析座標或種子推算）

## 前端

- 路徑：`#/modules/minecraft/layout-preview`
- 導覽：Minecraft → **世界與建築** → **布局預覽**
- 互動：拖曳平移、滾輪／雙指縮放、點選要素查看詳情

## API

```
GET /linkin/minecraft/layout-preview
GET /linkin/minecraft/layout-preview?plan_id=map-xxx&region=织庭都
```

回傳 `features`（point／rect／polyline）、`bounds`、`legend`、`counts`。  
`label: planned` 表示 **計畫／dry-run**，不代表遊戲內已建造。

## 座標策略

- `map_plan` plot 座標視為 **絕對世界座標**（與落地一致）
- `build_brief`／NPC 若 `location` 無法解析為 `x,y,z`，以 `seed` + 索引做 **確定性偏移**（`layout_mode: synthetic`）
- 建築 footprint 由 `block_count` 平方根估算，僅供示意

## AI Snapshot

`GET /linkin/minecraft/ai/snapshot` 可選帶 `layout_summary`（要素數與 bounds），供 prompt 注入。
