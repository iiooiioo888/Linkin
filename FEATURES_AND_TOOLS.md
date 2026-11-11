# FEATURES_AND_TOOLS.md — 功能矩阵与工具选型

## 0. 两个原则

1. **功能是“平台必须能做到的事”，工具是“用什么来做”。** 同一个功能可以换工具实现，功能验收标准不应绑定具体工具。
2. **MVP 只做 P0；P1 留接口；P2 只写文档不实现。** 任何工具如果不在 P0 功能链路里，默认不装、不接、不配置。

---

## 1. 平台功能清单（按优先级）

### P0 — MVP 必须有的功能

| 模块 | 功能 | 验收标准 |
|---|---|---|
| **项目管理** | 创建/编辑/列出项目；项目状态机；项目目录自动创建 | 创建项目后 `/mnt/ai-media/projects/{id}/` 下六个子目录存在 |
| **镜头表** | 导入 JSON 镜头表；手动增删改镜头；场景/镜头编号唯一 | 导入 3 镜头后 ShotBoard 按 scene 分组显示 |
| **镜头板** | 每个镜头显示关键帧缩略图、草稿/精修视频、状态、操作按钮 | 点击“生成草稿”能创建 job，状态实时变化 |
| **任务队列** | 创建/领取/完成/失败/取消/重试 job；attempt 上限；优先级 | 失败 job 可重试，超过 max_attempts 变 failed 且不可自动重试 |
| **工作流模板** | 导入 ComfyUI API 格式 JSON；参数映射文件；模板版本记录 | mapping 缺 node 时 job 失败并给出明确错误 |
| **模型注册** | 记录模型名、路径、sha256、VAE 名；任务执行前校验模型存在 | 缺模型时 job 失败，错误信息包含缺失模型名 |
| **Render Agent** | 轮询 central、claim job、注入参数、提交 ComfyUI、轮询 history、上报 asset/resource | 用 mock ComfyUI 跑通完整 job 生命周期 |
| **真实 ComfyUI 接入** | 关键帧、LTX 草稿、Wan 5B 精修三条工作流可真实执行 | 从 UI 点击到 MP4 落盘 NAS，无需命令行 |
| **审核** | 待审队列；通过/驳回/需重试 + reason；审核记录 | 驳回后镜头状态回退，可重新生成 |
| **合成** | 按顺序拼接已通过镜头；混音；烧字幕；输出 MP4 | 3 个镜头合成 15 秒成片，ffprobe 可读 |
| **合规标识** | 显式“AI 生成”文字；容器 metadata；ComplianceRecord 不可绕过 | 成片 100% 带文字标识和 `ai_generated=true` metadata |
| **存储约定** | 所有输出路径在 `projects/{id}/` 下；相对路径入库；sha256 记录 | 数据库无绝对路径；文件可在 NAS 直接找到 |
| **资源记录** | 记录 wall_minutes、gpu_minutes、attempts、discarded_count、storage_bytes | 项目详情页显示本片硬件小时/废片比/GB |
| **任务日志** | 每个 job 独立日志文件；UI 可查看错误摘要 | 失败 job 在 JobsPage 能看到错误原因 |
| **API 文档** | OpenAPI 自动生成；`docs/API.md` 与实现同步 | `/docs` 可打开，示例请求可复制 |

### P1 — MVP 跑通后再加

| 模块 | 功能 | 说明 |
|---|---|---|
| **角色/风格资产库** | 角色参考图集合、风格标签、按标签检索历史资产 | 先做简单标签 + 文件引用，不做向量检索 |
| **提示词模板** | 可复用提示词片段、negative 模板、变量注入 | 存 DB，不做复杂版本树 |
| **多 seed 对比** | 同一镜头生成多个候选，并排播放选择 | 先做 2–4 个候选，不做无限网格 |
| **自动初审** | VLM 检查角色一致性/明显畸变，标记可疑镜头 | 只做“建议”，不自动通过 |
| **批量任务** | 按镜头表批量创建草稿/精修 job | 先做手动触发，不做定时 |
| **夜间队列** | 23:00 读取 night_queue，派发 `cloud_allowed` 任务 | 默认关闭，开关在配置 |
| **云端适配器** | Vidu 错峰 API、云 GPU 租赁适配器 | 只允许 `data_class=cloud_allowed`；MVP 只留 stub |
| **归档迁移** | 活跃项目从 NVMe 池迁移到 HDD 归档 | 脚本 + 人工确认，不自动删源 |
| **通知** | 任务失败 webhook/邮件 | 先做 webhook，不做复杂通知中心 |
| **容量看板** | NAS 剩余空间、项目占用、增长趋势 | 读 `df` + DB 汇总，不接 Prometheus |
| **导出包** | 成片 + 字幕 + metadata + 封面帧打包 ZIP | 方便交付或备份 |
| **搜索** | 按项目名/角色/标签/状态/日期搜索 | Postgres full-text 或简单 LIKE 即可 |

