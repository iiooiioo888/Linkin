# P0-13 — API 文档同步（`/docs` + `docs/API.md`）

| Field | Value |
|---|---|
| **Title** | P0-API 文档同步 |
| **Priority** | P0 |
| **Status** | **partial** — FastAPI `/docs` 随主应用可用；`docs/API.md` **missing** |
| **Source** | FEATURES_AND_TOOLS.md §1 API 文档 · PROJECT_SPEC「Every API change must update docs/API.md」 |

## Acceptance criteria（§1）

- [x] OpenAPI 自动生成（FastAPI 内建；主应用挂载 LVS router 后 `/docs` 可见）
- [ ] `docs/API.md` 与实现同步（端点表、鉴权、示例请求可复制）
- [ ] 示例请求可复制（curl／httpx）

## Tiny note（本 PR 已记）

- 主应用启动后访问 `http://<host>:8000/docs`（Swagger）或 `/redoc`
- LVS 路由前缀：`/local-video-studio` 与 `/local-video-studio/api/v1/...`
- 鉴权：`X-API-Key`（见 `.env.example`／`LVS_API_KEY`）

## Remaining gap

1. 新增 `docs/API.md`（或 `docs/integrations/local-video-studio-api.md`）列出 v1 端点  
2. 变更 API 时同步更新该文 + OpenAPI 描述  
3. 可选：从 `docs/openapi.json` 导出 LVS 子集

## Tests + docs DoD

- [ ] 文档列出全部 v1 端点
- [ ] 与 `api.py` 对照 checklist

## Tools（§2–3）

| 工具 | 用途 |
|---|---|
| FastAPI OpenAPI | `/docs` |
| Markdown | 人类可读 API.md |
