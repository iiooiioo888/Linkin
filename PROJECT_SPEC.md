# PROJECT_SPEC.md — 私有化 AI 影片生成平台（Local-First Video Studio）

## 0. 项目摘要

**项目代号**：`local-video-studio`  
**目标**：搭建一套全私有化、可重复、可审核的 AI 影片生成流水线，覆盖“创意 → 镜头表 → 关键帧 → 草稿 → 精修 → 审核 → 合成 → 合规标识 → NAS 归档”。  
**定位**：个人创作基础设施。成功标准是“从想法到第一版草稿的时间足够短、成片可控”，不是单部影片财务回本。  
**核心硬件假设**：
- 工作站：RTX 5090D **32GB 初版**（必须开箱验证 GPU-Z 显存约 32768 MiB），Windows/Linux 均可，推荐 Linux + NVIDIA 驱动 + CUDA。
- 存储服务器：自组 TrueNAS/Unraid，x86，64GB ECC，万兆内网，HDD RAIDZ2 归档 + NVMe 镜像活跃项目池。
- 云端：Vidu 等 API、云 GPU 租赁，**Phase 2 才接入，默认禁用**。

**非目标（MVP 明确不做）**：
- 不做多租户 SaaS。
- 不做自动投流、分账、财务 ROI 核算。
- 不做全自动无人值守成片；审核必须有人工终审。
- 不在 MVP 接入 n8n；先用内置任务队列。
- 不承诺 4K/长片；MVP 目标 720p、5–10 秒镜头、60–180 秒成片。

---

## 1. 系统架构

```text
┌────────────────────────────── NAS (TrueNAS) ──────────────────────────────┐
│  Docker Compose:                                                           │
│  - central-api (FastAPI)       项目/镜头/任务/审核/资源记录/合规记录        │
│  - web-ui (React/Vite)         项目看板、镜头板、审核、任务状态             │
│  - postgres                    主数据库                                     │
│  - redis                       队列/锁                                     │
│  - worker-light                合成、归档、合规标识、资源汇总               │
│  - (Phase2) scheduler          夜间队列、云端 API/云 GPU 适配器             │
│                                                                            │
│  存储挂载: /mnt/ai-media/projects/{project_id}/...                          │
└────────────────────────────────────────────────────────────────────────────┘
                 ▲ HTTP/JSON (内网, API Key)
                 │
┌────────────────┴──────────── 工作站 (RTX 5090D 32GB) ─────────────────────┐
│  - ComfyUI (127.0.0.1:8188)      执行工作流                                 │
│  - render-agent (FastAPI/Worker) 从 central-api 拉任务，注入参数，提交 ComfyUI│
│  - 本地挂载 NAS: /mnt/ai-media    输出直接写入项目目录                      │
│  - (可选) Ollama                  本地小模型拆分镜/提示词                   │
└────────────────────────────────────────────────────────────────────────────┘
```

**关键原则**：
- Central API 只记录**相对路径和元数据**，不搬运大文件。
- 工作站把 ComfyUI 输出直接写到 NAS 挂载目录；Central 通过路径索引。
- 所有任务有 `data_class`: `local_only` / `cloud_allowed`。MVP 全部 `local_only`。
- 云端适配器在 MVP 只留接口，不实现真实调用。

---

## 2. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11、FastAPI、SQLAlchemy 2、Alembic、Pydantic v2 |
| 数据库 | PostgreSQL 16（MVP 可用 SQLite 开发，生产用 PG） |
| 队列 | Redis + RQ（或 Celery；MVP 推荐 RQ 简单） |
| 前端 | React + Vite + TypeScript + Tailwind CSS；TanStack Query；OpenAPI 生成 client |
| 渲染执行 | ComfyUI API + Python `requests`/`httpx`；FFmpeg |
| 本地 LLM | Ollama（可选，Qwen 小参数 GGUF） |
| 部署 | Docker Compose（NAS）；工作站可用 systemd 或 Docker |
| 测试 | pytest、httpx MockTransport、Playwright（可选）、ComfyUI mock server |
| 日志 | structlog / JSON logs；任务日志写入 DB + 文件 |

