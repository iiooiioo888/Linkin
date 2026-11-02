# CONTRACT：Align R5 — nginx `/modelgw` 暴露與雙電路共享邊界

> **狀態：** 契約碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `ALIGN-R5`  
> **實作：** `backend/core/align_r5_nginx_modelgw.py`  
> **測試：** `backend/tests/test_align_r5_nginx_modelgw.py`  
> **父錨：** Issue #148 talk §5；align-spec §10.1 R5；G-X1

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **本波** | nginx `/modelgw` location 暴露與雙電路共享 **正交後置邊界契約**（可測 allow／block／orthogonal_deferred／would_share＋shadow） |
| **允許意圖** | `docs_observe`／`contract_eval`（僅評估合法；不觸碰實檔） |
| **≠** | 真改 nginx／compose／入口路由／雙電路接線（`does_not_modify_nginx=True`） |

談結 ≠ 真改 nginx；「繼續」≠合並授權。G-X1 基礎設施＝另票；與 Align／Cap **分欄**。

## 不變式

1. 意圖 `docs_observe`／`contract_eval` 且 `infra_auth_flag=True` → **allow**（永不宣稱已改 nginx）
2. 意圖 `expose_modelgw_location`／`nginx_location_open` → **`orthogonal_deferred`**；shadow 記 `would_expose`；**`nginx_modified` 恒為 `False`**
3. 意圖 `share_dual_circuit`／`dual_circuit_merge` → **`would_share_dual_circuit`**；對齊 L5 禁第三電路精神；**`dual_circuit_wired` 恒為 `False`**
4. 缺 `infra_auth_flag` → fail-closed **block**（不猜）
5. 未知／缺意圖 → **block**（不猜）
6. `wire_change="none"`；不改環境、不改 nginx／compose／入口路由實檔

## 評估產出

| `verdict` | 含義 |
| :--- | :--- |
| `allow` | 僅文件／契約觀測：評估請求本身合法 |
| `block` | 缺 infra 授權／未知意圖 fail-closed |
| `orthogonal_deferred` | 暴露 `/modelgw`：與 Align 正交後置；未改 nginx |
| `would_share_dual_circuit` | 雙電路共享：本會共享但契約擋下；未接線 |

## 驗證

```bash
pytest backend/tests/test_align_r5_nginx_modelgw.py -q
```

## 明確不做（本波）

- 改 nginx／compose／入口路由實檔（`does_not_modify_nginx=True`）
- 雙電路共享真接線（`does_not_wire_dual_circuit=True`）
- 改 `MODELGW_WIRE_MODE`（維持 enforce；`wire_change=none`）
- 路徑 A／G-GATE1／L2／關 L1
- 真 AuthGate 擴張／R3 以外接線
- Cap-3／Cap-4／full Cap-2 擴張／真 aider／真 runsc
- 合並／部署／改 HMAC／sql／map／TOOL_DUAL／llm_config／role_catalog／CI／Ruff／frontend
- Fusion Bus 第三電路；LangGraph 替換 Scheduler＋Unit Bus
- G-X1 基礎設施真碼（`gx1_infra_separate_ticket=True`；另票）