### P2 — 明确不做，只写文档

- 多租户 / 用户注册 / 复杂 RBAC（MVP 只有 API Key + owner）
- 支付、分账、投流、自动发布到平台
- 全自动无人审核成片
- Kubernetes / 多机 GPU 集群调度
- 对象存储（S3/MinIO）后端
- 向量数据库 / 语义检索
- 移动端 App
- 实时协作编辑
- 自动安装 ComfyUI 自定义节点
- 真实云端计费对账

---

## 2. 工具选型清单

### 2.1 必须安装（P0）

| 类别 | 工具 | 用途 | 备注 |
|---|---|---|---|
| 后端框架 | **FastAPI** | API 服务 | Pydantic v2 |
| ORM/迁移 | **SQLAlchemy 2 + Alembic** | 数据模型与迁移 | 测试可用 SQLite |
| 数据库 | **PostgreSQL 16** | 主数据库 | 开发可 SQLite |
| 队列 | **Redis + RQ** | job 队列 | 比 Celery 简单，MVP 够用 |
| 后端测试 | **pytest + httpx** | 单元/集成测试 | 必须含 mock ComfyUI |
| 日志 | **structlog** | JSON 结构化日志 | 每 job 写文件 |
| 前端 | **React + Vite + TypeScript** | Web UI | Tailwind CSS |
| 数据请求 | **TanStack Query** | 缓存/轮询 job 状态 | OpenAPI 生成 client |
| 媒体处理 | **FFmpeg + ffprobe** | 合成、转码、校验、drawtext、metadata | 核心工具，必须固定版本 |
| 图像处理 | **ImageMagick** | 缩略图、封面帧 | 可选但推荐 |
| 元数据 | **exiftool** | 检查/写入容器元数据 | 合规校验用 |
| 容器 | **Docker Compose** | NAS 服务编排 | 工作站可用 systemd |
| 存储 | **TrueNAS / ZFS** | NAS 文件系统、快照 | 已有 |
| GPU 监控 | **nvidia-smi** | Agent 采样 gpu_minutes | 不装额外 exporter |
| 版本控制 | **Git** | 代码与工作流 JSON | 工作流必须进仓库 |

### 2.2 ComfyUI 侧（手动安装，不由平台自动装）

| 工具/节点 | 用途 | 备注 |
|---|---|---|
| **ComfyUI** | 渲染执行引擎 | 独立运行，Agent 通过 HTTP 访问 |
| **ComfyUI-Manager** | 节点管理 | 人工使用，平台不调用 |
| **ComfyUI-VideoHelperSuite** | 视频输入/输出 | 草稿/精修输出常用 |
| **ComfyUI-IPAdapter-plus / FaceID** | 角色锁定 | 关键帧阶段 |
| **ComfyUI-ControlNet-Aux** | 姿态/空间控制 | 按需 |
| **RIFE / 帧插值节点** | 可选后处理 | P1 |
| **模型文件** | FLUX/SDXL、IP-Adapter、Wan 2.2 5B、LTX-Video 2B、对应 VAE | 必须记录 sha256；Wan 14B 用 `wan_2.1_vae`，5B 用 `wan2.2_vae`，不可混用 |

### 2.3 推荐但可延后（P1）

| 类别 | 工具 | 用途 | 何时引入 |
|---|---|---|---|
| 本地 LLM | **Ollama**（Qwen 小参数 GGUF） | 剧本拆分镜、提示词优化 | 手动拆镜头嫌慢时 |
| 自动化 | **n8n** | 夜间队列、跨服务编排 | 手动夜间队列稳定后 |
| 备份 | **restic / borg** | 加密增量备份 | NAS 有重要项目后 |
| 同步 | **rsync / rclone** | 归档迁移、异机备份 | 需要冷备份时 |
| 监控 | **Uptime Kuma** | 服务存活告警 | 平台开始每天用之后 |
| 监控 | **Prometheus + Grafana** | 细粒度指标 | 多机/多 Agent 才需要 |
| 远程访问 | **Tailscale / WireGuard** | 内网安全访问 | 需要工作站外访问时 |
| 反向代理 | **Caddy / Nginx** | HTTPS、内网域名 | 多设备访问 UI 时 |
| 水印 | 不可见水印工具（按合规要求选型） | 隐式标识增强 | 有对外交付需求时 |

