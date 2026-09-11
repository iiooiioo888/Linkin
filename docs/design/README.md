# docs/design — 視覺與設計相關說明

## 根目錄 `DESIGN.md` 是什麼？

根目錄的 [`DESIGN.md`](../../DESIGN.md) 是 **Linear 風格前端視覺 Token**（顏色、字級、間距），供 `design.md` 工具鏈與 UI 對齊使用。

它**不是**：

- 系統架構設計（請看 [`../architecture/overview.md`](../architecture/overview.md)）
- AI Hub 契約（請看 [`../AI_HUB_DETAILED_DESIGN.md`](../AI_HUB_DETAILED_DESIGN.md)）
- 產品需求規格

請勿把架構／API／RAHO 說明寫進根 `DESIGN.md`，以免與視覺 Token 格式衝突（該檔需維持可被 `npx @google/design.md lint` 檢查的結構）。

## 監控級儀表板 v3

[`monitor-dashboard-v3.html`](monitor-dashboard-v3.html) — gold/dark token、三欄 `216px / 1fr / 304px`、監控視覺元件結構參考。實作對應 `frontend/src/index.css`、`frontend/src/lib/consoleColors.ts`、`frontend/src/components/ui/monitor/`。

## 相關入口

| 主題 | 文件 |
|------|------|
| 新人導覽 | [../onboarding.md](../onboarding.md) |
| 前端開發 | [../../frontend/README.md](../../frontend/README.md) |
| 知識庫索引 | [../README.md](../README.md) |
