# backend — FastAPI + LangGraph

靈境·Linkin 後端：統一管線入口、公司運行時、靈境／Minecraft 護欄、AI Hub、記憶與監控服務。

**完整目錄地圖：** [docs/structure.md](../docs/structure.md)  
**約束（必讀）：** [AGENTS.md](../AGENTS.md)

## 從哪改起

| 你要改… | 目錄／檔案 |
|---------|------------|
| HTTP／SSE／WS 路由 | `main.py` |
| 反思閉環圖與節點 | `core/graph.py`、`core/nodes.py`、`core/evaluation.py` |
| 公司／RAHO | `company/`、`company/raho/`、`core/company_nodes.py` |
| LLM 呼叫 | **僅** `core/llm.py` → `call_llm`（LiteLLM） |
| 模型池／API 路由 | `core/provider_pool.py`、`core/api_router.py`、`core/llm_config.py` |
| 靈境實體／憲法 | `linkin/` |
| Minecraft 寫入護欄 | `linkin/minecraft.py` + `tools/minecraft_mcp.py` |
| AI Hub | `hub/`（契約：`docs/AI_HUB_DETAILED_DESIGN.md`） |
| 向量記憶 | `memory/` |
| 監控／任務／軌跡 | `services/` |
| 登入閘門 | `auth/` |
| 種子／煙測 | `scripts/` |
| 測試 | `tests/`（一律 `monkeypatch`，不連真實 LLM／遊戲） |

## 啟動

```powershell
# 倉庫根目錄
python -m backend.main          # http://localhost:8000
pytest backend/tests/ -q
python -m backend.scripts.seed_demo_content
```

## 禁止

1. 直連任何模型供應商 SDK  
2. 直接改編譯後的 LangGraph 圖（改 `build_graph()`／節點）  
3. 繞過 OPC／Minecraft 護欄，或把 `write_file` 等檔案工具暴露給角色  

詳見根目錄 [AGENTS.md](../AGENTS.md) 與 [開發指南](../docs/development/guide.md)。
