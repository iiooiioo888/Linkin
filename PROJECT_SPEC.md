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
│  │  │  ├─ storage.py
│  │  │  ├─ workflow_inject.py
│  │  │  ├─ comfy_client.py
│  │  │  ├─ ffmpeg_compose.py
│  │  │  ├─ compliance.py
│  │  │  ├─ resource_meter.py
│  │  │  └─ cloud_adapters/
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

**Linkin 整合说明**：本规格在独立仓库时用上表；落地 Linkin monorepo 时映射为：
- `PROJECT_SPEC.md` 放仓库根目录
- 后端 `backend/local_video_studio/`（FastAPI router 注册进 `backend.main`）
- 前端 `frontend/src/modules/local-video-studio/` → `#/modules/local-video-studio`
- `docker-compose.local-video-studio.yml`（不破坏现有 compose 默认）
- `render-agent/`、`workflows/` 可放仓库根或 `backend/local_video_studio/` 旁

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

在 Linkin 内可用前缀 `/local-video-studio/api/v1` 以免与主 API 冲突。

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
- `POST /jobs`：创建任务。
- `GET /jobs?status=queued&assigned_agent=...`：Agent 拉取。
- `POST /jobs/{id}/claim`：Agent 声明任务。
- `POST /jobs/{id}/complete`：body `{status:"succeeded"|"failed", error?, asset?, resource?}`。
- `POST /jobs/{id}/cancel`。
- `POST /jobs/{id}/retry`。

### 6.4 Assets / Reviews
- `GET /projects/{id}/assets?type=...`。
- `POST /assets/{id}/review`：body `{decision:"approve"|"reject"|"needs_retry", reason}`。
- `GET /projects/{id}/review-queue`。

### 6.5 Compose / Compliance
- `POST /projects/{id}/compose`。
- `POST /assets/{id}/compliance-stamp`。
- `GET /assets/{id}/compliance`。

### 6.6 Resources
- `GET /projects/{id}/resources`。
- `POST /jobs/{id}/resource`。

---

## 7. Render Agent 与 ComfyUI 集成

### 7.1 Agent 主循环
1. 拉 queued 任务 → claim。
2. 校验 model_registry。
3. `workflow_inject.inject`。
4. 上传输入图到 ComfyUI `/upload/image`。
5. `POST /prompt` → 轮询 `/history/{prompt_id}`。
6. 输出落到 NAS `output_relative_path`，计算 sha256。
7. `complete` 上报 asset + resource。

### 7.2 参数注入映射
实现 `inject_params(workflow_json, params, mapping)`；缺 node/input 抛 `WorkflowMappingError`。

### 7.3 必要 ComfyUI 自定义节点（文档列出，不自动安装）
- ComfyUI-Manager、IPAdapter-plus/FaceID、ControlNet-Aux、VideoHelperSuite、可选 RIFE。
- 模型：FLUX/SDXL、IP-Adapter、Wan 2.2 5B、LTX-Video 2B；VAE 不可混用。

---

## 8. Workflow 模板规格

| 模板 | 用途 | 备注 |
|---|---|---|
| `keyframe_flux_ipadapter` | 关键帧 | IP-Adapter 锁角色 |
| `ltx_draft` | 5 秒草稿 | 快速验证 |
| `wan5b_refine` | 精修 | MVP 主力 |
| `h3_audio_optional` | 音画同步 | Phase 1.5 |
| `compose_ffmpeg` | 合成 | worker，非 ComfyUI |

14B 非 MVP 默认。

---

## 9. 存储与 NAS 约定

挂载点：`/mnt/ai-media`。

```text
/mnt/ai-media/projects/{project_id}/
  script/ keyframes/ drafts/ refines/ audio/ output/ logs/ resources/
```

`StorageAdapter`：`resolve` / `ensure_project_dirs` / `stat` / `delete`；MVP `LocalPathStorage(base=STORAGE_BASE)`。

---

## 10. Web UI 功能（MVP）

ProjectsPage、ProjectDetailPage、ShotBoardPage、ReviewPage、JobsPage、ComposePanel。  
无花哨动画；`<video controls>`；badge；optimistic + toast。

