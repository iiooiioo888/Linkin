# CONTRACT：G-GATE1 — 雙閘時序手冊（宣導落地）

> **狀態：** 文件／宣導落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `G-GATE1`  
> **性質：** 對人宣導與口徑契約（**不是** Align 式 runtime evaluate／shadow contract）  
> **父錨：** P4-S2 acceptance §5；碼註解 `hub/catalog.py`／`hub/service.py`／`modelgw/runtime.py`  
> **產線錨：** HEAD `caba36c`；WIRE=enforce；L1 繼續

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **本波** | 雙閘時序口徑落地：Hub＝B 濾鏡；ModelGW＝唯一準入權威 |
| **允許** | docs／FAQ／註解對齊；觀測既有 enforce 行為 |
| **≠** | 改閘邏輯、切 WIRE、合並部署、關 L1、開 L2、碰路徑 A、改 nginx／雙電路 |

宣導落地 ≠ 改閘；「繼續」≠合並授權。`wire_change=none`；`steal=false`。

## 運維一句（必背）

**Hub 拒 ≠ ModelGW 拒；ModelGW 拒才是準入權威結果。**

## 時序

```
客戶端／產品
  → [可選] Hub validate_model_id／目錄／電路   ← B 層產品濾鏡（可長期保留）
  → call_llm／call_llm_stream／_llm_probe
  → ModelGW precheck_model（WIRE=enforce）   ← 唯一「能不能叫」準入權威（READY∧O18∧tenant）
  → 上游
```

## 雙閘角色

| 層 | 角色 | 不得 |
| :--- | :--- | :--- |
| Hub `validate_model_id`／catalog | **B**：產品目錄濾鏡（可長期保留） | 替代 O18／READY 準入權威；把 Hub 拒說成 ModelGW 拒 |
| ModelGW `precheck_model`／admit（WIRE=enforce） | **唯一「能不能叫」準入權威** | 被 Hub 目錄「綠」繞過 |
| Hub 電路／探針 | 運維視圖；與 ModelGW **隔離** | 本波合併成單一電路狀態 |

## 不變式

1. Hub `validate_model_id`＝**B 層產品濾鏡**；**不是** ModelGW 準入權威
2. ModelGW `precheck_model`（WIRE=enforce）＝**唯一「能不能叫」準入權威**
3. Hub 目錄綠 **不得** 繞過 ModelGW admit（enforce 下）
4. Hub 拒 ≠ ModelGW 拒；不得把二者說成同一結果
5. 不得合併 Hub 電路狀態與 ModelGW 準入為單一「能不能叫」燈號
6. `wire_change="none"`；本文件不授權改環境、nginx、雙電路、HMAC、map、TOOL_DUAL、sql

## 與碼面錨點

| 檔案 | 錨 |
| :--- | :--- |
| `backend/hub/catalog.py` → `validate_model_id` | G-GATE1：B 濾鏡；非準入權威 |
| `backend/hub/service.py` → `_llm_probe` | 雙閘時序；目錄綠不得繞過 |
| `backend/modelgw/runtime.py` 模組 docstring | precheck＝唯一權威 |

## 明確不做（本波）

- 合並／部署／SSH 產線
- 改 `MODELGW_WIRE_MODE`（維持產線 enforce；`wire_change=none`）
- 關 L1；開 L2；碰路徑 A
- 改 nginx／compose／入口路由／雙電路接線（`does_not_modify_nginx=True`）
- 改 map／HMAC／TOOL_DUAL／sql／`llm_config.json`／`role_catalog.json`／CI／Ruff／frontend
- 新增 Align 式 runtime evaluate 模組或改 admit／precheck 行為

## 旗標

`ready_to_merge=false`｜`wire_change=none`｜`steal=false`｜`does_not_modify_nginx=true`｜`l1_continue=true`

合並／部署／改 WIRE／關 L1／路徑 A／L2 須用戶另句明確授權。
