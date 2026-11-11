# P1-04 — 云端适配器 stub

| Field | Value |
|---|---|
| **Title** | P1-云端适配器 stub |
| **Priority** | P1 |
| **Status** | **stub done** in [#167](https://github.com/iiooiioo888/Linkin/pull/167) (M7)；真实调用仍 open |
| **Source** | FEATURES_AND_TOOLS.md §4 item 14 · §1 云端适配器 |

## Acceptance criteria

- [x] Vidu／CloudGPU typed stubs（`cloud_adapters/`）
- [x] `CLOUD_ENABLED`／`LVS_CLOUD_ENABLED` 默认 `false`
- [ ] 真实 API 调用（仅 `data_class=cloud_allowed`）
- [ ] 计费对账（**P2 — 不做**）

## Tests + docs DoD

- [x] health／config 显示 cloud disabled
- [ ] 真实适配器测试（P1 实作时）

## Tools（§2–3）

| 工具 | 备注 |
|---|---|
| HTTP 适配器接口 | MVP 只留 stub |
| **不要** | 自动投流／财务计费 SDK |
