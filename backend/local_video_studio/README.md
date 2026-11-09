# Local Video Studio（`local-video-studio`）

本機優先的私有化 AI 影片生成模組。完整規格見倉庫根目錄 [`PROJECT_SPEC.md`](../../PROJECT_SPEC.md)；整合說明見 [`docs/integrations/local-video-studio.md`](../../docs/integrations/local-video-studio.md)。

## 里程碑（本目錄）

| 里程碑 | 狀態 | 內容 |
| --- | --- | --- |
| **M0** | 本 PR | 骨架、health、compose overlay、空前端 |
| M1+ | 未實作 | CRUD／Agent／ComfyUI — 見 PROJECT_SPEC |

## Health

```bash
# 主後端（python -m backend.main）
curl -s http://127.0.0.1:8000/local-video-studio/health
# → {"ok":true,"module":"local-video-studio","milestone":"M0",...}

# 統一模組目錄
curl -s http://127.0.0.1:8000/modules/local-video-studio/health
```

別名：`GET /local-video-studio/api/v1/health`。

## 前端

`#/modules/local-video-studio`（實驗室 → 整合 → 設計）。

## Compose（不改預設 `docker-compose.yml`）

```bash
docker compose -f docker-compose.local-video-studio.yml --profile local-video-studio up -d
```

服務：`lvs-postgres` / `lvs-redis` / `lvs-api` / `lvs-web` / `lvs-worker-light`（M0 僅骨架；ComfyUI 不進 compose）。

## 約束

- `LVS_CLOUD_ENABLED`／`CLOUD_ENABLED` 預設 `false`，M0 無雲端呼叫。
- 若日後需要 LLM，一律經 `backend.core.llm.call_llm`。
- 測試以 monkeypatch 隔離；勿依賴真實 ComfyUI／NAS。
