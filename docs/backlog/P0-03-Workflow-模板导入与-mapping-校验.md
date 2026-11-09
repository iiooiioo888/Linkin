# P0-03 — Workflow 模板导入与 mapping 校验

| Field | Value |
|---|---|
| **Title** | P0-Workflow 模板导入与 mapping 校验 |
| **Priority** | P0 |
| **Status** | **partial** — core inject/validate in [#167](https://github.com/iiooiioo888/Linkin/pull/167)；runtime import／version DB still **gap** |
| **Source** | FEATURES_AND_TOOLS.md §4 item 3 · §1 工作流模板 |

## Acceptance criteria（§1）

- [x] 仓内 ComfyUI API 格式 JSON 模板（keyframe／ltx／wan5b）
- [x] 参数 mapping 文件；缺 node 时 job／inject 失败并给出明确错误
- [ ] 运行时「导入」API（上传模板 JSON）
- [ ] 模板版本记录（DB）

## Remaining gap

1. `POST` 导入 workflow＋mapping，写入 `workflows/` 或 DB blob  
2. 版本字段／历史；任务绑定具体版本  
3. 文档：`docs/WORKFLOWS.md`（§5 要求；目前仅 OPERATIONS.md）

## Tests + docs DoD

- [x] `test_workflow_inject_*` · `test_m3_workflow_templates_and_mappings_exist`
- [ ] 导入 API 的验收测试
- [ ] `docs/WORKFLOWS.md`

## Tools（§2–3）

| 功能 | 主工具 | 不要用 |
|---|---|---|
| 参数注入 | mapping JSON + Python（`workflow_inject.py`） | 硬编码 node_id |
| 工作流执行 | ComfyUI HTTP API | 自己写推理后端 |
| 版本控制 | Git（工作流必须进仓库） | — |
