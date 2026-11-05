# Media Vault（採集圖片展示 + 監控）

雙面板共用同一套媒資儲存（SQLite 元資料 + 本機目錄），執行期互不依賴。

## 架構

```
MediaCrawler job ──completed──► ingest.py ──► media_vault.sqlite3
                      │              │
                      │              ├── originals/{batch_id}/
                      │              └── thumbs/
                      │
展示面板 (gallery) ◄──GET /media-vault/images──┐
監控面板 (monitor) ◄──GET /media-vault/monitor/summary──┘
```

| 元件 | 路徑 | 職責 |
| --- | --- | --- |
| 入庫 | `backend/media_vault/ingest.py` | 解析 job 結果目錄、dedup、Pillow 縮圖 |
| 儲存 | `backend/media_vault/db.py` | `unified_posts` / `media_assets` / `ingest_events` |
| API | `backend/media_vault/api.py` | 列表、檔案、監控、replay |
| 展示 UI | `frontend/src/modules/media-vault/GalleryPanel.tsx` | 篩選、網格、燈箱 |
| 監控 UI | `frontend/src/modules/media-vault/MonitorPanel.tsx` | KPI、圖表、失敗表 |
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
3. 啟動後端；前端開 `#/modules/media-vault/gallery` 或實驗室「採集 → Media Vault」。
4. MediaCrawler 任務 **completed** 後自動 best-effort 入庫；開發可用 `POST /media-vault/ingest/replay`。

## 前端路由

- **展示**：`#/modules/media-vault/gallery`（自訂 React，依 `compliance_basis` 著色風險條）
- **監控**：`#/modules/media-vault/monitor`（同一 shell 內分頁可切換）

Immich 作為可選外部圖庫；未設定時不影響測試與本地展示。

## Grafana（PostgreSQL）

將 DB 遷移至 Postgres 後，可使用 [`media-vault-grafana.sql`](./media-vault-grafana.sql) 建立等價檢視。
