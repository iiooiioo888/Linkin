# 靈境·Linkin 知識庫

> EvoLoop 運行時 × 世界觀憲法 × 監控中心  
> 本倉庫基於 [EvoLoop](https://github.com/iiooiioo888/Evoloop)（MIT）衍生 · 倉庫：[iiooiioo888/Linkin](https://github.com/iiooiioo888/Linkin)  
> 文件對齊日期：2026-09-09

**詳文以本目錄為準**；根 [README](../README.md) 只保留落地頁與快速開始。

## 從哪裡開始

| 角色 | 入口 |
|------|------|
| 新加入的開發者 | [新人導覽](onboarding.md) → [目錄地圖](structure.md) |
| 要動手改程式 | [開發指南](development/guide.md) · [貢獻指南](../CONTRIBUTING.md) |
| Agent／自動化 | [AGENTS.md](../AGENTS.md) |
| 卡住了 | [常見問題](faq.md) |

## 目錄

### 導覽 · 結構

- [新人導覽](onboarding.md) — 閱讀順序、第一個 PR
- [目錄地圖](structure.md) — **套件／路徑單一來源**（改目錄先改此文）

### 架構

- [架構總覽](architecture/overview.md) — 統一管線、三層能力、目錄結構
- [反思閉環](architecture/reflection-loop.md) — 評分 → 反思 → 改進
- [公司運行時](architecture/company-runtime.md) — RAHO、角色、預算
- [OPC 工業整合](architecture/opc-integration.md) — 6 級閉環、護欄
- [優化路線圖](architecture/optimization-roadmap.md) — 已落地優化項
- [AI Hub 詳細設計](AI_HUB_DETAILED_DESIGN.md) — 探針／熔斷／目錄契約（路徑固定，測試會讀取）

### API · 配置

- [REST API 參考](api/reference.md) — 端點、SSE、WebSocket
- [配置參考](config/reference.md) — 環境變數、模型池、RAHO、價卡

### 公司工具

- [量化行情工具](company/quant-tools.md) — 行情、回測、組合、資金流

### 靈境·Linkin

- [世界觀](linkin/worldview.md)
- [系統設計](linkin/architecture.md)
- [靈境 API](linkin/api.md)
- [Minecraft MCP](linkin/minecraft-mcp.md)
- [頂層系統提示詞](linkin/system-prompt.md)

### 開發 · 部署

- [開發指南](development/guide.md)
- [部署指南](deployment/guide.md)
- [常見問題](faq.md)

### 套件 README（心智模型）

| 套件 | 說明 |
|------|------|
| [backend/README.md](../backend/README.md) | 後端從哪改起 |
| [opc_service/README.md](../opc_service/README.md) | OPC 護欄與六級節點 |
| [frontend/README.md](../frontend/README.md) | 前端開發入口 |

### 根目錄相關（非詳文重複）

| 檔案 | 用途 |
|------|------|
| [README.md](../README.md) | 落地頁 |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | 貢獻流程 |
| [AGENTS.md](../AGENTS.md) | Agent 約束 |
| [DESIGN.md](../DESIGN.md) | **前端視覺 Token**（非系統設計） |
| [design/README.md](design/README.md) | 視覺 Token 說明（避免與架構混淆） |
| [DEPLOYMENT.md](../DEPLOYMENT.md) | 指向部署指南的捷徑 |
| [docs/openapi.json](openapi.json) | OpenAPI 匯出（若有） |

### 文件維護規則

1. **詳文只寫在 `docs/`**；根 README 保持落地頁與快速開始。  
2. **目錄／套件變更**先更新 [structure.md](structure.md)，再改各處精簡樹。  
3. **`docs/AI_HUB_DETAILED_DESIGN.md` 路徑勿搬**（測試硬編碼讀取）。  
4. **`DESIGN.md` 只放視覺 Token**，勿寫入架構／API／RAHO。

---

## 快速導航

| 我想… | 去這裡 |
|--------|--------|
| 第一次上手 | [新人導覽](onboarding.md) |
| 找目錄／改哪個套件 | [目錄地圖](structure.md) |
| 了解整體架構 | [架構總覽](architecture/overview.md) |
| 查 API | [REST API](api/reference.md) |
| 配 LLM／模型池 | [配置參考](config/reference.md) |
| 本地開發 | [開發指南](development/guide.md) |
| 部署 | [部署指南](deployment/guide.md) |
| 反思閉環 | [reflection-loop](architecture/reflection-loop.md) |
| 多代理人 | [company-runtime](architecture/company-runtime.md) |
| OPC | [opc-integration](architecture/opc-integration.md) |
| 靈境／Minecraft | [worldview](linkin/worldview.md) · [minecraft-mcp](linkin/minecraft-mcp.md) |
| 量化工具 | [quant-tools](company/quant-tools.md) |
| 常見問題 | [faq](faq.md) |
