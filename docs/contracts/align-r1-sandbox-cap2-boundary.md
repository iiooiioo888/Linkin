# CONTRACT：Align R1 — runsc／沙箱硬邊界＝Cap-2 碼波邊界

> **狀態：** 契約碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `ALIGN-R1`  
> **實作：** `backend/core/align_r1_sandbox_boundary.py`  
> **測試：** `backend/tests/test_align_r1_sandbox_boundary.py`  
> **父錨：** Issue #148／#140；`align-residual-talk-ticket-20261101` §3；align-spec §3 可保留沙箱硬邊界、§7.2、§10.1 R1

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **本波** | 沙箱硬邊界**契約**落地（可測 allow／block／abort＋shadow） |
| **歸屬** | Cap-2 碼波**邊界**（`cap2_boundary_only=True`） |
| **≠** | 已兌現 Cap-2 全量（`does_not_implement_full_cap2=True`） |

談結 ≠ 已兌現 Cap-2 全量；「繼續」≠合並授權。

## 硬邊界不變式

1. `runtime` **必須** `runsc`
2. `network` **必須** `none`（`network=none`）
3. token／secret **不**進沙箱
4. secret scan 失敗 → **擋 Delivery**（`block`）
5. sandbox abort → **fail-closed**（`abort`；**不開 draft**）
6. 本契約 allow **亦不**自動開 draft PR

## 評估產出

| `verdict` | 含義 |
| :--- | :--- |
| `allow` | 硬邊界全過 |
| `block` | 硬邊界違規擋下 |
| `abort` | sandbox abort；不開 draft |

## 驗證

```bash
pytest backend/tests/test_align_r1_sandbox_boundary.py -q
```

## 明確不做（本波）

- aider／真碼生成器接入
- 真 Docker／runsc 起容器
- draft PR 自動開
- 24 QA 骨架納入 ModelGW CI 必過
- R3／R5／Cap 全量真碼
- 合並／部署／改 `MODELGW_WIRE_MODE`（維持 enforce）
- 路徑 A／G-GATE1／L2／關 L1
- Fusion Bus 第三電路；LangGraph 替換 Scheduler＋Unit Bus
