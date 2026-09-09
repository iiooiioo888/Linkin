# 靈境·Linkin Frontend

單一版本 React 19 + Vite + TypeScript UI（IDE 風格 `AppShell`）。

| 活動欄 | 說明 |
|--------|------|
| 對話 | 聊天、任務進度；頂欄齒輪快速加入 API |
| 控制台 | EvoLoop：API 路由、角色／質詢樹、管線、L0、基礎設施 |
| 靈境 | 世界觀／NPC／任務／道具／工作室角色 |
| Minecraft | 建築方案、MineMCP 橋接 |
| 實驗室 | 提示詞、爬蟲、策略庫／策略圖、A/B… |

## 開發

```powershell
npm install
npm run dev
```

預設 **http://localhost:3001**（避開 Windows 上 5173 占用），API 代理至後端 `http://localhost:8000`。可用 `VITE_DEV_PORT` 覆寫。

## 關鍵目錄

| 路徑 | 用途 |
|------|------|
| `src/components/MonitorView.tsx` | 監控主視圖 |
| `src/lib/monitorTabs.ts` | 分頁單一資料源 |
| `src/lib/auth.ts` | 登入閘門 |
| `src/api/` | REST 客戶端（含 `linkin.ts`） |
| `src/components/linkin/` | 靈境／Minecraft UI |
| `src/vendor/neiki-gallery/` | 畫廊元件 |

## GitHub Pages

以 `VITE_BASE=/Linkin/`、`VITE_GITHUB_PAGES=true` 建置。完整說明：[部署指南](../docs/deployment/guide.md)。

## 相關文件

- [新人導覽](../docs/onboarding.md)
- [目錄地圖](../docs/structure.md)
- [開發指南](../docs/development/guide.md)
- [根 README](../README.md)
- 前端視覺 Token：根目錄 [`DESIGN.md`](../DESIGN.md)（非系統架構）
- Playwright E2E 預設 `http://localhost:3001`（`PLAYWRIGHT_BASE_URL` 可覆寫）