---

## 3. 仓库结构

```text
local-video-studio/
├─ PROJECT_SPEC.md
├─ README.md
├─ docker-compose.nas.yml
├─ docker-compose.workstation.yml
├─ .env.example
├─ backend/
│  ├─ pyproject.toml
│  ├─ alembic/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ config.py
│  │  ├─ db.py
│  │  ├─ models/
│  │  │  ├─ project.py
│  │  │  ├─ shot.py
│  │  │  ├─ asset.py
│  │  │  ├─ job.py
│  │  │  ├─ review.py
│  │  │  ├─ resource.py
│  │  │  └─ compliance.py
│  │  ├─ schemas/
│  │  ├─ api/
│  │  │  ├─ projects.py
│  │  │  ├─ shots.py
│  │  │  ├─ jobs.py
│  │  │  ├─ assets.py
│  │  │  ├─ reviews.py
│  │  │  ├─ compose.py
│  │  │  └─ resources.py
│  │  ├─ services/
│  │  │  ├─ storage.py          # StorageAdapter: local / nas path
│  │  │  ├─ workflow_inject.py  # ComfyUI JSON 参数注入
│  │  │  ├─ comfy_client.py     # /prompt /history /upload/image
│  │  │  ├─ ffmpeg_compose.py
│  │  │  ├─ compliance.py       # 显式标识 + 元数据 + 水印接口
│  │  │  ├─ resource_meter.py
│  │  │  └─ cloud_adapters/     # Phase2: vidu.py, cloud_gpu.py (stub)
│  │  └─ workers/
│  │     ├─ compose_worker.py
│  │     └─ archive_worker.py
│  └─ tests/
├─ render-agent/
│  ├─ pyproject.toml
│  ├─ agent/
│  │  ├─ main.py
│  │  ├─ config.py
│  │  ├─ poller.py
│  │  ├─ comfy_runner.py
│  │  ├─ model_registry.py
│  │  └─ heartbeat.py
│  └─ tests/
├─ web/
│  ├─ package.json
│  ├─ src/
│  │  ├─ api/client.ts
│  │  ├─ pages/ProjectsPage.tsx
│  │  ├─ pages/ProjectDetailPage.tsx
│  │  ├─ pages/ShotBoardPage.tsx
│  │  ├─ pages/ReviewPage.tsx
│  │  ├─ pages/JobsPage.tsx
│  │  ├─ components/VideoPreview.tsx
│  │  └─ components/StatusBadge.tsx
├─ workflows/
│  ├─ keyframe_flux_ipadapter.json
│  ├─ ltx_draft.json
│  ├─ wan5b_refine.json
│  ├─ h3_audio_optional.json
│  └─ mappings/
│     ├─ keyframe_flux_ipadapter.mapping.json
│     ├─ ltx_draft.mapping.json
│     └─ wan5b_refine.mapping.json
├─ scripts/
│  ├─ verify_gpu.sh
│  ├─ make_shot_table.py
│  ├─ compose_ffmpeg.sh
│  └─ seed_demo.py
└─ docs/
   ├─ API.md
   ├─ WORKFLOWS.md
   ├─ OPERATIONS.md
   └─ COMPLIANCE.md
```

---

## 4. 核心领域模型与状态机

### 4.1 实体

