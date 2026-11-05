# Media Vault（採集 · 媒体库）

三面板共用同一套媒資儲存（SQLite 元資料 + 本機目錄），執行期互不依賴。

## 一体化导航

```
實驗室 → 整合 → 採集 → 「采集 · 媒体库」
                              │
                              ▼
                    #/modules/media-vault  (Hub)
                    ┌─────────┬─────────┬─────────┐
                    │  控制   │  监控   │  图库   │
                    └────┬────┴────┬────┴────┬────┘
                         │         │         │
              MediaCrawlerPanel   KPI/图表   网格+灯箱
              + 入庫 replay      失败任务   batch 筛选
```

深链：`#/modules/media-vault/control` · `…/monitor` · `…/gallery`

## 架構

```
MediaCrawler job ──completed──► ingest.py ──► media_vault.sqlite3
                      │              │
                      │              ├── originals/{batch_id}/
                      │              └── thumbs/
                      │
控制 (control) ◄── GET /media-vault/control/overview
图库 (gallery) ◄── GET /media-vault/images
监控 (monitor) ◄── GET /media-vault/monitor/summary
```

| 元件 | 路徑 | 職責 |
| --- | --- | --- |
| 入庫 | `backend/media_vault/ingest.py` | 解析 job 結果目錄、dedup、Pillow 縮圖 |
| 儲存 | `backend/media_vault/db.py` | `unified_posts` / `media_assets` / `ingest_events` |
| API | `backend/media_vault/api.py` | 列表、檔案、監控、replay |
| Hub | `frontend/src/modules/media-vault/MediaVaultHub.tsx` | 三页签 + 相关仓库链接 |
| 控制 UI | `frontend/src/modules/media-vault/ControlPanel.tsx` | 嵌入 MediaCrawler + KPI |
| 图库 UI | `frontend/src/modules/media-vault/GalleryPanel.tsx` | 篩選、網格、燈箱 |
| 监控 UI | `frontend/src/modules/media-vault/MonitorPanel.tsx` | KPI、圖表、失敗表 |
| Immich（可選） | `backend/media_vault/sync_immich.py` | stub，設定 env 後擴充 |

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `MEDIA_VAULT_DATABASE_URL` | （檔案）`backend/data/media_vault.sqlite3` | `sqlite:///` 前綴或檔案路徑 |
| `MEDIA_VAULT_MEDIA_ROOT` | `backend/data/media_vault_media` | 原圖與縮圖根目錄 |
| `IMMICH_BASE_URL` | — | 可選，Immich 同步 |
| `IMMICH_API_KEY` | — | 可選 |

## 部署建議

1. 先確認監控 API 與 DB 路徑可寫（`GET /media-vault/monitor/summary`）。
2. 設定 `MEDIA_VAULT_*` 與 MediaCrawler 結果根目錄。
3. 啟動後端；前端開 `#/modules/media-vault` 或實驗室「採集 → 采集 · 媒体库」。
4. MediaCrawler 任務 **completed** 後自動 best-effort 入庫；控制页「入庫」或 `POST /media-vault/ingest/replay?job_id=`.

## 前端路由

- **Hub（默认控制）**：`#/modules/media-vault`
- **图库 / 监控**：`#/modules/media-vault/gallery`、`#/modules/media-vault/monitor`（Hub 内可切换）

Hub 页脚「相关仓库」：Linkin、MediaCrawler 上游、Immich / PhotoPrism 文档（可选外部图库）。

Immich 作為可選外部圖庫；未設定時不影響測試與本地展示。

## Grafana（PostgreSQL）

將 DB 遷移至 Postgres 後，可使用 [`media-vault-grafana.sql`](./media-vault-grafana.sql) 建立等價檢視。
