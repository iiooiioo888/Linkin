# 靈境·Linkin 服務安全檢查

檢查日期：2026-10-23（澳門時間）

範圍：這個倉庫裡會跑起來的服務（`backend`、`opc_service`、`frontend` nginx、`docker-compose.yml`）。沒有連上你的線上主機，沒有掃埠，也沒有對登入摘要做猜測。

假設：若生產環境直接使用本倉庫的 Compose，且 `8000`、`8001`、`6379`、`8100`、`3001` 能從本機以外連到，下面的嚴重度成立。若這些埠只綁在迴圈位址，而且已經用環境變數換掉預設閘門帳密，嚴重度要下調。

## 修復狀態

2026-10-23（澳門時間）已在程式裡處理下面六項。後面的章節保留當時的發現，方便對照。

1. 預設帳密與前端還原邏輯已移除。未設定 `LINKIN_GATE_ID` 與 `LINKIN_GATE_SECRET` 時登入拒絕。
2. Redis、Chroma、OPC 的宿主埠改綁 `127.0.0.1`。Redis 要 `REDIS_PASSWORD`。Chroma 映像釘在 `1.0.0`。OPC 讀寫要 `OPC_INTERNAL_TOKEN`，正式 Compose 關掉模擬伺服器。
3. 登入回應不再帶權杖。Cookie 只在 HTTPS 時加 Secure。查詢參數 `gate` 不再當權杖。
4. OpenAPI 預設關閉。`LINKIN_ENABLE_DOCS=1` 才掛上，而且仍要先登入。
5. 前端 nginx 加上內容安全政策、`X-Frame-Options`、`X-Content-Type-Options`、`Referrer-Policy`。
6. `python -m opc_service.main` 不再以 `reload=True` 啟動。

部署前要在 `.env` 填上閘門帳密、`REDIS_PASSWORD`（並寫進 `REDIS_URL`）和 `OPC_INTERNAL_TOKEN`。GitHub Pages 這類沒有後端的靜態站不再用瀏覽器裡的秘密放行。

## 摘要

最大的問題不是單一程式錯誤，而是預設登入材料會跟著前端一起送出，旁邊的 Redis、向量庫和 OPC 寫入服務又沒有同一道登入閘門。閘門打開之後，持有這把鑰匙的人可以改模型金鑰、下任務、寫世界資料。OPC 寫入服務自己不查這把鑰匙。

## Critical

### 1. 預設閘門帳密可從前端還原

- Rule ID: FASTAPI-AUTH-001／REACT-CONFIG-001
- Severity: Critical
- Location: `frontend/src/lib/gateDigest.ts` `peel`（約第 32–33、48–70 行）；`backend/auth/gate.py` `_expected_user`／`_expected_secret`（約第 30–69、173–185 行）
- Evidence: 前端用 `ID_PARTS`、`SECRET_PARTS` 和固定 pepper 在瀏覽器裡還原預設帳密，再與後端寫死的 HMAC 摘要比對。只有設定 `LINKIN_GATE_ID` 與 `LINKIN_GATE_SECRET` 才會改走環境變數。`LINKIN_AUTH_DISABLED=1` 會把整道閘門關掉。
- Impact: 任何能讀到網站腳本的人都可以登入仍使用預設值的服務，接著呼叫 `/config` 更換模型金鑰、建立任務、寫入實體。
- Fix: 生產環境必須設定 `LINKIN_GATE_ID` 與 `LINKIN_GATE_SECRET`，並從前端建置移除 `peel` 與預設片段。靜態站不應在瀏覽器裡核對真正的登入秘密。
- Mitigation: 在確認已改掉預設值之前，不要把 `3001` 或 `8000` 暴露到公網。不要設定 `LINKIN_AUTH_DISABLED`。
- False positive notes: 若部署已經覆寫這兩個環境變數，預設摘要不會再生效。前端腳本裡的還原邏輯仍然不該留在公開網站。

### 2. Redis、Chroma、OPC 寫入埠沒有應用閘門

- Rule ID: FASTAPI-AUTH-001／FASTAPI-CORS-001
- Severity: Critical
- Location: `docker-compose.yml` Redis `6379`（約第 143 行）、Chroma `8100`（約第 171 行）、OPC `8001`（約第 108 行）；`opc_service/app.py` `create_app`（約第 49–67 行）；`opc_service/routes/write.py` `write_tags`
- Evidence: Compose 把這三個服務發布到宿主埠。Redis 與 Chroma 的服務定義裡沒有密碼。OPC 應用允許任意來源的 CORS，寫入路由沒有登入檢查。Compose 還把 `OPC_SIM_ENABLED` 設為 true。
- Impact: 能連到這些埠的人可以讀寫任務與向量資料，或對 OPC 標籤送出寫入。寫入仍會經過白名單與數值邊界，但呼叫者不必先登入靈境。
- Fix: 資料庫與 OPC 只留在 Compose 網路內，不要映射到宿主埠。OPC 寫入改由已登入的後端轉送。Redis 加上密碼，Chroma 不要用 `latest` 浮動標籤。模擬伺服器不要開在會對外的部署。
- Mitigation: 用防火牆只允許本機連 `6379`、`8001`、`8100`。
- False positive notes: 若你實際的部署沒有發布這些埠，這項不適用於那台機器。本倉庫的 Compose 檔會發布它們。

