# Local Video Studio（本機優先影片工作室）

私有化 AI 影片生成流水線模組（代號 `local-video-studio`）。**完整規格**見倉庫根目錄 [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)（里程碑 M0–M7）。

## 本機優先

- 雲端預設關閉：`LVS_CLOUD_ENABLED=false`／`CLOUD_ENABLED=false`
- ComfyUI 在工作站本機執行，不進預設 `docker-compose.yml`
- 媒資／採集可與 [Media Vault](./media-vault.md)（`#/modules/media-vault`）並用；Studio 負責生成管線，Vault 負責採集庫

## Linkin 掛載（M0–M1）

| 層 | 路徑 |
| --- | --- |
| 規格 | `PROJECT_SPEC.md` |
| 後端 | `backend/local_video_studio/` → health + `/api/v1/projects|shots|scripts` |
| 模組目錄 | `GET /modules/local-video-studio` · `…/health` |
| 前端 | `#/modules/local-video-studio`（專案／詳情／鏡頭板） |
| Compose | `docker-compose.local-video-studio.yml`（`--profile local-video-studio`） |
| DB | `LVS_DATABASE_URL`（預設 SQLite）；DDL 見 `migrations/001_m1_*.sql` |

## 驗收

```bash
pytest backend/tests/test_local_video_studio.py -q
curl -s http://127.0.0.1:8000/local-video-studio/health
# M1：建立專案 → POST .../scripts 匯入 3 鏡 → GET .../shots
```

**M1 完成**：CRUD + 鏡頭表匯入。**M2+**（Agent／ComfyUI）未實作。
