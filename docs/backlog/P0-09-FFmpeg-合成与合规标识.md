# P0-09 — FFmpeg 合成与合规标识

| Field | Value |
|---|---|
| **Title** | P0-FFmpeg 合成与合规标识 |
| **Priority** | P0 |
| **Status** | **done** — [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M5) |
| **Source** | FEATURES_AND_TOOLS.md §4 item 9 · §1 合成／合规标识 |

## Acceptance criteria（§1）

- [x] 按顺序拼接已通过镜头；混音；烧字幕；输出 MP4
- [x] 显式「AI 生成」文字；容器 metadata；ComplianceRecord 不可绕过
- [x] 成片带文字标识与 `ai_generated=true` metadata（stamp 强制）

## Tests + docs DoD

- [x] 测试生成的 FFmpeg 命令／compose 闭环（非真实编码必测）
- [x] ComposePanel UI

## Tools（§2–3）

| 功能 | 主工具 | 不要用 |
|---|---|---|
| 合成 | FFmpeg（集中在 `ffmpeg_compose.py`） | MoviePy；手工剪辑批处理 |
| 合规 | FFmpeg drawtext + metadata | 事后手动加标 |
| 元数据 | exiftool（推荐校验） | — |

## Code pointers

- `backend/local_video_studio/ffmpeg_compose.py` · `compliance.py` · `compose_service.py`