- **Project**：一部影片。字段：id、name、description、status、created_at。
- **Script**：项目剧本/镜头表版本。字段：id、project_id、content_json、version。
- **Shot**：镜头。字段：id、project_id、scene_no、shot_no、description、dialogue、duration_sec、status、selected_keyframe_asset_id、selected_clip_asset_id。
- **Asset**：资产文件。字段：id、project_id、shot_id、type（keyframe/draft/refine/audio/final）、relative_path、mime、bytes、sha256、created_at。
- **GenerationJob**：生成任务。字段：id、project_id、shot_id、job_type（keyframe/draft/refine/audio/compose）、workflow_template、params_json、status、attempt、max_attempts、priority、data_class、assigned_agent、started_at、finished_at、error。
- **Review**：审核。字段：id、job_id/asset_id、decision（approve/reject/needs_retry）、reason、reviewer、created_at。
- **ResourceRecord**：资源记录。字段：id、job_id、gpu_minutes、wall_minutes、attempts、discarded_count、storage_bytes、api_calls、electricity_note。
- **ComplianceRecord**：合规。字段：id、asset_id、explicit_mark、metadata_json、watermark_id、created_at。
- **WorkflowTemplate**：工作流模板。字段：id、name、json_path、mapping_path、required_models_json、version。
- **ModelRegistry**：模型文件。字段：id、name、path、sha256、vae_name、notes。

### 4.2 状态机

**Project**：`draft → scripting → keyframing → drafting → refining → reviewing → composing → archived`（允许回退）。

**Shot**：`draft → keyframe_ready → draft_ready → refine_ready → approved / rejected`。

**Job**：`queued → running → succeeded / failed / cancelled`；失败可按 `attempt < max_attempts` 重新入队。

---

## 5. 数据库 DDL（核心表）

```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE scripts (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  content_json JSONB NOT NULL,
  version INT NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE shots (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  scene_no INT NOT NULL,
  shot_no INT NOT NULL,
  description TEXT NOT NULL,
  dialogue TEXT,
  duration_sec NUMERIC(6,2) NOT NULL DEFAULT 5,
  status TEXT NOT NULL DEFAULT 'draft',
  selected_keyframe_asset_id UUID,
  selected_clip_asset_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, scene_no, shot_no)
);

CREATE TABLE assets (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  shot_id UUID REFERENCES shots(id) ON DELETE SET NULL,
  type TEXT NOT NULL,
  relative_path TEXT NOT NULL,
  mime TEXT,
  bytes BIGINT,
  sha256 TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE generation_jobs (
  id UUID PRIMARY KEY,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  shot_id UUID REFERENCES shots(id) ON DELETE CASCADE,
  job_type TEXT NOT NULL,
  workflow_template TEXT NOT NULL,
  params_json JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  attempt INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  priority INT NOT NULL DEFAULT 100,
  data_class TEXT NOT NULL DEFAULT 'local_only',
  assigned_agent TEXT,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE reviews (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  decision TEXT NOT NULL,
  reason TEXT,
  reviewer TEXT NOT NULL DEFAULT 'owner',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resource_records (
  id UUID PRIMARY KEY,
  job_id UUID REFERENCES generation_jobs(id) ON DELETE CASCADE,
  gpu_minutes NUMERIC(10,2),
  wall_minutes NUMERIC(10,2),
  attempts INT,
  discarded_count INT DEFAULT 0,
  storage_bytes BIGINT,
  api_calls INT DEFAULT 0,
  electricity_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE compliance_records (
  id UUID PRIMARY KEY,
  asset_id UUID REFERENCES assets(id) ON DELETE CASCADE,
  explicit_mark BOOLEAN NOT NULL DEFAULT true,
  metadata_json JSONB NOT NULL,
  watermark_id TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE workflow_templates (
  id UUID PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  json_path TEXT NOT NULL,
  mapping_path TEXT NOT NULL,
  required_models_json JSONB,
  version TEXT NOT NULL
);

CREATE TABLE model_registry (
  id UUID PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT,
  vae_name TEXT,
  notes TEXT
);
```

---

## 6. API 规格（MVP）

统一前缀 `/api/v1`，认证 `X-API-Key`。所有错误返回 `{ "detail": "..." }`。

### 6.1 Projects
- `POST /projects`：创建项目。body：`{name, description}`。
- `GET /projects`：列表。
- `GET /projects/{id}`：详情，含 shots 统计。
- `PATCH /projects/{id}`：更新 status/name。

