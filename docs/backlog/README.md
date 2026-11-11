# Local Video Studio — FEATURES_AND_TOOLS backlog

Source of truth: root [`FEATURES_AND_TOOLS.md`](../../FEATURES_AND_TOOLS.md) §4.  
Spec: [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md).  
Merged baseline: [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M0–M6 MVP + §10 Web UI).

Each file is a GitHub-style markdown issue. **DoD**：§1 验收标准 + 对应测试 + 文档更新。

## Status vs #167

| ID | Issue | Status | Notes |
|---|---|---|---|
| P0-01 | 项目管理与镜头表 CRUD | **done** (#167) | projects／scripts／shots；六子目录 `ensure_project_dirs` |
| P0-02 | 任务队列与 Job 状态机 | **done** (#167) | claim／complete／cancel／retry／max_attempts；DB 队列（非 Redis+RQ，可接受） |
| P0-03 | Workflow 模板导入与 mapping 校验 | **partial** | 仓内 JSON＋`inject_params`；缺运行时导入 API／模板版本表 |
| P0-04 | Mock ComfyUI 与 Render Agent 闭环 | **done** (#167) | `mock_comfyui` + `agent/poller` |
| P0-05 | 真实关键帧工作流接入 | **done*** (#167) | `keyframe_flux_ipadapter`；CI mock；真机见 OPERATIONS.md |
| P0-06 | LTX 草稿工作流接入 | **done*** (#167) | `ltx_draft`；同上 |
| P0-07 | Wan 5B 精修工作流接入 | **done*** (#167) | `wan5b_refine`；同上 |
| P0-08 | 审核队列与镜头状态联动 | **done** (#167) | Review API／UI；approve／reject／needs_retry |
| P0-09 | FFmpeg 合成与合规标识 | **done** (#167) | `ffmpeg_compose`＋强制 `compliance.stamp` |
| P0-10 | 资源记录与项目汇总 | **done** (#167) | resources API／ResourcesPage／archive 脚本 |
| P0-11 | 模型注册与执行前校验 | **gap** | §1 有、§4 未编号；尚无 ModelRegistry |
| P0-12 | 任务日志文件与 UI 摘要 | **partial** | `error` 字段＋JobsPage；缺每 job 独立日志文件 |
| P0-13 | API 文档同步（`/docs` + `docs/API.md`） | **partial** | FastAPI `/docs` 可用；缺 `docs/API.md` |
| P1-01 | 角色/风格资产库 | open | |
| P1-02 | 多 seed 对比 | open | |
| P1-03 | 批量任务与夜间队列 | open | |
| P1-04 | 云端适配器 stub | **stub done** (#167) | Vidu／CloudGPU stubs；真实调用仍 open |
| P1-05 | 归档迁移与备份脚本 | **partial** | `scripts/archive_project.sh` 有；restic／冷备仍 open |

\*「done*」= 代码路径与模板已合入；真实 GPU／NAS 落盘属运维验收，不阻塞 docs backlog。

## Remaining P0 gaps (implement later)

1. P0-03 — workflow 导入 API／版本记录  
2. P0-11 — 模型注册表 + job 前校验  
3. P0-12 — 每 job 写 `projects/{id}/logs/` 文件  
4. P0-13 — 补 `docs/API.md`（与 OpenAPI 对齐）
