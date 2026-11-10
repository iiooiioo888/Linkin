# CONTRACT：UX-001 — HTTPS＋網域（代理拒純 HTTP IP）

> **狀態：** 契約／docs 碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不啟用產線 TLS）  
> **契約 ID：** `UX-001`  
> **runbook：** `docs/ops/ux-001-https-domain.md`  
> **example：** `docs/ops/snippets/nginx-ux-001-tls.example.conf`  
> **測試：** `backend/tests/test_ux_001_https_domain_docs.py`

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **問題** | 產線純 HTTP＋裸 IP；部分代理回 **400** |
| **本波** | shadow／docs：根因、DNS、nginx example、acme 清單、驗收；**不**真啟 TLS |
| **驗收（產品）** | 網域＋HTTPS；HTTP→HTTPS 301 |
| **≠** | 本 PR 啟用產線 443／申請憑證／改 WIRE／改 AuthGate／ModelGW |

## 不變式

1. `does_not_enable_tls_on_prod=true` — example.conf **不得**被當成已上線證明  
2. `wire_change=none` — 不改 `MODELGW_WIRE_MODE`／`.env` 切閘  
3. 倉庫 **無**私鑰／憑證實檔；`ssl_certificate_key` 僅 placeholder  
4. **不**改寫現網唯一啟用的 `listen 80` 行為（部署另授）  
5. `ready_to_merge=false`；「繼續」≠合並／部署授權  
6. 結案 UX-001 仍需真實網域＋**另授部署**

## 驗證

```bash
pytest backend/tests/test_ux_001_https_domain_docs.py -q
```

## 明確不做（本波）

- 真 ACME／certbot／產線 nginx reload  
- SSH 產線；合並；改 WIRE／HMAC／AuthGate／ModelGW 熱路徑  
- 提交 `.pem`／`.key`；路徑 A／Registry／關 L1  