### 6.2 Scripts / Shots
- `POST /projects/{id}/scripts`：上传镜头表 JSON。body：`{content_json}`。
- `POST /projects/{id}/shots`：创建镜头。body：`{scene_no, shot_no, description, dialogue, duration_sec}`。
- `GET /projects/{id}/shots`：镜头列表。
- `PATCH /shots/{id}`：更新描述/状态/选中资产。

**镜头表 JSON 约定**：
```json
{
  "project_title": "demo",
  "shots": [
    {
      "scene_no": 1,
      "shot_no": 1,
      "description": "wide shot, rainy alley, neon light",
      "dialogue": "",
      "duration_sec": 5,
      "character_refs": ["char_lin"],
      "style_tags": ["cyberpunk", "cinematic"]
    }
  ]
}
```

### 6.3 Jobs
- `POST /jobs`：创建任务。body：
```json
{
  "project_id": "uuid",
  "shot_id": "uuid",
  "job_type": "keyframe|draft|refine|audio",
  "workflow_template": "keyframe_flux_ipadapter",
  "params": {
    "prompt": "...",
    "negative_prompt": "...",
    "seed": 123,
    "width": 1280,
    "height": 704,
    "frames": 121,
    "input_image_relative_path": "projects/.../keyframes/shot_001.png",
    "output_relative_path": "projects/.../drafts/shot_001_ltx.mp4"
  },
  "priority": 100,
  "data_class": "local_only",
  "max_attempts": 3
}
```
- `GET /jobs?status=queued&assigned_agent=...`：Agent 拉取。
- `POST /jobs/{id}/claim`：Agent 声明任务，返回完整 params。
- `POST /jobs/{id}/complete`：body `{status:"succeeded"|"failed", error?, asset?:{relative_path,type,bytes,sha256}, resource?:{...}}`。
- `POST /jobs/{id}/cancel`。
- `POST /jobs/{id}/retry`。

### 6.4 Assets / Reviews
- `GET /projects/{id}/assets?type=...`。
- `POST /assets/{id}/review`：body `{decision:"approve"|"reject"|"needs_retry", reason}`。
- `GET /projects/{id}/review-queue`。

### 6.5 Compose / Compliance
- `POST /projects/{id}/compose`：body `{shot_ids:[...], output_name, add_watermark:true, metadata:{...}}`。创建 compose job。
- `POST /assets/{id}/compliance-stamp`：对成片执行显式标识 + 元数据写入，写 ComplianceRecord。
- `GET /assets/{id}/compliance`。

### 6.6 Resources
- `GET /projects/{id}/resources`：汇总 gpu_minutes、attempts、discarded_count、storage_bytes。
- `POST /jobs/{id}/resource`：Agent 上报。

---

## 7. Render Agent 与 ComfyUI 集成

### 7.1 Agent 主循环
1. `GET /jobs?status=queued&assigned_agent=null` 拉任务（或轮询 central）。
2. `POST /jobs/{id}/claim`，拿到 workflow_template、params、mapping。
3. 校验模型：读 `model_registry`，可选校验 sha256；若缺失则任务失败并报错。
4. 调用 `workflow_inject.inject(template_json, params, mapping)`。
5. 上传输入图：`POST http://127.0.0.1:8188/upload/image`（multipart，name）。
6. 提交：`POST /prompt` body `{prompt: injected_json, client_id: agent_id}`，得到 `prompt_id`。
7. 轮询 `GET /history/{prompt_id}`，每 2s，超时 2h；同时读 ComfyUI `/queue` 判断是否卡死。
8. 成功后从 ComfyUI 输出目录复制/确认文件到 `output_relative_path`（NAS 挂载路径），计算 sha256、bytes。
9. `POST /jobs/{id}/complete` 上报 asset + resource（wall_minutes、gpu_minutes 可用 nvidia-smi 采样估算）。

### 7.2 参数注入映射

