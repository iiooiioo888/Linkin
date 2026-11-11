# P0-01 — 项目管理与镜头表 CRUD

| Field | Value |
|---|---|
| **Title** | P0-项目管理与镜头表 CRUD |
| **Priority** | P0 |
| **Status** | **done** — satisfied by [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M1) |
| **Source** | FEATURES_AND_TOOLS.md §4 item 1 · §1 项目管理／镜头表 |

## Acceptance criteria（§1）

- [x] 创建/编辑/列出项目；项目状态机；项目目录自动创建
- [x] 创建项目后 `projects/{id}/` 下子目录存在（`script`／`keyframes`／`drafts`／`refines`／`audio`／`output` 等）
- [x] 导入 JSON 镜头表；手动增删改镜头；场景/镜头编号唯一
- [x] 导入 3 镜头后 ShotBoard 按 scene 分组显示

## Tests + docs DoD

- [x] `backend/tests/test_local_video_studio.py`（M1 CRUD／import）
- [x] `PROJECT_SPEC.md` · `docs/integrations/local-video-studio.md`

## Tools（§2–3）

| 功能 | 主工具 | 不要用 |
|---|---|---|
| 存储索引 | PostgreSQL／SQLite + 相对路径（`LocalPathStorage`） | 只靠文件夹命名 |
| API | FastAPI + Pydantic v2 + SQLAlchemy 2 | — |

## Code pointers

- `backend/local_video_studio/service.py` · `storage.py` · `api.py`
- `frontend/src/modules/local-video-studio/ProjectsPage.tsx` · `ShotBoardPage.tsx`
