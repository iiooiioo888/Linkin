# P0-04 — Mock ComfyUI 与 Render Agent 闭环

| Field | Value |
|---|---|
| **Title** | P0-Mock ComfyUI 与 Render Agent 闭环 |
| **Priority** | P0 |
| **Status** | **done** — satisfied by [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M2) |
| **Source** | FEATURES_AND_TOOLS.md §4 item 4 · §1 Render Agent |

## Acceptance criteria（§1）

- [x] 轮询 central、claim job、注入参数、提交 ComfyUI、轮询 history、上报 asset/resource
- [x] 用 mock ComfyUI 跑通完整 job 生命周期

## Tests + docs DoD

- [x] `backend/tests/test_local_video_studio_m2.py`
- [x] CI 默认 mock（`LVS_USE_MOCK_COMFY`／未设 `COMFYUI_URL`）

## Tools（§2–3）

| 功能 | 主工具 | 不要用 |
|---|---|---|
| 工作流执行 | ComfyUI HTTP API（mock 实现同契约） | 自己写推理后端 |
| 测试 | pytest + httpx／mock server | 真实 GPU 必测 |

## Code pointers

- `backend/local_video_studio/mock_comfyui.py` · `comfy_client.py` · `agent/poller.py`
