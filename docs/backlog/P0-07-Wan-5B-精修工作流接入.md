# P0-07 — Wan 5B 精修工作流接入

| Field | Value |
|---|---|
| **Title** | P0-Wan 5B 精修工作流接入 |
| **Priority** | P0 |
| **Status** | **done*** — [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M4)；real GPU = ops |
| **Source** | FEATURES_AND_TOOLS.md §4 item 7 |

## Acceptance criteria（§1）

- [x] `wan5b_refine` workflow + mapping
- [x] UI 精修按钮 → job → Review 链路
- [ ]* 真机 Wan 5B → refines/ 落盘（VAE：`wan2.2_vae`，不可与 14B 混用）

## Tests + docs DoD

- [x] M3–M6 测试含 refine／review 路径
- [x] OPERATIONS.md 模型注意事项

## Tools（§2–3）

| 工具 | 用途 |
|---|---|
| ComfyUI + Wan 2.2 5B | 精修 |
| sha256 模型登记（P0-11 gap） | 执行前校验 |
