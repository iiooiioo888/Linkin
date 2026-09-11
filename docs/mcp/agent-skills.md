# Agent skills — 可選 MCP 設定

本倉庫在 `.agents/skills/` 內嵌多個上游技能包。大多數技能僅為 **SKILL.md 工作流**（無需 MCP）。下列技能在啟用對應 MCP 伺服器時能力更完整；**請勿提交真實憑證**，僅在本地或 Cursor 使用者設定中填入。

完整技能清單與安裝方式見 [README — Agent skills](../../README.md#agent-skills)。

## 技能包與 MCP 對照

| 來源 | 技能數 | MCP | 說明 |
|------|--------|-----|------|
| [mattpocock/skills](https://github.com/mattpocock/skills) | 37 | 無 | 工程化工作流；skills-only |
| [anthropics/skills](https://github.com/anthropics/skills) | 20 | 無 | 文件處理、前端設計、`mcp-builder` 教學；skills-only |
| [openai/skills](https://github.com/openai/skills) | 43 | 部分 | 見下方「OpenAI 技能相關 MCP」 |
| [scrapegraphai/just-scrape](https://github.com/scrapegraphai/just-scrape) | 1 | 無（CLI） | 使用 `just-scrape` CLI + `SGAI_API_KEY` |
| [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) | 1 | 無（CLI） | 使用 `agent-browser` CLI（`npm i -g agent-browser`） |

### 命名衝突

Anthropic 與 OpenAI 皆提供 `pdf`、`skill-creator`。本倉庫保留兩套：

- `anthropic-pdf` / `anthropic-skill-creator` — 來自 `anthropics/skills`
- `openai-pdf` / `openai-skill-creator` — 來自 `openai/skills`

## OpenAI 技能相關 MCP

下列 MCP 為 **可選**；對應技能在無 MCP 時仍可閱讀，但部分步驟需手動查文件。

| MCP 伺服器 | 相關技能 | 端點 / 設定 |
|------------|----------|-------------|
| OpenAI Developer Docs | `openai-docs`, `chatgpt-apps` | `https://developers.openai.com/mcp` |
| Figma | `figma`, `figma-use`, `figma-implement-design`, … | `https://mcp.figma.com/mcp` + `FIGMA_OAUTH_TOKEN` |
| Linear | `linear` | `https://mcp.linear.app/mcp`（OAuth） |

詳細 Figma 設定片段見 `.agents/skills/figma/references/figma-mcp-config.md`。

## ScrapeGraphAI（CLI，非 MCP）

`just-scrape` 技能透過全域 CLI 呼叫 ScrapeGraph API，**不是** MCP 伺服器。

```bash
npm install -g just-scrape@latest
export SGAI_API_KEY="your-key-here"   # 或寫入 ~/.scrapegraphai/config.json
just-scrape validate
```

可選環境變數：`SGAI_API_URL`、`SGAI_TIMEOUT`、`SGAI_DEBUG`（見 `.agents/skills/just-scrape/SKILL.md`）。

## Vercel agent-browser（CLI，非 MCP）

`agent-browser` 為瀏覽器自動化 CLI，**不是** MCP 伺服器。

```bash
npm install -g agent-browser
agent-browser install   # 安裝 Chromium
agent-browser skills get core
```

工作流內容由已安裝版本動態提供（`agent-browser skills list`）。

## Cursor 範例片段

將下列內容合併到 Cursor 的 MCP 設定（例如使用者層 `~/.cursor/mcp.json` 或專案 `.cursor/mcp.json`）。**僅示範結構，請替換 placeholder。**

範例檔：[cursor-mcp.example.json](./cursor-mcp.example.json)

```json
{
  "mcpServers": {
    "openaiDeveloperDocs": {
      "url": "https://developers.openai.com/mcp"
    },
    "figma": {
      "url": "https://mcp.figma.com/mcp",
      "headers": {
        "Authorization": "Bearer ${FIGMA_OAUTH_TOKEN}",
        "X-Figma-Region": "us-east-1"
      }
    },
    "linear": {
      "url": "https://mcp.linear.app/mcp"
    }
  }
}
```

> Cursor 的 MCP JSON 格式可能隨版本演進；若 `headers` 不支援 env 展開，請在 IDE 的 MCP OAuth 流程中完成登入，或參考各技能內 `agents/openai.yaml` 的 `interface.tools` 定義。

## 相關連結

- [mcpservers.org — Anthropic](https://mcpservers.org/zh-TW/agent-skills/author/anthropic)
- [mcpservers.org — OpenAI](https://mcpservers.org/zh-TW/agent-skills/author/openai)
- [mcpservers.org — ScrapeGraphAI](https://mcpservers.org/zh-TW/agent-skills/author/scrapegraphai)
- [mcpservers.org — agent-browser](https://mcpservers.org/zh-TW/agent-skills/vercel/agent-browser)
