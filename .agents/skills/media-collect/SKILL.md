---
name: media-collect
description: 依名稱做跨平台公開社媒採集並交給 Media Vault 展示與監控。當用戶要從抖音、TikTok、小紅書、Instagram 或 X 找公開內容並入庫時使用。不負責登入或寫 Cookie。
---

# 跨平台採集（主技能）

編排層。原子工具契約在 [references/TOOLS.md](references/TOOLS.md)。架構順序見 `docs/integrations/crawl-skill-mcp.md`。

## 何時使用

- 用戶給出名稱、關鍵字或創作者，要跨平台找**公開**內容，並在 Media Vault（`#/modules/media-vault`）看到結果與監控。
- 只碰單一已接平台、且要走現成 HTTP／CLI 時，改用 `.agents/skills/mediacrawler/SKILL.md`。

## 步驟

1. **發現 MCP**  
   對照 `references/TOOLS.md` 與設計藍圖的平台判定（reuse／wrap／build）。  
   完成：每個目標平台標成「可呼叫的既有工具」或「缺口、停止該平台」。  
   設計期可選 `agent-discover`、`search-mcp-server`；它們不是本倉庫執行期依賴。

2. **呼叫平台工具**  
   只呼叫契約裡的 `search_*`，必要時再 `download_media`。參數限公開識別（關鍵字、作品 id、創作者 id）。  
   完成：每筆結果含平台、來源 URL、標題或說明；沒有工具就不假造內容。  
   抖音、小紅書優先 reuse `backend/mediacrawler` 與既有技能，不另寫爬蟲。

3. **交給 Media Vault 入庫概念**  
   將上一步整理成與 `backend/media_vault/ingest.py` 相容的欄位：平台、來源 URL、批次、合規標記（公開）。持久化仍由 Vault ingest（job 完成或 replay），本技能不直接寫 sqlite。  
   完成：列出將進入 `unified_posts`／`media_assets` 的欄位，並指向 Hub `#/modules/media-vault`（控制／監控／圖庫）。  
   展示與監控用既有 API，不在此新增端點。

## 禁止

- 不嵌入 Cookie、帳密、session、QR。
- 不把選擇器、簽名參數或繞過登入的步驟寫進本技能。
- 不在本技能內實作 MCP server 或新爬蟲。

## 相關

- 契約表：`references/TOOLS.md`
- 藍圖：`docs/integrations/crawl-skill-mcp.md`
- 入庫與 Hub：`docs/integrations/media-vault.md`