`workflows/mappings/wan5b_refine.mapping.json` 示例：
```json
{
  "template": "wan5b_refine",
  "mappings": [
    {"param": "prompt", "node_id": "6", "input": "text"},
    {"param": "negative_prompt", "node_id": "7", "input": "text"},
    {"param": "seed", "node_id": "3", "input": "seed"},
    {"param": "width", "node_id": "5", "input": "width"},
    {"param": "height", "node_id": "5", "input": "height"},
    {"param": "frames", "node_id": "5", "input": "length"},
    {"param": "input_image_relative_path", "node_id": "10", "input": "image"},
    {"param": "output_relative_path", "node_id": "20", "input": "filename_prefix"}
  ]
}
```
实现 `inject_params(workflow_json, params, mapping)`：按 node_id/input 写入；若 node 或 input 不存在，抛 `WorkflowMappingError`，任务失败并记录。

### 7.3 必要 ComfyUI 自定义节点（文档中列出，不自动安装）
- ComfyUI-Manager
- ComfyUI-IPAdapter-plus / FaceID
- ComfyUI-ControlNet-Aux
- ComfyUI-VideoHelperSuite
- 可选 RIFE / frame interpolation 节点
- 对应模型：FLUX/SDXL、IP-Adapter 权重、Wan 2.2 5B、LTX-Video 2B、VAE 按模板指定（Wan 14B 用 `wan_2.1_vae`，5B 用 `wan2.2_vae`，不可混用）。

---

## 8. Workflow 模板规格

| 模板 | 用途 | 输入 | 输出 | 备注 |
|---|---|---|---|---|
| `keyframe_flux_ipadapter` | 关键帧 | prompt、negative、seed、width/height、character_ref_images | PNG 到 `keyframes/` | IP-Adapter 锁定角色 |
| `ltx_draft` | 5 秒草稿 | prompt、seed、width/height、frames=121、input_keyframe | MP4 到 `drafts/` | 快速验证运镜/构图 |
| `wan5b_refine` | 精修 | prompt、seed、width=1280、height=704、frames=121、input_keyframe | MP4 到 `refines/` | MVP 主力精修 |
| `h3_audio_optional` | 音画同步 | prompt、input_image、duration | MP4 到 `audio_clips/` | Phase 1.5 可选 |
| `compose_ffmpeg` | 合成 | shot_ids、audio、subtitles、watermark | final MP4 | 由 worker 执行，非 ComfyUI |

**注意**：14B 只作为“个别镜头冲刺”，不在 MVP 默认流程；若 32GB 卡实测 14B 720p 稳定，再加 `wan14b_refine` 模板。

---

## 9. 存储与 NAS 约定

**挂载点**：工作站和 NAS 容器都使用 `/mnt/ai-media`。

**目录规范**：
```text
/mnt/ai-media/projects/{project_id}/
  script/            shot_table_v1.json
  keyframes/         shot_001.png
  drafts/            shot_001_ltx.mp4
  refines/           shot_001_wan5b.mp4
  audio/             voice.wav, bgm.mp3, subtitles.srt
  output/            final_v1.mp4, final_v1.metadata.json
  logs/              job_{id}.log
  resources/         resource_summary.json
```

**StorageAdapter 接口**：
```python
class StorageAdapter:
    def resolve(self, relative_path: str) -> Path: ...
    def ensure_project_dirs(self, project_id: str) -> None: ...
    def stat(self, relative_path: str) -> dict: ...
    def delete(self, relative_path: str) -> None: ...
```
MVP 实现 `LocalPathStorage(base="/mnt/ai-media")`；不实现对象存储。

**活跃/归档分层**：MVP 不自动迁移；文档写明“当前项目在 NVMe 池，归档后由人工/脚本迁移到 HDD 阵列”。可选脚本 `scripts/archive_project.sh`。

---

## 10. Web UI 功能（MVP）

页面：
1. **ProjectsPage**：项目列表、创建、状态。
2. **ProjectDetailPage**：项目概览、镜头表上传、镜头列表、资源汇总。
3. **ShotBoardPage**：按 scene 分组卡片；每镜头显示关键帧缩略图、草稿/精修视频、状态、按钮“生成关键帧/草稿/精修/通过/驳回/重试”。
4. **ReviewPage**：待审队列；视频播放器；通过/驳回/需重试 + reason。
5. **JobsPage**：任务列表、状态、attempt、错误、取消/重试。
6. **ComposePanel**：选择已通过镜头、排序、上传音频/字幕、生成成片、查看合规记录。

