# P0-06 — LTX 草稿工作流接入

| Field | Value |
|---|---|
| **Title** | P0-LTX 草稿工作流接入 |
| **Priority** | P0 |
| **Status** | **done*** — [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M3)；real GPU = ops |
| **Source** | FEATURES_AND_TOOLS.md §4 item 6 |

## Acceptance criteria（§1）

- [x] `ltx_draft` workflow + mapping
- [x] UI「生成草稿」创建 job，状态实时变化（TanStack Query 轮询）
- [ ]* 真机 LTX → drafts/ 落盘

## Tests + docs DoD

- [x] M3 模板存在／inject 测试
- [x] OPERATIONS.md

## Tools（§2–3）

| 工具 | 用途 |
|---|---|
| ComfyUI + LTX-Video 2B（手动） | 草稿渲染 |
| VideoHelperSuite | 视频 I/O |
| FFmpeg／ffprobe | 后续校验（合成阶段） |
