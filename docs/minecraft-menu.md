# Minecraft 頂層選單與監控

Minecraft 已提升為 Linkin 左側 ActivityBar 的一級世界模組（與控制台、實驗室並列），不再僅藏在通用 Modules 下。

## 選單結構

| 分組 | 頁面 | 說明 |
| --- | --- | --- |
| **總覽／監控** | 監控總覽 | KPI、管線、橋接、AI 可見事件 |
| | 地圖監控 | map plan 列表與落地狀態 |
| | NPC 監控 | pending_world / applied / partial |
| | 任務／道具監控 | 世界意圖狀態帶 |
| | 建築落地監控 | build-brief jobs 與方塊進度 |
| | 橋接健康 | EVOL_MC_MCP_* 配置、ping、錯誤（無密鑰） |
| **敘事／RPG** | 敘事工作區 | Phase 0–5 一鍵管線 |
| **世界與建築** | 建築、地圖計畫、橋接 | 操作工具 |
| **實體** | NPC、任務、道具 | 內容 CRUD |
| **憲章／工作室／管理** | 世界觀、工作室、Admin | 憲法與運維 |

預設進入：`#/modules/minecraft` → 監控總覽。

## 舊書籤相容

以下 hash 仍可用（別名自動解析）：

- `#/modules/minecraft/world`、`#/monitor/world` → 世界觀
- `#/modules/minecraft/bridge`、`#/monitor/minecraft` → 橋接
- `#/modules/minecraft/building` → 建築
- `overview` / `monitor_hub` → 監控總覽

## AI 可觀測性 API

人類監控面板與 AI / 敘事管線共用事件源：

| 端點 | 用途 |
| --- | --- |
| `GET /linkin/minecraft/monitor/summary` | 監控 hub KPI |
| `GET /linkin/minecraft/ai/snapshot` | 當前世界/RPG 狀態摘要 |
| `GET /linkin/minecraft/ai/events` | 分頁動作日誌（since/cursor） |
| `GET /linkin/minecraft/ai/context` | LLM 注入用 markdown/JSON（`max_chars`） |

整合方式：

1. **LangGraph**：`enhance_with_linkin_context` 在靈境/Minecraft 查詢時注入可觀測性摘要。
2. **公司工具**：`minecraft_server_state`（唯讀）供 story_studio 角色拉取完整上下文。
3. **前端**：監控總覽底部「AI 可見事件」面板讀取同一 `/ai/events`。

事件在 generate / commit / apply（build、world、map）、bridge probe 等路徑自動追加；狀態誠實標記 dry-run、partial、bridge_offline。

## 本機試用

```bash
# 後端
python -m backend.main

# 前端
cd frontend && npm run dev
```

- **桌面**：左側 ActivityBar 點 Minecraft 圖示 → SidePanel 分組導覽。
- **手機**：底部 Chat / Tasks / Wallet / More（⋯）→ More 中選 Minecraft（底部僅 4 格，模組在溢出選單）。
