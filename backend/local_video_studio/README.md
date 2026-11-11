# Local Video Studio（`local-video-studio`）

本機優先的私有化 AI 影片生成模組。完整規格見 [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)；功能矩陣見 [`FEATURES_AND_TOOLS.md`](../../FEATURES_AND_TOOLS.md)；整合說明見 [`docs/integrations/local-video-studio.md`](../../docs/integrations/local-video-studio.md)；backlog 見 [`docs/backlog/`](../../docs/backlog/README.md)；運維見 [`docs/integrations/OPERATIONS.md`](../../docs/integrations/OPERATIONS.md)。

**OpenAPI**：主應用啟動後開啟 `/docs`（Swagger）或 `/redoc`；LVS 前綴 `/local-video-studio` 與 `/local-video-studio/api/v1/*`（`X-API-Key`）。人類可讀端點表見 backlog [P0-13](../../docs/backlog/P0-13-API-文档同步.md)（`docs/API.md` 仍待補）。

## 里程碑

| 里程碑 | 狀態 | 內容 |
| --- | --- | --- |
| **M0** | 完成 | 骨架、health、compose overlay |
| **M1** | 完成 | Project／Script／Shot CRUD + 鏡頭表匯入 |
| **M2** | 完成 | Jobs API + mock ComfyUI + render-agent poller |
| **M3** | 完成 | ltx_draft／keyframe 工作流+mapping；`COMFYUI_URL` 真實路徑，否則 mock |
| **M4** | 完成 | wan5b_refine + Review API／UI + 鏡頭狀態機 |
| **M5** | 完成 | ffmpeg_compose + 強制 compliance.stamp + ComposePanel |
| **M6** | 完成 | StorageAdapter、資源彙總 API／UI、archive 腳本 |
| **M7** | stub | Vidu／CloudGPU；無 n8n |

## Health

```bash
curl -s http://127.0.0.1:8000/local-video-studio/health
# → milestone: M6, cloud_enabled: false, use_mock_comfy: …
```

## API 前綴 `/local-video-studio/api/v1`

完整端點與可複製 curl／httpx 見 [`docs/API.md`](../../docs/API.md)；工作流／模型見 [`docs/WORKFLOWS.md`](../../docs/WORKFLOWS.md)。

| 方法 | 路徑 | 說明 |
| --- | --- | --- |
| * | `/projects` `/shots` `/scripts` | M1 CRUD |
| * | `/jobs` `/jobs/{id}/claim|complete|cancel|retry` | M2 |
| GET | `/jobs/{id}/log` | P0-12 任務日誌尾部 |
| POST/GET | `/workflows` `/workflows/{name}` | P0-03 模板匯入與版本 |
| POST/GET | `/models` `/models/{name}` | P0-11 模型註冊 |
| GET | `/projects/{id}/assets` | 資產列表 |
| POST | `/assets/{id}/review` | approve／reject／needs_retry |
| GET | `/projects/{id}/review-queue` | 審核佇列 |
| POST | `/projects/{id}/compose` | 合成（強制 stamp） |
| GET/POST | `/assets/{id}/compliance`／`compliance-stamp` | 合規 |
| GET | `/projects/{id}/resources` | 資源彙總 |

## 前端（SPEC §10）

`#/modules/local-video-studio` → 專案／詳情／鏡頭板／任務／審核／合成／資源

- 鏡頭板：scene 分組、關鍵幀縮圖、草稿／精修 `<video>`、生成與審核按鈕
- 審核：佇列 + 播放器 + reason
- 任務：attempt／取消／重試
- 合成：排序、音訊／字幕上傳、合規紀錄與成片播放
- 媒體：`GET /assets/{id}/media`；上傳：`POST /projects/{id}/uploads`

## 測試

```bash
pytest backend/tests/test_local_video_studio.py \
       backend/tests/test_local_video_studio_m2.py \
       backend/tests/test_local_video_studio_m3_m6.py \
       backend/tests/test_local_video_studio_p0_gaps.py -q
```

## 約束

- `CLOUD_ENABLED=false`；相對路徑僅允許 `STORAGE_BASE` 下
- Compose 成功前必須 `compliance.stamp()`，不可繞過
- CI 使用 mock Comfy；真實驗收見 OPERATIONS.md
