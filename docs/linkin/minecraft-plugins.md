# Minecraft 第三方插件與內嵌地圖

Linkin 面板可整合伺服器上常見的網頁地圖插件（Dynmap、BlueMap、Squaremap），在 **Minecraft → 插件／地圖** 分組中設定 URL 並內嵌檢視。

## 面板入口

| 頁面 | 路徑 | 說明 |
|------|------|------|
| 插件中心 | `#/modules/minecraft/plugin-hub` | 插件目錄、安裝提示、URL 設定、探測 |
| 伺服器地圖 | `#/modules/minecraft/server-map` | iframe 內嵌已設定的地圖 |

舊書籤別名：`#/monitor/map`、`#/monitor/plugins` 會解析到上述頁面。

## 快速設定（Dynmap / BlueMap）

1. 在 Paper 伺服器安裝對應插件並確認網頁地圖可從瀏覽器公開存取（例如 `https://map.yourdomain.com/`）。
2. 打開 Linkin → **Minecraft** → **插件中心**。
3. 找到 **Dynmap**（或 BlueMap / Squaremap），勾選「啟用」，填入 **公開地圖 URL**。
4. 點 **探測 URL** 確認 HTTP 可達；再點 **設為預設地圖**。
5. 進入 **伺服器地圖** 即可在面板內查看；可用全螢幕、重載、新分頁開啟。

設定保存在後端 `EVOL_LINKIN_DATA_DIR/minecraft_plugin_settings.json`，不會寫入前端。

## API

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/linkin/minecraft/plugins/catalog` | 插件目錄與連線狀態 |
| GET | `/linkin/minecraft/plugins/settings` | 已保存設定 |
| PUT | `/linkin/minecraft/plugins/settings` | 更新啟用、URL、預設地圖插件 |
| POST | `/linkin/minecraft/plugins/{id}/probe` | 對地圖 URL 做 HEAD/GET 健康檢查 |

前端經模組閘道：`/modules/minecraft/api/minecraft/plugins/...`

`GET /linkin/minecraft/status` 的 `plugins` 欄位會摘要地圖插件狀態，供 AI 觀測與監控使用。探測與設定變更會寫入 `linkin_events` 集合。

## 反向代理（iframe 被阻擋時）

部分地圖站點設定 `X-Frame-Options: SAMEORIGIN` 或 CSP `frame-ancestors`，無法被 Linkin 跨域嵌入。可將地圖反代到 Linkin 同源路徑，例如 nginx：

```nginx
location /minecraft-map/ {
    proxy_pass http://127.0.0.1:8123/;
    proxy_set_header Host $host;
    # 視需要移除或覆寫 X-Frame-Options
    proxy_hide_header X-Frame-Options;
}
```

再在插件中心填寫 `https://linkin.example.com/minecraft-map/`。

## URL 安全策略

探測端點僅允許 `http`/`https`，並阻擋：

- 私有／迴圈／鏈路本機 IP
- `localhost` 與 `metadata.google.internal`
- 雲端 metadata `169.254.169.254`

請勿將內網地圖 URL 填給可被濫用的探測 API；生產環境建議只填公開 HTTPS 位址，或透過同源反代。

## 相關文件

- [minecraft-mcp.md](./minecraft-mcp.md) — MineMCP 橋接（方塊放置、指令）
- [api.md](./api.md) — 靈境 REST 總覽
