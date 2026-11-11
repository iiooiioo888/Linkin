# 靈境架構

靈境是掛在既有 **EvoLoop 統一管線** 上的世界觀控制面，不是第二套後端。聊天、公司運行時、OPC 維持原路由；靈境提供 `/linkin/*` 憲法與實體 API。

```
START → retrieve_memories → enhance_with_opc_context → enhance_with_linkin_context
    → enhance_with_recall_context → route_by_complexity
    → generate_initial_answer | run_company
```

複雜靈境任務（世界觀 + 敘事／NPC／任務／道具）走公司運行時：命中世界觀關鍵詞時由 `enhance_with_linkin_context` 注入憲法／RAG；這類查詢的預設模板可從 `quick_task` 升為 `story_studio`。

| 區塊 | 路徑 | 狀態 |
|------|------|------|
| 靈境憲法／API／工具 | `backend/linkin/` | 已落地（管線注入 `pipeline.py`、憲法、實體 RAG） |
| 世界／整合模組目錄 | `backend/modules/` | media-vault、local-video-studio |