UI 要求：不做花哨动画；视频用 `<video controls>`；状态用颜色 badge；所有操作 optimistic update + 错误 toast。

---

## 11. 合成与合规

### 11.1 FFmpeg 合成
输入：按 `shot_ids` 顺序的已通过精修片段、可选音频、可选 SRT。输出：`output/final_v1.mp4`。

命令骨架：
```bash
ffmpeg -f concat -safe 0 -i concat.txt \
  -i voice.wav -i bgm.mp3 \
  -filter_complex "[0:v]drawtext=text='AI 生成':x=w-tw-24:y=h-th-24:fontsize=28:fontcolor=white@0.8:box=1:boxcolor=black@0.4[v]" \
  -map "[v]" -map 1:a? -map 2:a? \
  -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium \
  -metadata ai_generated="true" \
  -metadata ai_model="wan2.2-5b;ltx-video" \
  -metadata ai_generation_params="seed=...;prompt_hash=..." \
  -metadata ai_service="local-video-studio" \
  output/final_v1.mp4
```
字幕用 `subtitles=subtitles.srt` 滤镜；音频混合用 `amix`。

### 11.2 合规
- 显式标识：`drawtext` 画面右下角“AI 生成”，可配置文字/位置/透明度。
- 隐式标识：容器 metadata 写入 `ai_generated`、`ai_model`、`ai_generation_params`、`ai_service`、`created_at`。
- 水印：定义 `WatermarkProvider` 接口；MVP 用 metadata + 显式文字；可选接入不可见水印工具作为后处理。
- 每个成片写 `ComplianceRecord`，不可绕过：compose worker 成功前必须调用 `compliance.stamp()`。

---

## 12. 调度与云端（Phase 2，MVP 只留接口）

**MVP**：RQ + Redis，单工作站 Agent 轮询。不做夜间定时。

**Phase 2**：
- `scheduler` 服务：每天 23:00 读取 `night_queue` 表，将 `cloud_allowed` 任务派发到 `cloud_adapters`。
- `ViduAdapter`：错峰 API，按调用次数记录 `api_calls`；只允许 `data_class=cloud_allowed`。
- `CloudGPUAdapter`：租用云 4090，同步 workflow JSON + 轻量输入，拉回输出。
- 数据分级规则在 API 层强制：`local_only` 任务禁止进入 cloud adapter。

---

## 13. 资源预算与记录（替代财务成本核算）

不做“单部影片成本”，做**资源记录**：
- 每个 job 记录 `wall_minutes`、`gpu_minutes`（Agent 用 `nvidia-smi` 采样）、`attempts`、`discarded_count`、`storage_bytes`、`api_calls`。
- 项目汇总页显示：本片总硬件小时、废片比（生成条数/采用条数）、归档 GB。
- 可选字段 `electricity_note` 由用户手填，不自动算钱。

**UI 文案**：不写“成本”，写“资源消耗”。

---

## 14. 配置与环境变量

`.env.example`：
```env
APP_ENV=dev
API_KEY=change-me
DATABASE_URL=postgresql+psycopg://studio:studio@postgres:5432/studio
REDIS_URL=redis://redis:6379/0
STORAGE_BASE=/mnt/ai-media
COMFYUI_URL=http://127.0.0.1:8188
AGENT_ID=workstation-5090
AGENT_POLL_INTERVAL_SEC=5
JOB_TIMEOUT_SEC=7200
COMPLIANCE_TEXT=AI 生成
COMPLIANCE_POSITION=bottom-right
CLOUD_ENABLED=false
VIDU_API_KEY=
```

工作站 systemd 或 compose 环境同理；`STORAGE_BASE` 必须是 NAS 挂载路径。

---

## 15. Docker Compose 样例

