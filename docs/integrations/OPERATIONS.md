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

## 真實 ComfyUI（M3 驗收）

CI／無 GPU 環境預設走 mock。工作站實跑：

```bash
# 1. 啟動本機 ComfyUI（含 Flux IP-Adapter、LTX、Wan2.2-5B 工作流節點）
# 2. 指向 Studio
export COMFYUI_URL=http://127.0.0.1:8188
export LVS_USE_MOCK_COMFY=false
export LVS_STORAGE_BASE=/mnt/ai-media   # 或本機可寫路徑
export LVS_CLOUD_ENABLED=false

# 3. 啟動 Linkin API + render-agent poller（週期呼叫 run_once）
python -m backend.main
# 另開終端：輪詢 queued jobs
python - <<'PY'
from backend.local_video_studio.db import init_db, session_scope
from backend.local_video_studio.agent.poller import run_once
init_db()
while True:
    with session_scope() as s:
        print(run_once(s) or "idle")
    import time; time.sleep(5)
PY
```

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
3. `POST /projects/{id}/compose` 會呼叫 ffmpeg（無則寫假 MP4），**成功前強制** `compliance.stamp()`；不可跳過。

## 儲存與歸檔（M6）

- 建立專案時自動建立 `script/keyframes/drafts/refines/audio/output/logs/resources`。
- 資源彙總：`GET /projects/{id}/resources`；前端詳情頁顯示。
- 歸檔（人工）：`STORAGE_BASE=... ARCHIVE_BASE=... ./scripts/archive_project.sh <project_id>`

## Phase 2 stubs（M7）

`backend/local_video_studio/cloud_adapters/`（Vidu／CloudGPU）在 `CLOUD_ENABLED=false` 時一律拒絕；無 n8n。
