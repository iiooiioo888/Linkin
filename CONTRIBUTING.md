# 貢獻指南

感謝協助維護 **靈境·Linkin**。本文件說明本地開發、變更範圍與送審前檢查。

## 開始之前

1. 讀 [新人導覽](docs/onboarding.md)（10–15 分鐘）
2. 讀 [AGENTS.md](AGENTS.md) 的**關鍵約束**（LLM／圖狀態／OPC／Minecraft）
3. 複製 `.env.example` → `.env`（勿提交 `.env`）

本地啟動與測試指令見 [開發指南](docs/development/guide.md)。

## 分支與範圍

| 規則 | 說明 |
|------|------|
| 主線 | 僅 `master`（CI／Pages 只追蹤此分支） |
| 變更範圍 | 一個 PR 解決一個問題；避免「順手大重構」 |
| 文件 | 行為變更時同步更新對應 `docs/`；勿只改根 README 堆細節 |
| 機密 | 禁止提交 API 金鑰、閘門明文、真實憑證 |

## 開發檢查清單

送審前請確認：

- [ ] `pytest backend/tests/ -q` 通過（或至少跑與變更相關的模組測試）
- [ ] 未直接呼叫模型供應商 SDK（一律 `call_llm`）
- [ ] 未繞過 OPC `guard`／Minecraft MCP 護欄
- [ ] 未把 `write_file` 等檔案系統工具暴露給角色
- [ ] 前端變更：`cd frontend && npm run build` 可通過（若改了 UI／型別）
- [ ] 新增環境變數時更新 `.env.example` 與 [docs/config/reference.md](docs/config/reference.md)

### 建議依模組跑測試

```powershell
pytest backend/tests/test_reflection_loop.py -q
pytest backend/tests/test_company.py -q
pytest backend/tests/test_raho.py -q
pytest backend/tests/test_linkin_api.py -q
pytest backend/tests/test_minecraft_mcp.py -q
pytest backend/tests/test_opc_service.py -q
pytest backend/tests/test_architecture.py -q
```

Windows 暫存目錄權限問題時：

```powershell
pytest backend/tests/ --basetemp=.pytest_tmp
```

## 文件放哪裡？

| 內容 | 位置 |
|------|------|
| 落地頁、快速開始 | 根 `README.md`（保持精簡） |
| 詳文 | `docs/**`（知識庫為準） |
| **目錄／套件地圖** | `docs/structure.md`（改目錄先改此文） |
| 後端／OPC 心智模型 | `backend/README.md` · `opc_service/README.md` |
| Agent／CI 常用指令 | `AGENTS.md` |
| 前端視覺 Token | 根 `DESIGN.md`（**不是**系統設計） |
| AI Hub 契約 | `docs/AI_HUB_DETAILED_DESIGN.md`（路徑請勿隨意搬移；測試會讀取） |

知識庫目錄：[docs/README.md](docs/README.md)

## PR 說明建議

請寫清楚：

1. **為什麼**要改（問題／目標）
2. **改了什麼**（模組與行為）
3. **怎麼驗證**（跑過哪些測試／手動步驟）

## 行為準則

- 對安全邊界、資料遺失風險、授權閘門不可「圖方便」繞過
- 優先重用現有 helper／模式；避免無請求的新抽象與新依賴
- 討論與程式註解優先繁中或與周遭檔案一致的語言
