# opc_service — OPC UA 微服務

工業感測讀寫、6 級閉環節點與**寫入護欄**。由主後端在工業任務路徑注入上下文；本服務可獨立進程執行。

**目錄地圖：** [docs/structure.md](../docs/structure.md)  
**架構詳文：** [docs/architecture/opc-integration.md](../docs/architecture/opc-integration.md)

## 關鍵檔案

| 檔案 | 職責 |
|------|------|
| `main.py` / `app.py` | 服務入口（預設埠 **8001**） |
| `graph.py` | OPC 閉環圖 |
| `sense.py` → `preprocess` → `analyze` → `diagnose` → `decide` → `act` | 六級節點 |
| `guard.py` | **所有寫入必經**：白名單、數值邊界 |
| `opc_client.py` | OPC UA 客戶端 |
| `simulator/` | 模擬伺服器 |
| `audit.py` | 審計日誌 |

## 啟動

```powershell
$env:OPC_SIM_ENABLED="true"
python -m opc_service.main
```

或：`docker compose up -d opc_service`

## 禁止

- **禁止**繞過 `guard.py` 直接寫入 OPC 標籤  
- 單元測試以 `monkeypatch` 隔離真實設備（見 `backend/tests/test_opc_service.py`）
