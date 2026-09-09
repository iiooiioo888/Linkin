# 常見問題

## 測試出現 `OSError: could not create numbered dir`

Windows 暫存目錄權限問題。`pyproject.toml` 已設 `--basetemp=.pytest_tmp`。仍失敗時：

```powershell
pytest backend/tests/ --basetemp=.pytest_tmp
```

## 支援哪些 LLM？只填 DeepSeek 會怎樣？

透過 LiteLLM + 運行時配置。常見：OpenAI、DeepSeek、Qwen、Moonshot、智譜、OpenRouter、Ollama／vLLM 相容端點。

**模型池規則：** 系統只依你保存的 API／端點開放可用模型。只存 DeepSeek → Agent 只能用 DeepSeek；OpenRouter → 爬取 `/models` 後寫入配置，Agent 只能從該目錄選用。Claude／Anthropic 不會進入可用池。

詳見 [配置參考](config/reference.md)。

## 角色卡片右上角的 `$0` 是什麼？

該角色的**合計成本**（API + Docker + 雲），不是狀態徽章。沒有用量時顯示 `$0`。單價見控制台「配置 → API 路由」公開價卡。

## 監控「記憶」分頁是空的？

已改名為 **L0 核心**（舊網址 `#/monitor/console/memory` 仍會導向）。向量庫預設讀 Chroma `evo_memory`。尚未跑過成功對話、或 Chroma 未啟動時會是空的。

```powershell
python -m backend.scripts.seed_demo_content
```

會寫入示範知識庫（Chroma + `backend/data/memory_store.json`）。`GET /memories` 在 Chroma 為空或失敗時會改讀 JSON。種子後請重啟後端再刷新監控。

## 如何新增自定義角色？

監控中心 → **執行 → 角色** → 新增／複製。資料寫入 `role_catalog.json`（可用 `EVOL_ROLE_CATALOG_PATH` 覆寫）。亦可 `POST /monitor/agents`。

## 內建有多少角色？

兩套數字，勿混用：

| 數字 | 含義 |
|------|------|
| **85** | 公司 `STANDARD_ROLES`（含 RAHO 脊柱） |
| **16** | 靈境子角色（4 總監 × 總監+執行者+審查員+記錄員） |

詳見 [目錄地圖](structure.md) · [公司運行時](architecture/company-runtime.md)。

## RAHO 是什麼？可以關掉嗎？

遞歸對抗分層：複雜任務先經用戶 Grill-Me 鎖定需求，再拆戰役／原子任務，由獨立憲兵驗收。預設開啟。

- `EVOL_RAHO_ENABLED=false` — 關閉整套  
- `EVOL_RAHO_USER_GRILL=false` — 只關 L5 審計  

規劃／憲兵預設走規則，不額外呼叫 LLM（`EVOL_RAHO_*_LLM`）。

## OpenRouter 目錄多久更新一次？

預設每 300 秒（`EVOL_LLM_OPS_INTERVAL_SEC`）。控制台 **配置 → API 路由** 可手動刷新；`EVOL_LLM_OPS_ENABLED=false` 可關背景任務。

## OPC 需要真實設備嗎？

不需要。`OPC_SIM_ENABLED=true` 即可用內建模擬伺服器。

## GitHub Pages 能聊天嗎？

Pages 僅靜態前端預覽；登入閘門可在無後端時本機核對。聊天、寫入、刷新模型目錄等需連到本機或已部署後端（可設 `VITE_API_URL`）。

## 為什麼只有一個版本？

前端與監控已合拼為單一 `AppShell` + `MonitorView`；CI／Pages 只追蹤 `master`。

## 根目錄 `DESIGN.md` 是系統設計嗎？

**不是。** 那是 Linear 風格前端視覺 Token。系統架構請看 [architecture/](architecture/overview.md)；AI Hub 契約見 [AI_HUB_DETAILED_DESIGN.md](AI_HUB_DETAILED_DESIGN.md)。

## 開發埠是 5173 還是 3001？

前端一律用 **http://localhost:3001**：

- 本機 `npm run dev`：Vite 預設 3001（`VITE_DEV_PORT` 可覆寫）
- Docker Compose prod：宿主 **3001** → 容器 nginx 80
- Docker Compose dev（HMR）：宿主／容器皆 **3001**

舊文件若寫 5173 已過時。後端仍是 **8000**，OPC **8001**，MineMCP 預設 **3000**。速查：[glossary.md](glossary.md)。
