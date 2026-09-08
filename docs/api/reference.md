# REST API 參考

Base URL: `http://localhost:8000`

## 聊天

### POST /chat

同步聊天，返回完整回答。

**請求：**
```json
{
  "query": "什麼是反思閉環？",
  "session_id": "abc123",
  "execution_strategy": "auto",
  "company_template": "quick_task",
  "history": [
    {"role": "user", "content": "之前的问题"},
    {"role": "assistant", "content": "之前的回答"}
  ]
}
```

**回應：**
```json
{
  "session_id": "abc123",
  "answer": "反思閉環是...",
  "score": 8.5,
  "iteration": 1
}
```

**execution_strategy：**
- `auto`（預設）：系統自動判斷複雜度
- `simple`：強制單次 LLM 生成
- `company`：強制多代理人公司運行時

---

### POST /chat/stream

SSE 串流聊天，即時推送階段進度與生成 token。

**事件格式：**

```
event: phase
data: {"phase": "generate"}

event: token
data: {"token": "反思"}

event: evaluation
data: {"score": 7.2, "iteration": 1, "multi_dim": {"accuracy": {"score": 8.0, "reason": "..."}, ...}}

event: done
data: {"answer": "完整回答", "score": 8.5, "iteration": 1}

event: error
data: {"error": "錯誤訊息"}
```

---

## 任務管理

### POST /tasks

建立後台任務，返回 task_id。

**請求：**
```json
{
  "query": "開發一個完整的電商系統",
  "execution_strategy": "company",
  "company_template": "fullstack_app",
  "options": {
    "budget_limit": 5.0,
    "max_parallel": 4,
    "max_iterations": 3,
    "pass_threshold": 8
  }
}
```

**回應：**
```json
{
  "task_id": "a1b2c3d4",
  "strategy": "company"
}
```

### GET /tasks/{task_id}

查詢任務進度。

**回應：**
```json
{
  "task_id": "a1b2c3d4",
  "status": "running",
  "strategy": "company",
  "resolved_path": "company",
  "query": "開發一個完整的電商系統",
  "phase": "execute_review",
  "progress": {
    "total_items": 5,
    "done": 2,
    "executing": 1,
    "review": 1,
    "blocked": 0
  },
  "budget": {
    "task_spent": 1.234,
    "budget_pressure": 0.25
  }
}
```

**status：** `pending` | `running` | `completed` | `failed` | `cancelled` | `interrupted`

### POST /tasks/{task_id}/cancel

取消執行中的任務。

### POST /tasks/{task_id}/resume

從檢查點恢復任務執行。

### GET /tasks/{task_id}/trace

獲取任務的思考過程記錄（分頁）。

**參數：** `limit`（預設 100）、`offset`（預設 0）

### WebSocket /tasks/{task_id}/ws

即時任務進度推送。

---

## RAHO 質詢與裁決

### POST /raho/grill/start

啟動 L5→L4 用戶 Grill-Me。簡單閒聊可回 `should_grill: false`。

### POST /raho/grill/turn

回答一輪審計。`force_lock: true` 視同過度授權，五維未達標會終止而非放行。

### GET /raho/grill/status

審計閘門狀態與鎖定門檻。

### GET /raho/tree

遞歸質詢樹、戰役 DAG、待決決策與阻塞點。可帶 `run_id`。

### POST /raho/decide

L5 用戶點選熱馬桶圈方案。

### GET /raho/scorecard

角色被質詢率與決策清晰度。

### POST /raho/commander/plan

L3 戰術指揮官：把 L4 門票 JSON（或鎖定簡報）拆成原子作戰地圖。可能回 `PLAN_READY`、`REJECT_TO_L4` 或 `ESCALATE_TO_USER`。

### POST /raho/commander/grill

L3 回應 L2 `[GRILL]`（資料缺失／工具不足／邏輯矛盾／單純確認）。3 輪無解自動 `[ESCALATE]`。

---

## 配置

### GET /config

取得當前 LLM 配置（金鑰脫敏）。

### POST /config

動態更新 LLM 配置（即時生效）。

```json
{
  "api_key": "sk-...",
  "api_base": "https://api.openai.com/v1",
  "model": "gpt-4o"
}
```

### POST /config/test

測試 LLM 連線。

---

## 記憶庫

### GET /memories

列出記憶（分頁）。參數：`limit`、`offset`

### DELETE /memories/{memory_id}

刪除單條記憶。

### POST /memories/cleanup

清理過期或低品質記憶。參數：`max_age_days`、`min_score`

---

## Docker 管理

### GET /docker/status

獲取 Docker 狀態摘要。

### GET /docker/budget

獲取容器預算狀態。

### POST /docker/restart/{service}

重啟指定服務。

### POST /docker/stop/{service}

停止指定服務。

### POST /docker/start/{service}

啟動指定服務。

---

## 雲控制台

### GET /cloud/billing

費用摘要。

### GET /cloud/monitoring?range=1h

資源監控歷史數據。

### GET /cloud/alerts

告警規則與歷史。

---

## 控制面版

### GET /dashboard

聚合資料（統計/任務/存檔/審計/能力）。

### GET /health

健康檢查。回傳 `{"status": "ok"}`

---

## 靈境·Linkin

完整表格見 [靈境 API](../linkin/api.md)。常用端點：

- `GET/PUT /linkin/constitution` — 世界觀憲法
- `GET/POST /linkin/npcs`、`PUT/DELETE /linkin/npcs/{id}`、`POST /linkin/npcs/{id}/dialogue`
- `POST /linkin/quests/generate`、`GET /linkin/quests`、`DELETE /linkin/quests/{id}`
- `POST /linkin/buildings/generate`、`GET /linkin/buildings`、`DELETE /linkin/buildings/{id}`
- `POST/GET /linkin/items`、`DELETE /linkin/items/{id}`
- `GET /linkin/events`
- `POST /linkin/admin/execute`（敏感操作需 `confirmed`）
- `GET /linkin/overview`