**NAS `docker-compose.nas.yml`**：
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: studio
      POSTGRES_PASSWORD: studio
      POSTGRES_DB: studio
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7
  central-api:
    build: ./backend
    env_file: .env
    ports: ["8000:8000"]
    volumes: ["/mnt/ai-media:/mnt/ai-media"]
    depends_on: [postgres, redis]
  web:
    build: ./web
    ports: ["3000:80"]
    environment: [VITE_API_BASE=http://central-api:8000]
  worker-light:
    build: ./backend
    command: python -m app.workers.compose_worker
    env_file: .env
    volumes: ["/mnt/ai-media:/mnt/ai-media"]
volumes:
  pgdata:
```

**工作站 `docker-compose.workstation.yml`**：
```yaml
services:
  render-agent:
    build: ./render-agent
    env_file: .env
    network_mode: host
    volumes:
      - /mnt/ai-media:/mnt/ai-media
      - ./workflows:/app/workflows:ro
    restart: unless-stopped
```
ComfyUI 独立运行，不在 compose 内；Agent 通过 `COMFYUI_URL` 访问。

---

## 16. 开发里程碑与任务拆分（给 Cursor 的顺序）

**M0 — 仓库骨架（0.5 天）**
- 建目录、README、PROJECT_SPEC.md、.env.example、docker-compose 文件。
- 后端 FastAPI 健康检查 `/health`。
- 前端 Vite 空页面。
- **验收**：`docker compose up` 后 `/health` 返回 ok，前端可打开。

**M1 — 项目/镜头/镜头表 CRUD（1–2 天）**
- SQLAlchemy models + Alembic 初始迁移。
- Projects/Shots API + 镜头表 JSON 导入。
- 前端 ProjectsPage、ProjectDetailPage、ShotBoardPage 只读列表。
- **验收**：创建项目、导入 3 镜头、列表展示。

**M2 — Render Agent + Mock ComfyUI（2–3 天）**
- 实现 `comfy_client.py`、`workflow_inject.py`、Agent claim/complete。
- 写 `tests/mock_comfyui.py`：模拟 `/prompt`、`/history`、`/upload/image`，返回假视频文件。
- 前端 JobsPage 展示任务状态。
- **验收**：创建一个 keyframe job，Agent 领取，mock 返回成功，Asset 入库。

**M3 — 真实 ComfyUI 接入（2–4 天，依赖环境）**
- 导入 `keyframe_flux_ipadapter.json` 和 `ltx_draft.json`，配置 mapping。
- 工作站实跑：关键帧 → LTX 草稿 → 视频落盘到 NAS。
- 记录 wall_minutes/gpu_minutes。
- **验收**：从 ShotBoard 点击“生成草稿”，真实产出 5 秒 MP4，状态变 `draft_ready`。

**M4 — 精修 + 审核 UI（2–3 天）**
- 接入 `wan5b_refine.json`。
- ReviewPage：播放、通过/驳回/重试；Review API。
- Shot 状态机联动：approve 后 `approved`，可进入 compose。
- **验收**：一条镜头走完 keyframe→draft→refine→approve。

**M5 — 合成 + 合规（1–2 天）**
- `ffmpeg_compose.py`：concat、音频、字幕、drawtext、metadata。
- ComplianceRecord 写入；compose 成功前强制 stamp。
- **验收**：3 个已通过镜头合成 15 秒成片，画面有“AI 生成”，metadata 可读。

**M6 — NAS 归档与资源汇总（1 天）**
- StorageAdapter 固定 `/mnt/ai-media`；项目目录自动创建。
- 资源汇总 API + UI。
- **验收**：成片在 NAS 目录可见，资源页显示硬件分钟/废片比/GB。

**M7 — Phase 2 可选**
- 夜间队列、Vidu/CloudGPU adapter stub、n8n 对接。**MVP 不实现**。

---

## 17. 测试策略与验收标准

**单元测试**：
- `workflow_inject`：正确注入、缺 node 抛错。
- `comfy_client`：mock `/prompt` 重试、超时。
- `ffmpeg_compose`：生成 concat 文件、metadata 参数。
- `compliance`：显式标识必选、metadata 必写。

**集成测试**：
- 用 mock ComfyUI 跑完整 job 生命周期。
- SQLite 内存库跑 API CRUD。

**E2E（手动）**：
1. 创建项目 `demo`。
2. 导入 3 镜头镜头表。
3. 每镜头：生成关键帧 → 草稿 → 精修 → 通过。
4. Compose 成片，检查水印/metadata。
5. 检查 NAS 目录和资源汇总。

**MVP 验收标准**：
- 单镜头从“点击生成”到“视频出现在 ShotBoard”无需手工命令行。
- 任务失败有错误信息、可重试、attempt 上限生效。
- 成片 100% 带显式标识和 metadata。
- 所有输出路径在 `/mnt/ai-media/projects/{id}/` 下。
- 资源记录包含 wall_minutes、attempts、discarded_count。

---

## 18. 给 Cursor 的首条指令（可直接粘贴）

```text
You are implementing the project described in PROJECT_SPEC.md.

Rules:
1. Read PROJECT_SPEC.md fully before coding.
2. Implement milestones in order: M0 -> M1 -> M2. Do not implement M3+ until M2 tests pass.
3. Use FastAPI + SQLAlchemy 2 + Pydantic v2 + PostgreSQL (SQLite allowed in tests).
4. For M2, create a mock ComfyUI server in tests/mock_comfyui.py and make all integration tests use it. Do not require a real ComfyUI instance for CI.
5. Every API change must update docs/API.md and add/adjust tests.
6. Keep storage paths relative to STORAGE_BASE; never hardcode absolute paths.
7. Do not implement cloud adapters, n8n, or night scheduler in M0-M2. Leave typed stubs only.
8. After each milestone, output: files changed, how to run tests, and a manual verification checklist.
9. If a requirement is ambiguous, ask one concise question before coding; otherwise choose the simplest implementation consistent with the spec.
10. Start with M0: create repo skeleton, health endpoint, compose files, and README. Then stop and report.
```

---

## 19. 风险与待确认项（写进 README 的“Known Risks”）

1. **32GB 初版 5090D 的货源与保修**：开箱必须 GPU-Z 验证；保修可能换 D v2。
2. **Wan 14B 在 32GB 上的稳定性**：MVP 不默认使用；先测 5B。
3. **ComfyUI 节点/模型版本漂移**：workflow JSON 必须记录版本和模型哈希；模板不可随意替换 VAE。
4. **NAS 小文件元数据瓶颈**：活跃项目放 NVMe 池，HDD 只归档；MVP 不自动迁移。
5. **合规标识不可绕过**：compose worker 必须在成功前写 ComplianceRecord。
6. **云端默认关闭**：`CLOUD_ENABLED=false`；任何 cloud adapter 对 `local_only` 任务必须拒绝。

---

这份规格可以直接作为 Cursor 的 `PROJECT_SPEC.md`。建议你先让 Cursor 只做 **M0 + M1 + M2（mock ComfyUI）**，等任务状态机和审核 UI 跑通后，再让它接真实 ComfyUI。这样即使真实模型环境出问题，平台骨架和测试仍然可运行。

---

## Appendix A — Linkin monorepo 映射（落地說明）

本規格原文假設獨立倉庫；落地 [iiooiioo888/Linkin](https://github.com/iiooiioo888/Linkin) 時映射為：

- `PROJECT_SPEC.md` → 倉庫根目錄
- 後端 → `backend/local_video_studio/`（FastAPI router 註冊進 `backend.main`）
- 前端 → `frontend/src/modules/local-video-studio/` → `#/modules/local-video-studio`
- Compose → `docker-compose.local-video-studio.yml`（不破壞現有 `docker-compose.yml` 預設）
- 整合捷徑 → `docs/integrations/local-video-studio.md`
- `render-agent/`、`workflows/` → 可放倉庫根或 `backend/local_video_studio/` 旁（M1+）
