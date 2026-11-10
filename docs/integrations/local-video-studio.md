# Local Video Studio（本機優先影片工作室）

私有化 AI 影片生成流水線模組（代號 `local-video-studio`）。**完整規格**見倉庫根目錄 [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)（里程碑 M0–M7）。**運維／真實 Comfy** 見 [`OPERATIONS.md`](./OPERATIONS.md)。

## 本機優先

- 雲端預設關閉：`LVS_CLOUD_ENABLED=false`／`CLOUD_ENABLED=false`
- ComfyUI 在工作站本機執行；未設 `COMFYUI_URL` 時 agent 走 mock（CI 友好）
- 媒資根：`LVS_STORAGE_BASE`／`STORAGE_BASE`（預設 `/mnt/ai-media`）
- 媒資／採集可與 [Media Vault](./media-vault.md) 並用

## Linkin 掛載（MVP M0–M6）

| 層 | 路徑 |
| --- | --- |
| 規格 | `PROJECT_SPEC.md` |
| 後端 | `backend/local_video_studio/` |
| 模組目錄 | `GET /modules/local-video-studio` · `…/health`（milestone **M6**） |
| 前端 | `#/modules/local-video-studio`（專案／詳情／鏡頭／任務／審核／合成） |
| Compose overlay | `docker-compose.local-video-studio.yml` |
| 歸檔 | `scripts/archive_project.sh` |

## 驗收

```bash
pytest backend/tests/test_local_video_studio*.py -q
curl -s http://127.0.0.1:8000/local-video-studio/health
# 真實 M3：export COMFYUI_URL=http://127.0.0.1:8188 LVS_USE_MOCK_COMFY=false
```

**M0–M6 完成**（M7 僅 cloud adapter stubs）。
