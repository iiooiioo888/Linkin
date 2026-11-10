# CONTRACT：Align R3 — AuthGate→tenant 自動注入殘差

> **狀態：** 契約碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `ALIGN-R3`  
> **實作：** `backend/core/align_r3_authgate_tenant.py`  
> **測試：** `backend/tests/test_align_r3_authgate_tenant.py`  
> **父錨：** Issue #148 talk §4；align-spec §10.1 R3；`modelgw-p5-admit-tenant-spec` Q7

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **本波** | AuthGate→tenant **自動注入殘差契約**（可測 allow／block／would_inject_blocked＋shadow） |
| **允許來源** | `explicit`／`http_body`（tenant 字串含 `""`） |
| **≠** | 真 AuthGate 接線／改 admit 熱路徑／宣稱已注入（`does_not_wire_real_authgate=True`） |

談結 ≠ 真注入兌現；「繼續」≠合並授權。P5 Q7 殘差＝本契約紙面邊界，**非**本波交付真映射。

## 不變式

1. 來源 `explicit`／`http_body` → **allow**（`tenant_id` 可為 `""`；現行 C 類口徑）
2. 來源 `authgate_session`／`header_guess`／`cookie` → **`would_inject_blocked`**；shadow 記錄；**`tenant_injected` 恒為 `False`**
3. 缺來源且 `tenant_required=True` → fail-closed **block**（不猜）
4. 異 tenant 交叉（`cross_tenant_id` ≠ `tenant_id`）→ **block**
5. 未知來源 → **block**（不猜）
6. `wire_change="none"`；不改環境、不 import 改 WIRE、不改 admit 熱路徑

## 評估產出

| `verdict` | 含義 |
| :--- | :--- |
| `allow` | 顯式／HTTP body（或未要求 tenant 的缺來源空路徑 `""`） |
| `block` | 缺來源／異 tenant／未知來源 fail-closed |
| `would_inject_blocked` | AuthGate／header／cookie 類：本會注入但契約擋下；未注入 |

## 驗證

```bash
pytest backend/tests/test_align_r3_authgate_tenant.py -q
```

## 明確不做（本波）

- 真 AuthGate／session→tenant 接線（`does_not_wire_real_authgate=True`）
- 改 admit／route／chat 熱路徑（`does_not_mutate_admit_hotpath=True`）
- 改 `MODELGW_WIRE_MODE`（維持 enforce；`wire_change=none`）
- R5／路徑 A／G-GATE1／L2／關 L1
- Cap-3／Cap-4／full Cap-2 擴張／真 aider／真 runsc
- 合並／部署／改 HMAC／sql／map／TOOL_DUAL／llm_config／role_catalog／CI／Ruff／frontend
- Fusion Bus 第三電路；LangGraph 替換 Scheduler＋Unit Bus