### 2.4 明确不引入（MVP）

- Celery（RQ 够用，避免复杂度）
- Kubernetes / Nomad
- MinIO / S3 对象存储
- 向量数据库（Chroma/Weaviate/Qdrant）
- 复杂 RBAC / OAuth / 多租户框架
- 自动节点安装器
- 自动投流/发布 SDK
- 财务计费系统

---

## 3. 功能与工具的对应关系（避免错配）

| 功能 | 主工具 | 备用/可替换 | 不要用 |
|---|---|---|---|
| 任务队列 | RQ + Redis | APScheduler（定时） | Celery（MVP 过重） |
| 工作流执行 | ComfyUI HTTP API | 本地 CLI（调试用） | 自己写推理后端 |
| 参数注入 | mapping JSON + Python | Jinja 模板 | 硬编码 node_id |
| 合成 | FFmpeg | MoviePy（不推荐） | 手工剪辑软件做批处理 |
| 合规标识 | FFmpeg drawtext + metadata | exiftool 后处理 | 事后手动加标 |
| 存储索引 | PostgreSQL + 相对路径 | SQLite FTS | 只靠文件夹命名 |
| 资源记录 | DB + nvidia-smi 采样 | 手填 CSV | 自动电费计算（MVP 不做） |
| 备份 | ZFS snapshot + restic | rsync 冷备 | RAID 当备份 |
| 前端状态 | TanStack Query 轮询 | WebSocket（P1） | 全局 setInterval 散落 |

---

## 4. 建议的仓库 backlog 顺序（给 Cursor）

按功能优先级拆 issue，建议顺序：

1. `P0-项目管理与镜头表 CRUD`
2. `P0-任务队列与 Job 状态机`
3. `P0-Workflow 模板导入与 mapping 校验`
4. `P0-Mock ComfyUI 与 Render Agent 闭环`
5. `P0-真实关键帧工作流接入`
6. `P0-LTX 草稿工作流接入`
7. `P0-Wan 5B 精修工作流接入`
8. `P0-审核队列与镜头状态联动`
9. `P0-FFmpeg 合成与合规标识`
10. `P0-资源记录与项目汇总`
11. `P1-角色/风格资产库`
12. `P1-多 seed 对比`
13. `P1-批量任务与夜间队列`
14. `P1-云端适配器 stub`
15. `P1-归档迁移与备份脚本`

每个 issue 的完成定义：**功能验收标准 + 对应测试 + 文档更新**。没有测试和文档的 issue 不算完成。

---

## 5. 给 Cursor 的追加指令（可粘贴）

```text
Read PROJECT_SPEC.md and FEATURES_AND_TOOLS.md.

Rules:
1. FEATURES_AND_TOOLS.md is the source of truth for scope. Do not implement P2 features.
2. P0 features only for now. P1 features must be left as typed stubs or TODO comments with interface definitions.
3. Tools listed under "明确不引入" must not be added to dependencies.
4. Every P0 feature must have an acceptance test. If a feature cannot be tested without real ComfyUI, test it against tests/mock_comfyui.py.
5. Do not auto-install ComfyUI custom nodes. Only document required nodes in docs/WORKFLOWS.md.
6. Keep FFmpeg command construction in one module (services/ffmpeg_compose.py) and test the generated command args, not the actual encoding.
7. When creating issues or commits, prefix with P0/P1 and reference the feature name from the table.
8. Start by generating the issue backlog from section 4 as GitHub-style markdown issues under docs/backlog/, then implement P0 issues in order.
```

---

这份清单的边界很明确：**P0 是“能跑通一部短片”的最小功能集，P1 是“跑得更顺”的增强，P2 是“现在不做”的诱惑清单。** 工具选型的核心不是“哪个最强”，而是“每个 P0 功能都有且只有一个主工具，并且这个工具可以被替换而不影响功能验收”。
