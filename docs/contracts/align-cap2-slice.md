# CONTRACT：Align Cap — Cap-2 垂直切片契約（超出 R1 邊界）

> **狀態：** 契約碼面落地（PR 開立；**`ready_to_merge=false`**；不合並／不部署／不改 WIRE）  
> **契約 ID：** `ALIGN-CAP2`  
> **實作：** `backend/core/align_cap2_slice.py`  
> **測試：** `backend/tests/test_align_cap2_slice.py`  
> **父錨：** Issue #148／#150；`align-residual-talk-ticket-20261101` §6 Cap；align-spec Cap-2；QA24 ownership Cap-2

## 一句精神

| 項 | 值 |
| :--- | :--- |
| **本波** | Cap-2 **切片契約**（provider／fallback／draft 閘／Delivery evidence／QA24） |
| **前置** | **必須** R1 boundary allow（`requires_r1_boundary_allow=True`） |
| **≠** | 真 aider／真 runsc／真開 draft／ModelGW CI 必過／全量 code_ops |

R1＝邊界 only（已落地 #150）；本票＝邊界**之外**的 Cap-2 契約面。談結 ≠ 真 runtime 兌現；「繼續」≠合並授權。

## 不變式

1. R1 `block`／`abort`／`r1_boundary_allow=False` → Cap **必須**擋下；**不得**覆寫放行
2. sandbox abort／scan 擋／空 Delivery evidence → **不開** draft 閘（`draft_gate_allowed=False`）
3. provider 預設 `aider`；不可用且 `fallback_enabled` → `opencode`（`fallback_used=True`）
4. `opens_real_draft_pr` **恒為** `False`（契約閘 ≠ 真開 PR）
5. `modelgw_ci_required` **恒為** `False`；QA24 ownership＝`Cap-2`
6. 本契約 **不**接真 aider／真 Docker／runsc／不改 WIRE／不合並產品

## 評估產出

| `verdict` | 含義 |
| :--- | :--- |
| `allow` | R1 allow＋切片條件全過；可標 `draft_gate_allowed`（仍不真開） |
| `block` | R1 未 allow／scan／evidence／provider 擋下 |
| `abort` | R1 abort 或 sandbox abort；fail-closed |

## 驗證

```bash
pytest backend/tests/test_align_cap2_slice.py -q
```

## 明確不做（本波）

- 真 aider／真碼生成器接線（`does_not_wire_real_aider=True`）
- 真 Docker／runsc 起容器（`does_not_start_real_runsc=True`）
- 真開 draft PR（`does_not_open_real_draft_pr=True`）
- 24 QA 骨架納入 ModelGW CI 必過（`modelgw_ci_required=False`）
- R3／R5／Cap-3／Cap-4／路徑 A／G-GATE1／L2
- 合並／部署／改 `MODELGW_WIRE_MODE`（維持 enforce）
- 改 HMAC／sql／map／llm_config／role_catalog／CI／frontend
- Fusion Bus 第三電路；LangGraph 替換 Scheduler＋Unit Bus
