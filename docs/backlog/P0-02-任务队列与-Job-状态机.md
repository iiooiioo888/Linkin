# P0-02 — 任务队列与 Job 状态机

| Field | Value |
|---|---|
| **Title** | P0-任务队列与 Job 状态机 |
| **Priority** | P0 |
| **Status** | **done** — satisfied by [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M2) |
| **Source** | FEATURES_AND_TOOLS.md §4 item 2 · §1 任务队列 |

## Acceptance criteria（§1）

- [x] 创建/领取/完成/失败/取消/重试 job
- [x] attempt 上限；优先级
- [x] 失败 job 可重试；超过 `max_attempts` 变 failed 且不可自动重试

## Tests + docs DoD

- [x] `backend/tests/test_local_video_studio_m2.py`
- [x] JobsPage 显示 attempt／错误／取消／重试

## Tools（§2–3）

| 功能 | 主工具 | 备用 | 不要用 |
|---|---|---|---|
| 任务队列 | **当前**：DB 状态机（`lvs_generation_jobs`） | RQ + Redis（选型清单） | Celery（MVP 过重） |

> 注：§2 推荐 RQ+Redis；#167 以 DB 队列落地且可测。后续若引入 RQ，须保持同一验收标准、不改功能契约。

## Code pointers

- `backend/local_video_studio/jobs.py` · `agent/poller.py`
- `frontend/src/modules/local-video-studio/JobsPage.tsx`