---

## 11. 合成与合规

FFmpeg concat + 音频 + 字幕 + drawtext「AI 生成」+ metadata。  
`ComplianceRecord` 必写；compose 成功前强制 `compliance.stamp()`。

---

## 12. 调度与云端（Phase 2）

MVP：RQ + Redis，Agent 轮询。`CLOUD_ENABLED=false`。云端仅 stub。

---

## 13. 资源预算与记录

记录 wall_minutes、gpu_minutes、attempts、discarded_count、storage_bytes、api_calls。  
UI 写「资源消耗」不写「成本」。

---

## 14. 配置与环境变量

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

---

## 15. Docker Compose 样例

见规格：`docker-compose.nas.yml`、`docker-compose.workstation.yml`。  
Linkin：使用 `docker-compose.local-video-studio.yml`，ComfyUI 独立运行。

---

## 16. 开发里程碑与任务拆分（给 Cursor 的顺序）

- **M0 — 仓库骨架**：目录、README、PROJECT_SPEC.md、.env.example、docker-compose；FastAPI health；前端空页。验收：health 返回 ok，前端可打开。
- **M1 — 项目/镜头/镜头表 CRUD**：SQLAlchemy models + Alembic；Projects/Shots API + 镜头表 JSON 导入；前端 Projects／Detail／ShotBoard 只读列表。验收：创建项目、导入 3 镜头、列表展示。
- **M2 — Render Agent + Mock ComfyUI**：`comfy_client`、`workflow_inject`、Agent claim/complete；`tests/mock_comfyui.py`；JobsPage。验收：keyframe job 经 mock 成功入库。
- **M3 — 真实 ComfyUI 接入**（依赖环境）：导入 workflow JSON + mapping；工作站实跑关键帧→LTX 草稿；记录 wall/gpu minutes。验收：ShotBoard「生成草稿」产出 MP4，`draft_ready`。
- **M4 — 精修 + 审核 UI**：`wan5b_refine`；ReviewPage 播放／通过／驳回／重试；状态机联动。验收：一条镜头走完 keyframe→draft→refine→approve。
- **M5 — 合成 + 合规**：`ffmpeg_compose`（concat／音频／字幕／drawtext／metadata）；ComplianceRecord；compose 前强制 stamp。验收：成片带「AI 生成」标识与 metadata。
- **M6 — NAS 归档与资源汇总**：StorageAdapter 固定 `STORAGE_BASE`；资源汇总 API + UI。验收：成片在 NAS 可见，资源页有硬件分钟／废片比／GB。
- **M7 — Phase 2 可选**：夜间队列、Vidu／CloudGPU adapter stub、n8n。**MVP 不实现**。

本 PR **只做 M0**，然后停止并回报。

---

## 17. 测试策略

单元：workflow_inject、comfy_client mock、ffmpeg、compliance。  
集成：mock ComfyUI 全生命周期；测试可用 SQLite。  
MVP 验收：单镜头闭环无需手工命令行；失败可重试；成片 100% 带标识；输出在 `STORAGE_BASE/projects/{id}/`；资源记录含 wall_minutes／attempts／discarded_count。

---

## 18. 给 Cursor 的首条指令

1. Read PROJECT_SPEC.md fully before coding.
2. Implement milestones in order: M0 → M1 → M2；M3+ 需人工确认 GPU／ComfyUI 环境。
3. FastAPI + SQLAlchemy 2 + Pydantic v2；测试可用 SQLite。
4. M2 必须有 mock ComfyUI，CI 不依赖真机。
5. 路径相对 STORAGE_BASE。
6. 不实现 cloud/n8n/night scheduler（仅 stub）。
7. **Start with M0 only, then stop and report.**

---

## 19. Known Risks

1. 5090D 32GB 货源与保修；开箱 GPU-Z 验证。
2. Wan 14B 稳定性；MVP 用 5B。
3. ComfyUI 节点/模型版本漂移。
4. NAS 小文件瓶颈；活跃在 NVMe。
5. 合规不可绕过。
6. 云端默认关闭。
