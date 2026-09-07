# EvoLoop Frontend

單一版本 React + Vite + TypeScript UI（IDE 風格 `AppShell`）。

| 視圖 | 說明 |
|------|------|
| 聊天 | 對話、任務進度；頂欄齒輪快速加入 API |
| 控制台 | 執行／觀測／系統（API 路由、記憶、基礎設施）／靈境 |
| 軌跡 | 任務執行軌跡 |

## 開發

```powershell
npm install
npm run dev
```

預設 `http://localhost:3001`（避開 Windows 上 5173 占用），API 代理至後端 `http://localhost:8000`。可用環境變數 `VITE_DEV_PORT` 覆寫。

## GitHub Pages

以 `VITE_BASE=/Evoloop/`、`VITE_GITHUB_PAGES=true` 建置；完整說明見根目錄 [README.md](../README.md)。
