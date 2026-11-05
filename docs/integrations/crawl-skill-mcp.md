# 採集：Skill + MCP 藍圖

名字 → 跨平台公開內容 → Media Vault 展示與監控。本文件只定分工與順序，**不**新增 MCP server 或爬蟲實作。

## 三層

| 層 | 是什麼 | 不是什麼 |
| --- | --- | --- |
| **Skill** | 工作流 Markdown（何時做、先後步驟、完成條件） | 登入、Cookie、選擇器、請求參數 |
| **MCP** | 原子工具（搜尋一則、下載一則媒體） | 跨平台編排、入庫策略 |
| **編排** | 主技能把「發現工具 → 呼叫 → 交給 Vault 入庫概念」串起來 | 取代 `backend/mediacrawler` 任務機 |

代理先乾跑這條鏈。穩定後再把同一契約凍進 FastAPI 確定管線（既有 MediaCrawler job + `backend/media_vault`），代理不再臨場決定平台順序。

## 建議順序

1. **盤點**：對照下表，標 reuse / wrap / build。
2. **登記 MCP**：只登記已存在、且只讀公開資料的工具；本倉庫目前沒有這些外部 MCP。
3. **mcp2skill**：每個原子工具一張薄技能，不把多平台流程寫進同一張。
4. **薄主技能**：`.agents/skills/media-collect/SKILL.md`（約 50–100 行，wrapper：步驟在主檔，工具契約在 `references/TOOLS.md`）。
5. **代理乾跑**：不寫 Cookie、不啟動真實採集；只核對工具名與入庫欄位是否對得上 Vault。
6. **之後凍結**：完成的 job 仍走 `backend/media_vault/ingest.py` → `unified_posts` / `media_assets`，Hub 為 `#/modules/media-vault`（控制／監控／圖庫）。

## 既有 Linkin 零件

| 零件 | 路徑 | 本藍圖怎麼用 |
| --- | --- | --- |
| MediaCrawler 適配 | `backend/mediacrawler/` | 抖音、小紅書等已接平台的 **reuse** 執行面（`EVOL_MEDIACRAWLER_ENABLED`，預設關） |
| 平台技能 | `.agents/skills/mediacrawler/SKILL.md` | 既有 CLI／HTTP 操作說明；主技能不複製 Cookie 與啟用步驟 |
| Media Vault | `backend/media_vault/`、`docs/integrations/media-vault.md` | 持久化與 `#/modules/media-vault` 展示／監控；入庫概念對齊 `ingest`（批次、去重、合規欄位） |
| 結構索引 | `docs/structure.md`「採集」 | 採集仍屬整合，不新開產品模式 |

## 平台盤點

| 平台 | 判定 | 依據 |
| --- | --- | --- |
| 抖音 Douyin | **reuse** | MediaCrawler `--platform dy`（search／detail／creator），技能表已列 |
| TikTok | **wrap** | 與抖音不是同一適配；若日後有獨立公開 MCP，只包一層工具名，不在本階段自寫爬蟲 |
| 小紅書 | **reuse** | MediaCrawler `--platform xhs` |
| Instagram | **build** | 倉庫與 MediaCrawler 平台表皆無；列為缺口，不在本 PR 實作 |
| X | **build** | 同上 |

快手、B站、微博、貼吧、知乎已在 `.agents/skills/mediacrawler/SKILL.md`，維持 reuse，不納入本次跨平台缺口。

合規：只採集各平台允許的公開資料；遵守服務條款。Cookie、帳密、session **不得**寫進技能、契約或 git。

## 設計期工具（非執行期依賴）

下列名稱只在設計階段用來發現或生成技能。**倉庫內沒有**把它們接成執行期套件；`skill-creator` 僅以 `.agents/skills/anthropic-skill-creator/`、`.agents/skills/openai-skill-creator/` 存在，目錄名不同。

| 名稱 | 設計期用途 |
| --- | --- |
| `agent-discover` | 找已登記的 MCP，不假設本機已安裝 |
| `search-mcp-server` | 依平台關鍵字找候選 MCP |
| `smart-mcp-proxy` | 討論多伺服器掛載方式；未接入 Linkin |
| `mcp2skill` | 由原子工具生成單技能，再由主技能引用 |
| `skill-creator` | 校主技能前欄與篇幅；用倉庫內 Anthropic／OpenAI 兩份，不另裝同名套件 |

工具契約（名稱、參數、平台、合規）見 `.agents/skills/media-collect/references/TOOLS.md`。`search_*` 與 `download_media` 是契約名，不是已實作的 MCP。
