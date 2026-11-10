# UX-001｜HTTPS＋網域運維 Runbook（shadow／docs）

**契約／票：** UX-001 · 代理對純 HTTP IP 回 400  
**性質：** 正式 ops runbook（**僅文件＋example.conf**；本 PR **不**啟用產線 TLS）  
**WIRE：** 本文件 **不**授權改 `MODELGW_WIRE_MODE`（`wire_change=none`）  
**旗標：** `ready_to_merge=false` · `does_not_enable_tls_on_prod=true` · `steal=false` · `wire_change=none`

> **硬口徑：** 本 PR **不**真申請憑證、**不**部署啟用 TLS、**不**改現網唯一啟用的 `listen 80` 行為、**不**SSH 產線。  
> 「繼續」≠合並／部署授權。結案 UX-001 仍需：**真實網域 DNS**＋**另授部署**（含 acme／reload）。

---

## 1. 根因

| 項 | 說明 |
| :--- | :--- |
| 現象 | 產線入口以純 HTTP＋裸 IP 對外（例：`http://47.82.83.20/`） |
| 代理行為 | 部分上游／CDN／企業代理對「純 HTTP＋IP Host」回 **400**（缺合法 Host／拒非 TLS／SNI 不符） |
| 驗收目標 | **網域＋HTTPS**（有效憑證、HTTP→HTTPS 301、Host＝網域） |
| 本票範圍 | shadow／docs：runbook＋nginx **example**＋契約摘要＋輕量存在性測試 |

**≠** 本票把「文件寫好」說成產線已 HTTPS；**≠** 改 `frontend/nginx.conf` 產線行為。

---

## 2. 前置：DNS

1. 選定公開網域（例：`app.example.com`；實際值由 Ops／PM 另定）。  
2. 於 DNS 供應商新增 **A**（或 **AAAA**）紀錄指向產線公網 IP（例：`47.82.83.20`）。  
3. 等待解析生效；本機驗證：

```bash
dig +short A app.example.com
# 預期：產線公網 IP
curl -sSI -H "Host: app.example.com" http://<產線IP>/ | head -n 20
```

4. **禁止**在未解析／未授部署時把 example.conf 直接覆蓋產線唯一啟用的 80 server。

---

## 3. nginx（example；非產線啟用檔）

倉庫內參考檔：

[`docs/ops/snippets/nginx-ux-001-tls.example.conf`](snippets/nginx-ux-001-tls.example.conf)

設計要點：

| 項 | 要求 |
| :--- | :--- |
| `listen 443 ssl` | TLS 終止於外層代理 |
| `server_name` | **placeholder**（如 `YOUR_DOMAIN.example`）；部署時替換 |
| 憑證路徑 | placeholder（`ssl_certificate`／`ssl_certificate_key`）；**倉庫不含私鑰** |
| HTTP→HTTPS | `listen 80` 對該 `server_name` 回 **301** 至 `https://$host$request_uri` |
| 既有 80 行為 | example **另開**可選 server 區塊；**不**改寫現網「唯一啟用 80」的預設站行為（部署另授） |
| HSTS | 可選；僅在 HTTPS 穩定後另授開啟 |

**明確：** 本檔為 **example**；複製到產線 `/etc/nginx/...` 與 `nginx -t`／reload **需另授**。

---

## 4. ACME／憑證（另授；本 PR 不做）

建議路徑（擇一；實際工具依產線）：

1. **certbot**（nginx plugin 或 webroot）對 `YOUR_DOMAIN` 簽 Let’s Encrypt。  
2. 或雲廠商憑證＋手動掛載 PEM。

檢查清單（部署票用）：

- [ ] DNS 已指向產線  
- [ ] 80／443 防火牆允許 ACME 與訪客  
- [ ] 私鑰僅機上、權限受限、**不**進 git  
- [ ] `nginx -t` 通過後再 reload  
- [ ] `curl -sSI https://YOUR_DOMAIN/` 回 200／302（業務預期）且憑證鏈完整  

本 PR：**不**執行 certbot、**不**寫入產線憑證路徑實值、**不**提交任何 `.pem`／`.key`。

---

## 5. HTTP→HTTPS 與驗收

### 5.1 預期行為（部署後）

| 請求 | 預期 |
| :--- | :--- |
| `http://YOUR_DOMAIN/` | **301** → `https://YOUR_DOMAIN/` |
| `https://YOUR_DOMAIN/` | 業務 200／入口頁；有效憑證 |
| `http://<裸IP>/` | 依部署策略：維持既有 80 站 **或** 另授改為引導／拒絕（本 PR **不**改） |
| 代理經 HTTPS＋網域 | **不再**因純 HTTP IP 觸發 400（UX-001 結案條件） |

### 5.2 驗收指令（部署票）

```bash
# 301
curl -sSI http://YOUR_DOMAIN/ | grep -iE 'HTTP/|Location:'

# TLS
curl -sSI https://YOUR_DOMAIN/ | head -n 15
echo | openssl s_client -servername YOUR_DOMAIN -connect YOUR_DOMAIN:443 2>/dev/null \
  | openssl x509 -noout -subject -dates
```

### 5.3 本 PR 可驗（文件／example）

```bash
pytest backend/tests/test_ux_001_https_domain_docs.py -q
```

斷言：runbook／契約／example 存在；含 `listen 443 ssl`、`301`、`does_not_enable_tls_on_prod`；**無**私鑰材料。

---

## 6. 明確不做（本 PR）

- 真申請／續期憑證；寫入產線 nginx 啟用檔  
- SSH／部署／reload 產線；改 WIRE／`.env` 閘  
- 改 `frontend/nginx.conf` 為唯一產線 443 行為  
- 改 AuthGate／ModelGW 熱路徑  
- 合並本 PR（`ready_to_merge=false`）；路徑 A／Registry／關 L1  
- 提交私鑰、完整憑證鏈、帳密  

---

## 7. 殘差／結案條件

| 殘差 | 狀態 |
| :--- | :--- |
| 真實網域選定＋DNS | **未做**（本 PR 外） |
| ACME＋產線 nginx 啟用 | **未做**；需 **另授部署** |
| UX-001 產品結案 | 僅在網域＋HTTPS 驗收通過後由 PM／Ops 關閉 |

**本文件落地 ≠ UX-001 已關。**
