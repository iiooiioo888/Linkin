# CONTRACT：Align G-C2 — Delivery 宣稱 vs O10 合入（分票對表）

> **狀態：** 契約碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `ALIGN-G-C2`  
> **實作：** `backend/core/align_g_c2_authority.py`  
> **測試：** `backend/tests/test_align_g_c2_authority.py`  
> **父錨：** Issue #148／#140；`code-ops-domain-plugin-align-docs-patch-20261030` §3.3；align-spec §7.3

## 一句精神

| 權威 | 管什麼 | 不管什麼 |
| :--- | :--- | :--- |
| **DeliveryClaimAuthority**（領域） | 能否**宣稱交付**（fail-closed） | 能否合入主線 |
| **O10MergeAuthority**（DAG／O10） | 能否**合入** | 能否宣稱領域交付 |

**對表、不合併碼波**（`map_not_merge`）。Delivery succeeded **≠** 自動 O10 allow。

## 不變式

1. `AuthorityKind.DELIVERY_CLAIM` ≠ `AuthorityKind.O10_MERGE`
2. 空 diff／scan 擋／sandbox abort／draft 取消／基建失敗 → **不得** `unit_status=succeeded`／`code_ops.delivery.succeeded`
3. `O10MergeDecision.delivery_success_implies_merge` **恒為** `False`
4. 本契約 **不**實作 code_ops→`code_gen` 餵線
5. 本契約 **不**授權合並／部署／改 `MODELGW_WIRE_MODE`

## 驗證

```bash
pytest backend/tests/test_align_g_c2_authority.py -q
```

## 明確不做

- R1／R3／R5／Cap 真碼
- code_ops→code_gen 餵線實作
- Fusion Bus 第三電路
- LangGraph 替換 Scheduler＋Unit Bus
- 路徑 A／G-GATE1／L2／關 L1