## High

### 3. 登入權杖放在 localStorage，Cookie 未標成只走 HTTPS

- Rule ID: REACT-AUTH-001／FASTAPI-SESS-001
- Severity: High
- Location: `backend/main.py` `auth_login` 與 `_set_gate_cookie`（約第 479–497 行）；`frontend/src/lib/auth.ts` `writeRecord`（約第 45–46 行）；`backend/auth/gate.py` `extract_token`（約第 135–141 行）
- Evidence: 登入回應把權杖放進 JSON。前端再寫進 `localStorage`。Cookie 的 `secure` 固定為 false。權杖也可以放在查詢參數 `gate` 裡通過。
- Impact: 一旦頁面被注入腳本，權杖會被讀走。權杖出現在網址時，還可能進到代理日誌或 Referer。沒有 HTTPS 時，同一網路上的人可以看見 Cookie。
- Fix: 權杖只放在 `HttpOnly`、`Secure`、`SameSite` Cookie。生產環境依請求是否為 HTTPS 開啟 `secure`。停止接受查詢參數裡的權杖。
- Mitigation: 在 nginx 強制 HTTPS，並加上內容安全政策。
- False positive notes: 前端目前沒有搜到 `dangerouslySetInnerHTML`。權杖存放方式仍然不符合基線，嚴重性取決於有沒有別的注入點。

### 4. 互動文件與 OpenAPI 不需登入

- Rule ID: FASTAPI-OPENAPI-001
- Severity: High
- Location: `backend/middleware/auth_gate.py` `_OPEN_EXACT`（約第 11–22 行）；`backend/main.py` `FastAPI(...)`（約第 262–267 行，未關閉 `docs_url`／`openapi_url`）
- Evidence: `/docs`、`/redoc`、`/openapi.json` 在閘門的公開名單裡。應用建立時也沒有關掉文件。
- Impact: 未登入的人可以讀到全部路由形狀，用來對照後面的管理介面。
- Fix: 生產環境設定 `docs_url=None`、`redoc_url=None`、`openapi_url=None`，並從公開名單移除這三條路徑。
- Mitigation: 在反向代理擋下這些路徑。
- False positive notes: 開發機保留文件是合理的。這項針對會對外的部署。

## Medium

### 5. 前端沒有內容安全政策，入口只聽 HTTP

- Rule ID: REACT-CSP-001／REACT-HEADERS-001／FASTAPI-HEADERS-001
- Severity: Medium
- Location: `frontend/nginx.conf`（約第 6–8、36–45 行）
- Evidence: nginx 只 `listen 80`。設定裡沒有 `Content-Security-Policy`、`X-Frame-Options`、`X-Content-Type-Options` 或 `Referrer-Policy`。
- Impact: 瀏覽器少了一層對注入腳本和被嵌進其他網站的限制。與第 3 項疊加時，權杖更容易被帶走。
- Fix: 終止 TLS，並在回應加上上述標頭。內容安全政策不要使用 `unsafe-inline` 與 `unsafe-eval`，除非建置方式必須如此並寫明原因。
- Mitigation: 先在外層代理補上標頭與 HTTPS。
- False positive notes: 若外層已有另一台代理負責 TLS 與標頭，應用內的 nginx 可以只當上游。目前倉庫裡的這份設定沒有這些標頭。

### 6. OPC 行程以自動重載啟動

- Rule ID: FASTAPI-DEPLOY-001
- Severity: Medium
- Location: `opc_service/main.py` `__main__`（約第 27–31 行）
- Evidence: 直接執行 `python -m opc_service.main` 時，uvicorn 使用 `reload=True`。
- Impact: 這是開發伺服器行為。檔案變更會重啟行程，不適合當作對外服務的啟動方式。
- Fix: 正式啟動不要帶 `reload`。用與後端 Dockerfile 相同的單次 uvicorn 指令。
- Mitigation: 只用 Compose 裡固定的啟動指令，不要在生產機手動跑這個模組。
- False positive notes: Compose 若使用映像自己的指令而不是這段 `__main__`，這項只影響手動啟動。

## 已看過、目前沒有當成漏洞的部分

- 後端 HTTP 閘門在未關閉時會擋下 `/config`、任務與多數管理路由。`/health` 與 `/auth/login` 是刻意公開的。
- `GET /config` 回傳的模型金鑰有做遮罩。
- MediaCrawler 以參數陣列啟動行程，沒有 `shell=True`。
- 前端沒有搜到 `dangerouslySetInnerHTML`。
- 公司任務的 OPC 寫入路徑另有白名單與數值邊界。那道檢查不能代替「呼叫者必須先登入」。

## 建議先做的三件事

1. 換掉預設閘門帳密，並從前端移除可還原的預設片段。
2. 取消 Redis、Chroma、OPC 的宿主埠映射，或至少用防火牆限制來源。
3. 權杖改只放在安全 Cookie，並關掉公開的 OpenAPI。
