# 開發指南

> 新人請先讀 [onboarding.md](../onboarding.md)、[目錄地圖](../structure.md) 與根目錄 [CONTRIBUTING.md](../../CONTRIBUTING.md)。  
> 對齊日期：2026-09-09

## 環境需求

| 工具 | 版本 | 說明 |
|------|------|------|
| Python | **3.12+** | 後端（`pyproject.toml` `requires-python`） |
| Node.js | 20+ | 前端 |
| Docker | 可選 | Redis／Chroma／一鍵編排 |

## 本地開發

```powershell
git clone https://github.com/iiooiioo888/Linkin.git
cd Linkin

python -m venv .venv
.venv\Scripts\Activate.ps1          # Linux/Mac: source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env              # Linux/Mac: cp .env.example .env
# 編輯 .env：API 金鑰、可選 api_base／模型

# 後端 http://localhost:8000
python -m backend.main

# 前端 http://localhost:3001
cd frontend
npm install
npm run dev
```

可選基礎設施：

```powershell
docker compose up -d redis chroma
python -m backend.scripts.seed_demo_content
python -m backend.scripts.seed_linkin_world
```

## 腳本速查

| 命令 | 用途 |
|------|------|
| `python -m backend.scripts.seed_demo_content` | 示範記憶／任務／軌跡 |
| `python -m backend.scripts.seed_linkin_world` | 靈境世界種子 |
| `python -m backend.scripts.smoke_test` | 向量記憶冒煙 |
| `python backend/scripts/test_llm_connection.py` | LLM 連線 |
| `python -m backend.scripts.export_openapi` | 匯出 OpenAPI |
| `python -m backend.scripts.export_monitor_fallback` | Pages 監控降級資料 |

完整表見 [目錄地圖 · scripts](../structure.md#backendscripts)。

## 測試

單元測試以 `monkeypatch` 隔離 LLM／Redis／OPC／MineMCP，**無需真實 API 金鑰**。目前約 **639** 筆收錄（以 `pytest --collect-only -q` 為準）。

```powershell
pytest backend/tests/ -q

# 依領域
pytest backend/tests/test_company.py -q
pytest backend/tests/test_raho.py -q
pytest backend/tests/test_reflection_loop.py -q
pytest backend/tests/test_linkin_api.py -q
pytest backend/tests/test_minecraft_mcp.py -q
pytest backend/tests/test_opc_service.py -q
pytest backend/tests/test_provider_pool.py -q
pytest backend/tests/test_architecture.py -q

# Windows 暫存目錄權限
pytest backend/tests/ --basetemp=.pytest_tmp
```

## 專案結構

完整表見 **[目錄地圖](../structure.md)**。精簡樹：

```
Linkin/
├── backend/                    # 見 backend/README.md
│   ├── main.py                 # FastAPI 入口
│   ├── auth/ · middleware/ · environment/ · prompts/
│   ├── core/                   # 圖、節點、LLM、評估、模型池
│   │   ├── graph.py            #   build_graph()、複雜度路由
│   │   ├── nodes.py            #   生成／評估／反思／改進
│   │   ├── company_nodes.py    #   公司運行時節點
│   │   ├── llm.py              #   call_llm（唯一允許的 LLM 出口）
│   │   ├── provider_pool.py    #   模型池鎖定
│   │   └── evaluation.py       #   多維評估
│   ├── company/                # 協調器、角色（85）、raho/、量化
│   ├── linkin/                 # 靈境＋16 席子角色＋Minecraft 業務護欄
│   ├── tools/ · hub/ · memory/ · services/
│   ├── config/                 # 執行期 JSON（價卡等）
│   ├── data/ · scripts/
│   └── tests/
├── opc_service/                # 見 opc_service/README.md
├── frontend/                   # 見 frontend/README.md（預設 :3001）
├── docs/                       # 知識庫
└── docker-compose.yml
```

更完整說明：[架構總覽](../architecture/overview.md) · [目錄地圖](../structure.md) · 根 [README](../../README.md)。

## 關鍵約束

1. **LLM**：一律 `backend.core.llm.call_llm`，禁止直連供應商 SDK  
2. **測試隔離**：外部服務用 `monkeypatch`，不依賴真實金鑰／遊戲伺服器  
3. **圖狀態**：禁止改編譯後的圖；改 `build_graph()` 與節點實作  
4. **OPC**：寫入必須經 `opc_service/guard.py`  
5. **Minecraft**：寫入必須經 `backend/tools/minecraft_mcp.py` 與 `backend/linkin/minecraft.py`；禁止把檔案系統工具暴露給角色  

詳見 [AGENTS.md](../../AGENTS.md)。

## 擴展點

### 新評估維度

1. `backend/core/evaluation.py` 的 `DIMENSION_WEIGHTS`  
2. `MULTI_DIM_EVALUATE_PROMPT` 維度說明  
3. `RuleBasedFallback` 規則邏輯  

### 新組織模板

在 `backend/company/roles.py` 的 `BUILTIN_TEMPLATES` 新增角色與預算。席位職責表見 [角色介紹](../company/roles.md)；改完後執行 `python -m backend.scripts.export_roles_doc` 同步文件。

### 新 OPC 感測器

1. `opc_service/simulator/` 模擬資料  
2. `opc_service/analyze.py` 的 `DEFAULT_THRESHOLDS`  

### 更換／鎖定 LLM

1. `.env` 或控制台「API 路由」寫入金鑰與端點  
2. `EVOL_MODEL`（仍會被模型池 `clamp`）  
3. 通用端點可開 `EVOL_LLM_OPS_ENABLED` 爬取 `/models`  

詳見 [配置參考](../config/reference.md)。

## 調試

### LangGraph 軌跡

```powershell
curl http://localhost:8000/tasks/{task_id}/trace
```

前端：監控中心 → 軌跡（`http://localhost:3001`）。

### LLM 快取

```python
from backend.core.llm_cache import get_llm_cache
print(get_llm_cache().stats)
```

### 向量記憶

```python
from backend.memory.vector_store import VectorMemoryStore
store = VectorMemoryStore()
print(store.count())
```

### LLM 連線

```powershell
python backend/scripts/test_llm_connection.py
```

## 相關文件

- [常見問題](../faq.md)  
- [術語表](../glossary.md)  
- [部署指南](../deployment/guide.md)  
- [REST API](../api/reference.md)  
- [前端 README](../../frontend/README.md)
