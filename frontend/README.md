# 靈境·Linkin Frontend

單一版本 React 19 + Vite + TypeScript UI（IDE 風格 `AppShell`）。

| 活動欄 | 說明 |
|--------|------|
| 對話 | 聊天；有進行中任務才左右分裂（左對話／文件／終端，右監控） |
| 控制台 | EvoLoop：總覽、執行、審計、計費、系統（不含世界觀／Admin） |
| 世界模組 | 可插拔宿主；Minecraft 為內建（世界觀／Admin／內容／建築／橋接），目錄 `GET /modules`，業務 `/modules/{id}/api/*` |
| 實驗室 | 提示詞、爬蟲、策略庫／策略圖、A/B… |

## 行動端／響應式

主斷點對齊 Tailwind **`md`（768px）**：

| 寬度 | 行為 |
|------|------|
| `<768px` | 左側 ActivityBar 改為**底部 Tab 列**；SidePanel 為漢堡選單抽屜（遮罩點擊關閉、body 捲動鎖定）；對話右側任務監控改為「監控」按鈕開啟全屏抽屜 |
| `≥768px` | 維持 IDE 三／四欄布局（ActivityBar \| SidePanel \| Main \| RightPanel） |

其他 CSS 斷點：聊天 `.ws` 平板堆疊 `960px`；控制台 `.rd-body` 堆疊 `1023px`；KPI 格 `consoleLayout` 使用 `sm`/`lg`。

**如何驗證**

1. `npm run dev` 後以 Chrome DevTools 裝置模式（例如 **390×844**）檢查：對話、控制台、世界模組、實驗室均可從底部 Tab 切換；側欄可開關。
2. 有進行中任務時，點「監控」應開啟任務監控抽屜；composer 貼底且含 `safe-area-inset`。
3. 可選：Chrome「加入主畫面」測試輕量 PWA（`manifest.webmanifest` + `theme-color`）。

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
| `src/lib/monitorTabs.ts` | 控制台分頁（總覽／執行／審計／計費／系統） |
| `src/lib/worldModules.ts` | 世界模組目錄（可 hydrate `GET /modules`） |
| `src/modules/` | 模組宿主；`minecraft/` 為獨立世界模組 |
| `src/lib/auth.ts` | 登入閘門 |
| `src/api/` | REST 客戶端（`createModuleClient` 統一閘道、`linkin.ts` 為 Minecraft 型別包裝） |
| `src/vendor/neiki-gallery/` | 畫廊元件 |

## GitHub Pages

以 `VITE_BASE=/Linkin/`、`VITE_GITHUB_PAGES=true` 建置。完整說明：[部署指南](../docs/deployment/guide.md)。

## 相關文件

- [新人導覽](../docs/onboarding.md)
- [目錄地圖](../docs/structure.md)
- [術語表](../docs/glossary.md)
- [開發指南](../docs/development/guide.md)
- [根 README](../README.md)
- 前端視覺 Token：根目錄 [`DESIGN.md`](../DESIGN.md)（非系統架構）
- Playwright E2E 預設 `http://localhost:3001`（`PLAYWRIGHT_BASE_URL` 可覆寫）
