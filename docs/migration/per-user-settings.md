# 每帳號設定隔離（API／整合／實驗室）

## 為什麼

先前 LLM 金鑰、路由、目錄刷新間隔寫在同一份 `EVOL_CONFIG_DIR/llm_config.json`，
並同步到程序環境變數 `OPENAI_API_KEY`。任何登入帳號的儲存都會蓋掉其他人，
下一個請求還可能沿用上一個人留在環境變數裡的金鑰。

角色目錄、技能覆寫、計費在 #91 已按 `user_id` 分開。這次把**會隨登入改變的設定**對齊同一把鑰匙。

## 現在怎麼存

| 表面 | 已登入 | 未綁定租戶（腳本、背景） |
| --- | --- | --- |
| API 金鑰、路由、模型勾選、目錄刷新間隔 | `EVOL_USER_SETTINGS_DIR/<user_id>/llm_config.json` | 仍是 `llm_config.json` + 環境變數 |
| 外部整合啟用／網址／金鑰 | `<user_id>/integrations.json` | 環境變數；無租戶時切換只活在程序內 |
| 實驗室 MCP 開關 | `<user_id>/lab.json` | `user_settings/_platform/lab.json` |
| 公司後反思覆寫 | `<user_id>/reflect.json` | `cost_speed.json`（路由表本身仍是平台檔） |
| 向量記憶／JSON 記憶 | 帳號自己的 collection 與檔 | 原 `evo_memory`／`EVOL_MEMORY_STORE_PATH` |
| 採集 Cookie | `<user_id>/mediacrawler.json` | 原 `runtime.json` |

已登入的 API 設定**不繼承**平台金鑰、其他帳號的端點或 `OPENAI_API_KEY`。
成本路由（公司／個人路徑）仍讀平台 `cost_speed.json`；只有「公司後反思」模式可以按帳號覆寫，而且環境變數 `EVOL_POST_COMPANY_REFLECT` 仍優先於所有帳號。

Hub、雲端、檢查點、資料庫連接池、Minecraft 伺服器是這台服務的基礎設施，不是帳號秘密，維持共用。

回應裡的金鑰維持既有脫敏（`masked_key`／cookie preview）。閘門開啟時，未帶會話的寫入回 401。

## 既有全域檔怎麼遷移（不刪秘密）

啟動時呼叫 `migrate_legacy_user_settings`：

1. 若 `llm_config.json` 有內容，且遺留擁有者還沒有自己的檔，**複製**過去。
2. 採集 `runtime.json` 裡的 cookie 同樣只複製一次。
3. **不刪除、不覆寫**來源檔。沒有擁有者檔時，腳本與未綁定租戶的呼叫仍讀得到原來的金鑰。
4. 其他帳號保持空白，直到自己儲存。

遺留擁有者優先序：

1. `EVOL_SETTINGS_LEGACY_OWNER`（你的閘門使用者名稱）
2. 否則 `LINKIN_GATE_ID`
3. 否則 `deploy_admin`（與角色目錄遷移相同）

生產升級前請把 `EVOL_SETTINGS_LEGACY_OWNER` 設成實際登入名稱，重啟一次。
若已經重啟過、檔在 `deploy_admin` 而登入名稱不同：來源 `llm_config.json` 還在，設好環境變數再重啟即可再複製（只在目標檔不存在時複製）。

多個真人帳號可設 `LINKIN_GATE_ACCOUNTS`（JSON 陣列或檔案路徑）：

```json
[
  {"username": "alice", "secret": "請換成密語"},
  {"username": "bob", "secret": "請換成另一組"}
]
```

這與原本的單一 `LINKIN_GATE_ID`／`LINKIN_GATE_SECRET` 並存。密語不要寫進 Git。

## 驗收

- `pytest backend/tests/test_per_user_settings.py`
- 兩個帳號 A、B 登入後，A 在「API 路由」儲存金鑰；B 重新整理同一頁，不應看到 A 的路由名稱、脫敏金鑰或「已配置」。
- B 啟用 MemOS 或改實驗室開關，A 重新整理應仍是自己的值。
