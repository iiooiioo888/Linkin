---
name: mediacrawler
description: 多平台公開社媒資料採集（小紅書、抖音、快手、B站、微博、貼吧、知乎）。當用戶需要爬取公開社媒內容、關鍵詞搜尋、創作者主頁或帖子詳情時使用，例如「爬小紅書關鍵詞」「抓取抖音創作者資料」。
---

# MediaCrawler 多平台採集

開源多平台公開社媒資料採集工具（Playwright），上游：[NanmiCoder/MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)。

> **法律聲明**：僅供學習與研究，請遵守各平台服務條款與 robots 規則，僅採集公開資料，使用者自行承擔法律責任。

## Linkin 環境（推薦）

1. **控制台 UI**：`#/monitor/skills` →「MediaCrawler 採集」卡片。
2. **HTTP API**：
   - `GET /mediacrawler/status` — 整合狀態（已安裝／需配置／已啟用）
   - `POST /mediacrawler/jobs/validate` — 配置校驗（乾跑）
   - `POST /mediacrawler/jobs` — 啟動採集任務
   - `GET /mediacrawler/jobs` — 任務列表
   - `GET /mediacrawler/jobs/{id}` — 任務狀態與日誌
   - `GET /mediacrawler/jobs/{id}/results` — 結果檔案列表
3. **啟用**：伺服器設定 `EVOL_MEDIACRAWLER_ENABLED=true` 並配置 `MEDIACRAWLER_HOME`。

## 伺服器前置

```bash
# Python 3.11+、uv、Node.js 16+
git clone https://github.com/NanmiCoder/MediaCrawler.git /opt/MediaCrawler
cd /opt/MediaCrawler && uv sync && uv run playwright install

export MEDIACRAWLER_HOME=/opt/MediaCrawler
export EVOL_MEDIACRAWLER_ENABLED=true
```

## 支援平台與類型

| 平台 | `--platform` | 搜尋 | 詳情 | 創作者 |
|------|-------------|------|------|--------|
| 小紅書 | `xhs` | search | detail | creator |
| 抖音 | `dy` | search | detail | creator |
| 快手 | `ks` | search | detail | creator |
| B站 | `bili` | search | detail | creator |
| 微博 | `wb` | search | detail | creator |
| 貼吧 | `tieba` | search | detail | creator |
| 知乎 | `zhihu` | search | detail | creator |

## 登入方式

- **Cookie（v1 支援）**：在 Linkin UI 或 API 配置 Cookie 字串，對應 `--lt cookie`。
- **QR 碼（需人工）**：在伺服器上直接執行 `uv run main.py --platform xhs --lt qrcode`，掃碼後 Cookie 會緩存於 MediaCrawler 目錄；Linkin API 不代為彈出 QR。

## 典型 CLI（上游）

```bash
cd $MEDIACRAWLER_HOME
uv run main.py --platform xhs --lt cookie --type search
uv run main.py --platform dy --lt cookie --type detail
uv run main.py --help
```

## 輸出格式

MediaCrawler 原生支援 CSV、JSON、JSONL、Excel、SQLite。Linkin 任務完成後可在 UI 或 API 瀏覽結果目錄中的檔案。

## 注意

- 預設 **停用**（`EVOL_MEDIACRAWLER_ENABLED` 未設或 `false`）；乾跑校驗仍可用。
- 並發上限 1–2 個任務；結果目錄受路徑牢籠保護。
- 勿將 Cookie 或密碼提交至 Git；僅存於伺服器運行時配置。
