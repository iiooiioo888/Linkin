# 📚 靈境·Linkin 知識庫

> EvoLoop 運行時 × 世界觀憲法 × 監控中心  
> 本倉庫基於 [EvoLoop](https://github.com/iiooiioo888/Evoloop)（MIT）衍生 · 倉庫：[iiooiioo888/Linkin](https://github.com/iiooiioo888/Linkin)  
> 文件對齊日期：2026-09-04

## 目錄

### 🏗️ 架構

- [架構總覽](architecture/overview.md) — 統一管線、三層能力、數據流
- [反思閉環](architecture/reflection-loop.md) — 評分 → 反思 → 改進迭代機制
- [公司運行時](architecture/company-runtime.md) — 多代理人協調、80 席角色、工作項狀態機、預算管控
- [OPC 工業整合](architecture/opc-integration.md) — 6 級閉環、安全護欄、超時降級

### 📡 API

- [REST API 參考](api/reference.md) — 端點、請求/回應格式、SSE 串流、WebSocket

### ⚙️ 配置

- [配置參考](config/reference.md) — 環境變數、模型池／運維、模型價格、預算、LLM 配置

### 🌌 靈境·Linkin

- [世界觀](linkin/worldview.md) — 三大陣營、靈絲術、區域風格
- [系統設計](linkin/architecture.md) — 掛載方式、五層控制、部件對照
- [靈境 API](linkin/api.md) — `/linkin/*` 與工具鐵律
- [Minecraft MCP](linkin/minecraft-mcp.md) — MineMCP 橋接、角色工具、乾跑
- [頂層系統提示詞](linkin/system-prompt.md) — 所有子角色繼承的活文件

### 🛠️ 開發

- [開發指南](development/guide.md) — 專案結構、測試、調試、擴展點

### 🚀 部署

- [部署指南](deployment/guide.md) — Docker Compose、GitHub Pages（https://iiooiioo888.github.io/Evoloop/）、生產環境

---

## 快速導航

| 我想… | 去這裡 |
|--------|--------|
| 了解系統整體架構 | [架構總覽](architecture/overview.md) |
| 查看 API 端點 | [REST API 參考](api/reference.md) |
| 配置 LLM／模型池鎖定 | [配置參考](config/reference.md) · 根目錄 [README](../README.md#-模型池與運維) |
| 監控中心／自定義角色／層級跳轉 | 根目錄 [README](../README.md#-監控中心) |
| 記憶庫空白／寫入示範 60 條 | 根目錄 [README](../README.md#-快速開始) · `python -m backend.scripts.seed_demo_content` |
| 本地開發調試 | [開發指南](development/guide.md) |
| 部署到生產環境 | [部署指南](deployment/guide.md) |
| 理解反思閉環如何工作 | [反思閉環](architecture/reflection-loop.md) |
| 理解多代理人如何協作 | [公司運行時](architecture/company-runtime.md) |
| 接入工業設備 | [OPC 整合](architecture/opc-integration.md) |
| 靈境世界觀／NPC／建築 | [世界觀](linkin/worldview.md) · [靈境 API](linkin/api.md) |
