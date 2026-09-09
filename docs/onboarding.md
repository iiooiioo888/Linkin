# 新人導覽

> 目標：半天內能在本機跑起服務、知道改哪裡、知道文件在哪。  
> 對齊日期：2026-09-09

## 1. 專案一句話

**Linkin** = EvoLoop 統一管線（反思／公司／OPC）+ 靈境世界觀 + 監控中心前端。  
沒有「標準版／公司版／OPC 版」三套產品；複雜度路由決定執行路徑。

## 2. 建議閱讀順序（約 30–45 分鐘）

| 順序 | 文件 | 為什麼 |
|:----:|------|--------|
| 1 | [根 README](../README.md) | 落地頁、快速開始、約束摘要 |
| 2 | 本文 | 心智模型 |
| 3 | [目錄地圖](structure.md) | 套件路徑單一來源（85 vs 16 角色別搞混） |
| 4 | [術語表](glossary.md) | RAHO／L 層／埠號（5 分鐘） |
| 5 | [AGENTS.md](../AGENTS.md) | 模組邊界與**禁止事項** |
| 6 | [架構總覽](architecture/overview.md) | 資料流 |
| 7 | 依你要動的領域選讀 | 見下表 |
| 8 | [開發指南](development/guide.md) · [貢獻指南](../CONTRIBUTING.md) | 動手與送審 |

### 依任務選讀

| 你要改… | 讀這些 |
|---------|--------|
| 反思閉環／圖節點 | [reflection-loop](architecture/reflection-loop.md) · `backend/core/` |
| 多代理人／RAHO | [company-runtime](architecture/company-runtime.md) · [角色介紹](company/roles.md) · `backend/company/` |
| OPC | [opc-integration](architecture/opc-integration.md) · `opc_service/` |
| 靈境／Minecraft | [linkin/](linkin/worldview.md) · [minecraft-mcp](linkin/minecraft-mcp.md) |
| 模型池／價卡／Hub | [config/reference](config/reference.md) · [AI Hub](AI_HUB_DETAILED_DESIGN.md) |
| 量化工具 | [company/quant-tools](company/quant-tools.md) |
| API／前端監控 | [api/reference](api/reference.md) · [frontend/README](../frontend/README.md) |
| 部署 | [deployment/guide](deployment/guide.md) |

## 3. 目錄心智模型

完整表格與套件說明見 **[目錄地圖](structure.md)**；心智模型摘要：

```
請求 → FastAPI (backend/main.py)
     → LangGraph (backend/core/graph.py)
         ├─ 簡單：生成 → 評估 →（反思）→ 記憶
         ├─ 複雜：company/ + raho/
         └─ 工業：opc_service 上下文 + 6 級閉環
前端 MonitorView 只負責觀測與配置；寫世界／OPC 仍走護欄。
```

| 目錄 | 職責 | 套件 README |
|------|------|-------------|
| `backend/core/` | 圖、節點、`call_llm`、評估、模型池 | [backend/](../backend/README.md) |
| `backend/company/` | 協調器、**85** 席 STANDARD_ROLES、RAHO | 同上 |
| `backend/linkin/` | 憲法、實體、**16** 席子角色、Minecraft 業務護欄 | 同上 |
| `backend/tools/` | MineMCP／運維等底層橋接 | 同上 |
| `backend/hub/` | AI Hub 契約實作 | 同上 |
| `opc_service/` | OPC UA 讀寫與護欄（獨立進程） | [opc_service/](../opc_service/README.md) |
| `frontend/src/` | 單一 UI（活動欄五層） | [frontend/](../frontend/README.md) |
| `docs/` | **詳文唯一來源** | [docs/README.md](README.md) |

## 4. 本機最小路徑

```powershell
# 根目錄
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env

python -m backend.main          # :8000
# 另開終端
cd frontend; npm install; npm run dev   # :3001
```

可選：`docker compose up -d redis chroma`、`python -m backend.scripts.seed_demo_content`。

## 5. 第一個安全的練習 PR

建議從小處開始，例如：

- 修正文件錯字／過期端口（本知識庫）
- 為既有行為補一則單元測試（`monkeypatch`，不連外網）
- 前端文案或無行為變更的型別整理

送審前對照 [CONTRIBUTING.md](../CONTRIBUTING.md) 檢查清單。

## 6. 常見迷路點

| 現象 | 去哪看 |
|------|--------|
| 測試暫存目錄權限 | [faq](faq.md) · `--basetemp=.pytest_tmp` |
| 記憶／L0 空白 | [faq](faq.md) · `seed_demo_content` |
| 只配 DeepSeek 卻跑到別家模型 | [config/reference](config/reference.md) 模型池 |
| Pages 不能聊天 | 正常；需本地／Docker 後端 |
| `DESIGN.md` 很長像設計系統 | 那是**前端視覺 Token**，不是架構；架構在 `docs/architecture/` |

## 7. 下一步

- 目錄地圖：[structure.md](structure.md)  
- 角色一覽：[company/roles.md](company/roles.md)（85＋16＋模板）  
- 術語表：[glossary.md](glossary.md)  
- 知識庫總目錄：[README.md](README.md)  
- 卡住：[faq.md](faq.md)
