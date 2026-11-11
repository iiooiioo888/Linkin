# Local Video Studio API

與 FastAPI 自動 OpenAPI（啟動後 [`/docs`](http://127.0.0.1:8000/docs)、[`/redoc`](http://127.0.0.1:8000/redoc)）同步的人類可讀說明。模組前綴：

| 前綴 | 說明 |
| --- | --- |
| `/local-video-studio` | health |
| `/local-video-studio/api/v1` | MVP v1（下表路徑皆相對此前綴，除非另註） |
| `/modules/local-video-studio/...` | 模組閘道別名（同 router） |

**鑑權**：`X-API-Key: <LVS_API_KEY>`。未設定 `LVS_API_KEY`／`API_KEY` 時開發環境可不帶。錯誤一律 `{ "detail": "..." }`。

互動式文件：主應用啟動後開啟 `http://<host>:8000/docs`，可複製 curl／Try it out。

---

## Health

```bash
curl -s http://127.0.0.1:8000/local-video-studio/health
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/health
```

---

## Projects / Scripts / Shots

```bash
# 建立專案
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/projects \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"name":"demo","description":"first cut"}'

# 列表／詳情／更新
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects -H "X-API-Key: $LVS_API_KEY"
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id} -H "X-API-Key: $LVS_API_KEY"
curl -s -X PATCH http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id} \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"status":"keyframing"}'

# 鏡頭表匯入
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/scripts \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"content_json":{"project_title":"demo","shots":[{"scene_no":1,"shot_no":1,"description":"wide alley","duration_sec":5}]}}'

# 鏡頭 CRUD
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/shots \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"scene_no":1,"shot_no":1,"description":"wide rainy alley","duration_sec":5}'
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/shots -H "X-API-Key: $LVS_API_KEY"
curl -s -X PATCH http://127.0.0.1:8000/local-video-studio/api/v1/shots/{shot_id} \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"status":"draft"}'
```

---

## Jobs

```bash
# 建立任務（可綁 workflow_version、required_models）
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/jobs \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{
    "project_id":"PROJECT_ID",
    "shot_id":"SHOT_ID",
    "job_type":"keyframe",
    "workflow_template":"keyframe_flux_ipadapter",
    "workflow_version":1,
    "required_models":["flux_dev"],
    "params":{
      "prompt":"cinematic keyframe",
      "seed":42,
      "width":1024,"height":1024,
      "input_image_relative_path":"projects/PROJECT_ID/script/ref.png",
      "output_relative_path":"projects/PROJECT_ID/keyframes/SHOT_ID.png"
    },
    "priority":100,
    "data_class":"local_only",
    "max_attempts":3
  }'

# 列表／詳情
curl -s 'http://127.0.0.1:8000/local-video-studio/api/v1/jobs?project_id=PROJECT_ID' -H "X-API-Key: $LVS_API_KEY"
curl -s 'http://127.0.0.1:8000/local-video-studio/api/v1/jobs?status=queued' -H "X-API-Key: $LVS_API_KEY"
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id} -H "X-API-Key: $LVS_API_KEY"

# Agent claim／complete／cancel／retry
curl -s -X POST 'http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id}/claim?agent_id=workstation-5090' \
  -H "X-API-Key: $LVS_API_KEY"
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id}/complete \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"status":"failed","error":"model missing: flux_dev"}'
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id}/cancel -H "X-API-Key: $LVS_API_KEY"
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id}/retry -H "X-API-Key: $LVS_API_KEY"

# P0-12：任務日誌（projects/{id}/logs/{job_id}.log）
curl -s 'http://127.0.0.1:8000/local-video-studio/api/v1/jobs/{job_id}/log?tail=80' \
  -H "X-API-Key: $LVS_API_KEY"
```

失敗任務的 `error`／`error_summary` 會出現在 JobsPage；日誌實體檔在 `STORAGE_BASE/projects/{project_id}/logs/{job_id}.log`。

---

## Workflows（P0-03）

```bash
# 匯入 ComfyUI API 格式 JSON＋mapping（缺 node → 422）
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/workflows \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{
    "name":"my_keyframe",
    "workflow_json":{"6":{"class_type":"CLIPTextEncode","inputs":{"text":"x"}}},
    "mapping_json":{"mappings":[{"param":"prompt","node_id":"6","input":"text"}]},
    "required_models":["flux_dev"],
    "notes":"imported"
  }'

curl -s 'http://127.0.0.1:8000/local-video-studio/api/v1/workflows?latest_only=true' -H "X-API-Key: $LVS_API_KEY"
curl -s 'http://127.0.0.1:8000/local-video-studio/api/v1/workflows/my_keyframe?version=1' -H "X-API-Key: $LVS_API_KEY"
```

同名再匯入會 bump `version`；job 可透過 `workflow_version` 綁定。詳見 [WORKFLOWS.md](./WORKFLOWS.md)。

---

## Models（P0-11）

```bash
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/models \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{
    "name":"flux_dev",
    "path":"/models/checkpoints/flux1-dev.safetensors",
    "sha256":"...",
    "vae_name":"ae.safetensors",
    "notes":"keyframe"
  }'

curl -s http://127.0.0.1:8000/local-video-studio/api/v1/models -H "X-API-Key: $LVS_API_KEY"
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/models/flux_dev -H "X-API-Key: $LVS_API_KEY"
```

Render agent 在 submit ComfyUI 前校驗：未註冊／檔案不存在 → job `failed`，`error` 含模型名。Wan 5B 不可搭配 `wan_2.1_vae`；Wan 14B 不可搭配 `wan2.2_vae`。

---

## Assets / Reviews / Compose / Resources

```bash
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/assets -H "X-API-Key: $LVS_API_KEY"
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/assets/{asset_id} -H "X-API-Key: $LVS_API_KEY"
curl -s -o out.bin http://127.0.0.1:8000/local-video-studio/api/v1/assets/{asset_id}/media -H "X-API-Key: $LVS_API_KEY"

curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/assets/{asset_id}/review \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"decision":"approve","reason":"ok"}'
curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/review-queue -H "X-API-Key: $LVS_API_KEY"

curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/compose \
  -H 'Content-Type: application/json' -H "X-API-Key: $LVS_API_KEY" \
  -d '{"shot_ids":["SHOT1","SHOT2"],"output_name":"final_v1.mp4","add_watermark":true}'

curl -s http://127.0.0.1:8000/local-video-studio/api/v1/assets/{asset_id}/compliance -H "X-API-Key: $LVS_API_KEY"
curl -s -X POST http://127.0.0.1:8000/local-video-studio/api/v1/assets/{asset_id}/compliance-stamp -H "X-API-Key: $LVS_API_KEY"

curl -s http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/resources -H "X-API-Key: $LVS_API_KEY"

# 上傳音訊／字幕／參考圖
curl -s -X POST 'http://127.0.0.1:8000/local-video-studio/api/v1/projects/{project_id}/uploads?kind=ref' \
  -H "X-API-Key: $LVS_API_KEY" -F 'file=@./ref.png'
```

---

## Python（httpx）示例

```python
import httpx

base = "http://127.0.0.1:8000/local-video-studio/api/v1"
headers = {"X-API-Key": "dev-key"}

with httpx.Client(base_url=base, headers=headers, timeout=30.0) as client:
    project = client.post("/projects", json={"name": "demo"}).json()
    shot = client.post(
        f"/projects/{project['id']}/shots",
        json={"scene_no": 1, "shot_no": 1, "description": "wide"},
    ).json()
    job = client.post(
        "/jobs",
        json={
            "project_id": project["id"],
            "shot_id": shot["id"],
            "job_type": "keyframe",
            "workflow_template": "keyframe_flux_ipadapter",
            "params": {"prompt": "neon"},
        },
    ).json()
    log = client.get(f"/jobs/{job['id']}/log").json()
```

---

## 變更約定

每次改動 `backend/local_video_studio/api.py` 路由時，同步更新本檔與 OpenAPI 描述（FastAPI 函式 docstring／`response_model`）。驗收：本檔列出全部 v1 端點，且 `/docs` 可開啟、示例可複製。
