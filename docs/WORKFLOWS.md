# Local Video Studio — 工作流與模型

FEATURES_AND_TOOLS §5：不自動安裝 ComfyUI 自訂節點；僅文件列出必要節點與模型。

## 倉內模板（#167）

| 模板名 | JSON | mapping | 用途 |
| --- | --- | --- | --- |
| `keyframe_flux_ipadapter` | `backend/local_video_studio/workflows/keyframe_flux_ipadapter.json` | `mappings/keyframe_flux_ipadapter.mapping.json` | 關鍵幀 |
| `ltx_draft` | `.../ltx_draft.json` | `mappings/ltx_draft.mapping.json` | LTX 草稿 |
| `wan5b_refine` | `.../wan5b_refine.json` | `mappings/wan5b_refine.mapping.json` | Wan 5B 精修 |

Render agent 優先讀 DB 匯入版本；否則回退上表倉內檔。

## 執行時匯入（P0-03）

`POST /local-video-studio/api/v1/workflows` 上傳 ComfyUI **API 格式** JSON＋mapping。

- 匯入時以 `inject_params` 校驗：mapping 指向的 node／input 不存在 → **422**，訊息含 node id。
- 同名再匯入 → `version` +1；任務可用 `workflow_version` 綁定。
- 落盤副本：`workflows/imported/{name}.v{N}.json`（DB blob 為真相）。

Job 執行中若 mapping 缺 node → job `failed`，`error` 明確標示。

## 必要 ComfyUI 節點（人工安裝）

- ComfyUI-Manager
- ComfyUI-IPAdapter-plus / FaceID
- ComfyUI-ControlNet-Aux
- ComfyUI-VideoHelperSuite
- （可選）RIFE／幀插值

## 模型註冊（P0-11）

`POST /local-video-studio/api/v1/models` 登記：`name`、`path`、`sha256`、`vae_name`、`notes`。

Agent claim 後、submit 前：

1. 合併 job `required_models` 與模板 `required_models_json`
2. 查 `lvs_model_registry`；未註冊或檔案不存在 → job 失敗，錯誤含**模型名**
3. VAE：Wan **5B** 不可用 `wan_2.1_vae`；Wan **14B** 不可用 `wan2.2_vae`

建議路徑根：`LVS_MODELS_ROOT` 或 `STORAGE_BASE/models`。

## 任務日誌（P0-12）

`STORAGE_BASE/projects/{project_id}/logs/{job_id}.log`（JSON Lines）。  
`GET /jobs/{id}/log` 回傳尾部與 `error_summary`；JobsPage 顯示 `error`。
