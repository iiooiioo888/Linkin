# Local Video Studio — 運維手冊（M3–M6）

## 環境變數

| 變數 | 預設 | 說明 |
| --- | --- | --- |
| `LVS_STORAGE_BASE`／`STORAGE_BASE` | `/mnt/ai-media` | 媒資根；專案相對路徑僅允許其下 |
| `LVS_COMFYUI_URL`／`COMFYUI_URL` | （空→mock） | 真實 ComfyUI 位址，例如 `http://127.0.0.1:8188` |
| `LVS_USE_MOCK_COMFY` | 未設且無 URL→true | 強制 mock／真實；CI 請保持 mock |
| `LVS_CLOUD_ENABLED`／`CLOUD_ENABLED` | `false` | MVP 禁止雲端／n8n |
| `LVS_COMPLIANCE_TEXT` | `AI 生成` | 成片顯式標識文字 |
| `LVS_AGENT_ID` | `workstation-5090` | render-agent 認領 ID |
| `LVS_AGENT_POLL_INTERVAL_SEC` | `5` | daemon 輪詢間隔（秒） |
| `LVS_JOB_TIMEOUT_SEC`／`JOB_TIMEOUT_SEC` | `7200` | 等待 Comfy history 的上限（秒） |
| `LVS_QUEUE_STALL_SEC` | `300` | `/queue` 狀態不變則判定停滯 |
| `LVS_ALLOW_FAKE_MEDIA` | `false` | 僅 dev／test 可寫假 MP4；正式環境必須失敗 |
| `LVS_VERIFY_MODEL_SHA256` | `false` | `true` 時 sha256 未登記或不符即拒絕執行 |
| `LVS_DRAWTEXT_FONT` | 系統 DejaVu／Liberation，否則失敗 | drawtext `fontfile`；缺檔不得略過「AI 生成」 |
| `LVS_LEASE_TTL_SEC` | `120` | agent 租約；過期後 running job 退回 queued |

## 真實 ComfyUI（M3 驗收）

CI／無 GPU 環境預設走 mock。工作站實跑：

```bash
# 1. 啟動本機 ComfyUI（含 Flux IP-Adapter、LTX、Wan2.2-5B 工作流節點）
# 2. 指向 Studio
export COMFYUI_URL=http://127.0.0.1:8188
export LVS_USE_MOCK_COMFY=false
export LVS_STORAGE_BASE=/mnt/ai-media   # 或本機可寫路徑
export LVS_CLOUD_ENABLED=false

# 3. 啟動 Linkin API，另開終端跑 render-agent daemon
python -m backend.main
python -m backend.local_video_studio.agent
```

Daemon 會寫心跳（`{STORAGE_BASE}/agents/{AGENT_ID}.heartbeat.json`）、以租約認領任務，並在 `SIGTERM`／`SIGINT` 時停止領取新任務、把等待中的 job 退回佇列。不另附 systemd unit：程序由 `docker-compose.local-video-studio.yml` 的 `lvs-worker-light`（`restart: unless-stopped`）負責拉起。

工作流模板與 mapping：

- `backend/local_video_studio/workflows/keyframe_flux_ipadapter.json`
- `backend/local_video_studio/workflows/ltx_draft.json`
- `backend/local_video_studio/workflows/wan5b_refine.json`
- 對應 `workflows/mappings/*.mapping.json`
- 執行時匯入：`POST /local-video-studio/api/v1/workflows`（版本進 DB；見 `docs/WORKFLOWS.md`）
- 模型註冊：`POST /local-video-studio/api/v1/models`；缺檔時 job 失敗且錯誤含模型名
- 任務日誌：`projects/<id>/logs/<job_id>.log`；`GET /jobs/{id}/log`
- API 文件：`docs/API.md` 與 `/docs` 同步

前端任務頁可建立關鍵幀／草稿／精修；產出落在 `projects/<id>/keyframes|drafts|refines/`。

## 審核與合成（M4–M5）

1. 精修資產進入審核佇列 → `POST /assets/{id}/review`（approve／reject／needs_retry）。
2. 僅 `approved` 且有 `selected_clip_asset_id` 的鏡頭可合成。
3. `POST /projects/{id}/compose` 呼叫 ffmpeg（字幕濾鏡、`amix`、音訊 `-map`、drawtext `fontfile`）。**預設不寫假 MP4**：找不到 ffmpeg、退出碼非 0、或顯式標識缺字型時丟出 `ComposeError`，任務標為 `failed`，**不寫** `ComplianceRecord`。只有測試或本機明確設 `LVS_ALLOW_FAKE_MEDIA=true` 才允許假成片。成功路徑在寫入合規紀錄前仍必須呼叫 `compliance.stamp()`。
4. 任務若帶 `input_image_relative_path` 而檔案不存在，job `failed`，錯誤含該路徑（不再補 1×1 PNG）。

## 儲存與歸檔（M6）

- 建立專案時自動建立 `script/keyframes/drafts/refines/audio/output/logs/resources`。
- 資源彙總：`GET /projects/{id}/resources`；前端詳情頁顯示。
- 歸檔（人工）：`STORAGE_BASE=... ARCHIVE_BASE=... ./scripts/archive_project.sh <project_id>`

## Phase 2 stubs（M7）

`backend/local_video_studio/cloud_adapters/`（Vidu／CloudGPU）在 `CLOUD_ENABLED=false` 時一律拒絕；無 n8n。
