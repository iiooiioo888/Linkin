# 工具契約（尚未實作）

名稱是主技能 `media-collect` 的呼叫契約，不是已註冊的 MCP。實作留待後續 PR。禁止在呼叫中帶 Cookie、帳密或 session。

| 名稱 | 參數 | 平台 | 合規 |
| --- | --- | --- | --- |
| `search_douyin` | `query` 或 `creator_id`；可選 `limit` | 抖音（reuse MediaCrawler `dy`） | 僅公開搜尋／創作者頁；遵守平台條款 |
| `search_tiktok` | `query` 或 `creator_id`；可選 `limit` | TikTok（wrap，尚無倉庫內實作） | 同上；無工具則回報缺口 |
| `search_xhs` | `query` 或 `creator_id`；可選 `limit` | 小紅書（reuse MediaCrawler `xhs`） | 僅公開筆記與創作者 |
| `search_instagram` | `query` 或 `creator_id`；可選 `limit` | Instagram（build） | 無官方公開契約前不得抓取 |
| `search_x` | `query` 或 `creator_id`；可選 `limit` | X（build） | 同上 |
| `download_media` | `platform`、`source_url`、`asset_url` | 上表已成功搜尋的平台 | 只下載該筆公開媒體 URL；檔案落點交給 Media Vault ingest，不另開寫入路徑 |

入庫不在此表：由 `backend/media_vault/ingest.py` 消費採集結果目錄，Hub 為 `#/modules/media-vault`。
