# 部署指南

> 對齊日期：2026-09-09

## Docker Compose（推薦）

### 一鍵部署

```powershell
# 全部服務
docker compose up -d

# 僅基礎設施（Redis + ChromaDB）
docker compose up -d redis chroma

# 查看日誌
docker compose logs -f backend
```

### 服務端口

| 服務 | 端口 | 說明 |
|------|------|------|
| `backend` | 8000 | FastAPI + LangGraph |
| `frontend` | **3001**（宿主） | Compose prod：3001→容器 80；Compose dev／本機 Vite：3001 |
| `opc_service` | 8001 | OPC UA 微服務 |
| `redis` | 6379 | 任務持久化 |
| `chroma` | 8100 | 向量記憶庫 |

完整埠號矩陣見 [術語表](../glossary.md)。

### 環境變數

在專案根目錄建立 `.env`（可從 `.env.example` 複製）：

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_API_BASE=https://api.deepseek.com
EVOL_MODEL=deepseek-v4-flash
```

完整變數見 [配置參考](../config/reference.md)。

### 健康檢查

```powershell
curl http://localhost:8000/health
curl http://localhost:8100/api/v1/heartbeat
docker compose exec redis redis-cli ping
```

## 本地開發部署

```powershell
python -m backend.main

cd frontend
npm install
npm run dev

# OPC（可選）
$env:OPC_SIM_ENABLED="true"; python -m opc_service.main
```

前端預設 http://localhost:3001。詳見 [開發指南](../development/guide.md)。

## GitHub Pages（前端）

推送到 **`master`** 後，Actions `Deploy to GitHub Pages` 會：

1. 匯出監控降級資料（`python -m backend.scripts.export_monitor_fallback`）
2. 以 `VITE_BASE=/{倉庫名}/`、`VITE_GITHUB_PAGES=true` 建置前端（本倉庫為 `/Linkin/`）
3. 部署至 [https://iiooiioo888.github.io/Linkin/](https://iiooiioo888.github.io/Linkin/)

> 僅 `master` 觸發；`main` 已停用，避免雙版本分叉。

Pages 僅託管靜態前端。聊天、LLM、寫入需本地或 Docker 後端（可設 `VITE_API_URL`）。

手動觸發：GitHub → Actions → **Deploy to GitHub Pages** → Run workflow。

上游 EvoLoop Demo：[https://iiooiioo888.github.io/Evoloop/](https://iiooiioo888.github.io/Evoloop/)

## 生產環境建議

### 安全

- 使用 HTTPS
- 收緊 CORS（勿長期 `allow_origins=["*"]`）
- 啟用登入閘門（勿在生產設 `LINKIN_AUTH_DISABLED=1`）
- OPC 寫入白名單限制

### 性能

- Redis 持久化（AOF + RDB）
- ChromaDB 使用 HttpClient
- 後端多 worker：`uvicorn backend.main:app --workers 4`
- 前端 Nginx 反向代理

### 監控

- `/dashboard`、`/cloud/monitoring`、`/cloud/alerts`

### 備份

- Redis：`BGSAVE`
- ChromaDB：持久目錄
- JSONL：`backend/data/archives/`、`company_runs/`、`traces/`（注意 `.gitignore` 規則）
