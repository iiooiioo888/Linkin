# 靈境·Linkin 系統設計

靈境是掛在既有 **EvoLoop 統一管線** 上的世界觀控制面，不是第二套後端。聊天、公司運行時、OPC、監控中心維持原路由；靈境只新增 `/linkin/*` 與監控「靈境」分組。

## 與 EvoLoop 的關係

```
使用者 / 監控中心
        │
        ▼
 FastAPI backend/main.py
        │
        ├── /chat /tasks /monitor/* /config /cloud /docker   （既有）
        └── /linkin/*  ← register_linkin(app)               （靈境）
                │
                ├── constitution.json   世界觀憲法
                ├── tools.py            工具鐵律
                ├── knowledge.py        RAG 四庫（Chroma → JSON 降級）
                └── roles.py            16 席子角色（繼承頂層提示詞）
```

複雜靈境任務仍走公司運行時：Manager 分解 → 建築／敘事／NPC／道具總監 → 執行者 → 審查員（四維 ≥80）→ 記錄員寫入 RAG。

## 五層控制

| 層 | 職責 | 程式位置 |
|----|------|----------|
| 身份 | 靈境意志 | `docs/linkin/system-prompt.md` |
| 憲法 | 陣營、靈絲術、邊界 | `backend/data/linkin_constitution.json` |
| 規則 | 思考流程、單次一工具 | `backend/linkin/prompts.py` |
| 工具 | 參數校驗、敏感二次確認 | `backend/linkin/tools.py` |
| 記憶 | 四維評分後寫入 | `backend/linkin/knowledge.py` |

## 部件對照（相對倉庫現況）

下列路徑在倉庫中**已經存在**，請勿平行再寫一套同名模組。

| 模組 | 路徑 | 狀態 |
|------|------|------|
| FastAPI 入口 | `backend/main.py` | 已掛載 `/linkin/*` |
| 統一圖 / 節點 / LLM | `backend/core/` | EvoLoop 既有 |
| 公司協調器與 80 席角色 | `backend/company/` | 既有；靈境加 16 席 custom |
| AI Hub | `backend/hub/` | 既有 |
| 監控／雲／Docker | `backend/services/` | 既有 |
| 靈境憲法／API／工具 | `backend/linkin/` | 已落地 |
| 種子 | `backend/scripts/seed_linkin_world.py` | 已落地 |
| OPC 微服務 | `opc_service/` | 既有 6 級閉環 |
| 前端監控與靈境面板 | `frontend/src/` | 已落地 |
| Docker Compose / CI / LICENSE | 倉庫根目錄 | 既有 |
