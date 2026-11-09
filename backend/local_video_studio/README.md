# Local Video Studio（`local-video-studio`）

本機優先的私有化 AI 影片生成模組。完整規格見倉庫根目錄 [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)；整合說明見 [`docs/integrations/local-video-studio.md`](../../docs/integrations/local-video-studio.md)。

## 里程碑（本目錄）

| 里程碑 | 狀態 | 內容 |
| --- | --- | --- |
| **M0** | 完成 | 骨架、health、compose overlay |
| **M1** | 完成 | Project／Script／Shot CRUD + 鏡頭表匯入 + 前端列表 |
| **M2** | 本 PR | Jobs API + mock ComfyUI + render-agent poller + JobsPage |
| M3+ | 未實作 | 真實 ComfyUI — 見 PROJECT_SPEC |

## Health

```bash
curl -s http://127.0.0.1:8000/local-video-studio/health
# → {"ok":true,"module":"local-video-studio","milestone":"M2",...}
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/health
```

## M1 API（前綴 `/local-video-studio/api/v1`）

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| POST | `/projects` | 建立專案 |
| GET | `/projects` | 列表 |
| GET | `/projects/{id}` | 詳情（含 shot_count） |
| PATCH | `/projects/{id}` | 更新 name／status／description |
| POST | `/projects/{id}/scripts` | 上傳鏡頭表 JSON（可匯入 shots） |
| POST | `/projects/{id}/shots` | 建立鏡頭 |
| GET | `/projects/{id}/shots` | 鏡頭列表 |
| PATCH | `/shots/{id}` | 更新鏡頭 |

可選 `X-API-Key`（當 `LVS_API_KEY` 有值時強制）。

## 資料庫

- 預設 SQLite：`backend/data/local_video_studio.sqlite3`
- 覆寫：`LVS_DATABASE_URL=sqlite:////path/to.db` 或 Postgres URL
- Schema：`migrations/001_m1_projects_scripts_shots.sql`；啟動時 `create_all`

## 前端

`#/modules/local-video-studio`（專案）· `…/detail` · `…/shots`

## 約束

- `LVS_CLOUD_ENABLED`／`CLOUD_ENABLED` 預設 `false`
- M1 無 ComfyUI／Agent；測試以 tmp SQLite + monkeypatch 隔離


## M2 Jobs（`/local-video-studio/api/v1`）

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| POST | `/jobs` | 建立任務 |
| GET | `/jobs` | 列表（`status`／`project_id`） |
| POST | `/jobs/{id}/claim` | Agent 認領 |
| POST | `/jobs/{id}/complete` | 完成並寫入 Asset／Resource |
| POST | `/jobs/{id}/cancel` | 取消 |
| POST | `/jobs/{id}/retry` | 重試 |

Mock：`backend/local_video_studio/mock_comfyui.py`。Agent：`python -c "from backend.local_video_studio.agent import run_once; ..."`（見測試）。
