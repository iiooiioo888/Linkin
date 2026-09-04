# Minecraft MCP 整合（靈境·Linkin）

將 Minecraft 服務端操作封裝成公司運行時角色可調用的工具。Linkin 負責思考與決策，MineMCP 負責執行。

```
公司運行時 / 靈境角色
        │  tool_call: place_block / fill_block / execute_command …
        ▼
backend/tools/minecraft_mcp.py     JSON-RPC 客戶端 + 乾跑 + 審計
        │  鐵律：backend/linkin/minecraft.py
        ▼
MineMCP（Paper 1.21 插件）  HTTP /sse?token=
        ▼
Minecraft 世界
```

## 為什麼不是直接 POST `/sse`

MineMCP 給編輯器的 MCP 連線 URL 是 `http://localhost:3000/sse?token=…`。本倉庫用 **JSON-RPC `tools/call`** 打同一端點（Token 放 query，並附 `Authorization: Bearer`）。放置方塊的**遠端工具名是 `pose_block`**（MineMCP 拼寫），對內與角色目錄使用 `place_block`，並註冊別名 `pose_block`。

檔案系統工具（`write_file` 等）預設封鎖，不對角色開放。

## 服務端（Paper / Purpur）

1. Java 21 + Paper/Purpur 1.21
2. 安裝 [MineMCP](https://github.com/AxenoDev/MineMCP/releases) 到 `plugins/`
3. 修改 `plugins/MineMCP/config.yml` 的 token（不要用預設值）
4. 控制台出現 `MCP server started on port 3000`

端口 3000 與本專案前端預設 3001 / 5173 錯開。後端 API 仍是 8000。

## Linkin 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `EVOL_MC_MCP_ENABLED` | `false` | `true` 才對 MineMCP 發真實請求 |
| `EVOL_MC_MCP_URL` | `http://127.0.0.1:3000` | 不含 path |
| `EVOL_MC_MCP_TOKEN` | （空） | 與插件 config.yml 相同；未設定則永遠乾跑 |
| `EVOL_MC_MCP_RPC_PATH` | `/sse` | JSON-RPC 路徑 |
| `EVOL_MC_MCP_WORLD` | `world` | 預設世界名 |
| `EVOL_MC_MCP_TIMEOUT` | `30` | 秒 |
| `EVOL_MC_MCP_MAX_FILL` | `5000` | 單次 fill 上限（再與憲法取小） |
| `EVOL_MC_MCP_ALLOW_FILES` | `false` | 允許檔案工具（不建議） |
| `EVOL_MC_MCP_AUDIT_PATH` | `backend/data/linkin/mcp_audit.jsonl` | 審計 |

未啟用或無 Token：**乾跑**。工具仍可被角色呼叫，回傳 `dry_run: true`，不寫入世界。單元測試一律乾跑。

Docker 後端要打宿主機上的 Minecraft 時，Windows 可用 `EVOL_MC_MCP_URL=http://host.docker.internal:3000`。

## 公司角色與 `tools_allowed`

工具註冊在 `backend.company.tools.tool_registry`（與 Docker / 實驗室工具同一套 ReAct `tool_call` 格式）。

| 工具 | 誰能用（`allowed_roles`） |
|------|---------------------------|
| `place_block` / `pose_block` / `break_block` / `fill_block` | manager、creative_lead、story_writer、`custom_linkin_build_*` |
| `execute_command` | manager、`custom_linkin_build_director`（敏感指令需 `confirmed`） |
| `get_player` / `get_online_players` | 上述 + reviewer 與 `custom_linkin_*` |

`role_catalog.json` 的 `tools_allowed` **非空時取交集**。空列表表示不額外限制（仍受 `allowed_roles` 約束）。`allow_tool_use: false` 則完全不注入、不執行工具。

`python -m backend.scripts.seed_linkin_world` 會把建築總監／執行者的 `tools_allowed` 寫成對應 MCP 工具。

靈境複雜任務預設走 `story_studio`，因此 **story_writer / creative_lead / manager** 在公司運行時就能呼叫放置方塊，不必等自定義角色被指派為 `RoleType`。

## API 與監控

| 方法 | 路徑 |
|------|------|
| GET | `/linkin/minecraft/status` |
| POST | `/linkin/minecraft/probe` |
| POST | `/linkin/minecraft/call` |
| POST | `/linkin/buildings/{id}/dispatch` 錨點放一顆標記方塊，不一次填滿方案體積 |
| POST | `/linkin/admin/execute` 通過鐵律後轉發 `execute_command` |

監控中心：**靈境 → Minecraft**。建築面板可「發送到 Minecraft」。實驗室 MCP 分頁顯示橋接狀態。

## 其他 MCP 實作

- Paper 首選：[AxenoDev/MineMCP](https://github.com/AxenoDev/MineMCP)
- Paper + Fabric：[InventivetalentDev/minecraft-mcp](https://github.com/InventivetalentDev/minecraft-mcp)（WebSocket，可另接 `EVOL_MC_MCP_RPC_PATH`）
- Fabric 深度：[Etoryx/mcpfabric](https://github.com/Etoryx/mcpfabric)

本倉庫客戶端先對齊 MineMCP JSON-RPC；換實作時只改橋接層，不要讓節點直連遊戲。
