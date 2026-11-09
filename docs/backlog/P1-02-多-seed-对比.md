# P1-02 — 多 seed 对比

| Field | Value |
|---|---|
| **Title** | P1-多 seed 对比 |
| **Priority** | P1 |
| **Status** | open |
| **Source** | FEATURES_AND_TOOLS.md §4 item 12 |

## Scope

- 同一镜头生成 2–4 个候选，并排播放选择
- 不做无限网格

## Acceptance（draft）

- [ ] 一次触发 N 个 seed job（N≤4）
- [ ] UI 并排预览并选定 `selected_*_asset_id`
- [ ] 测试覆盖候选选择写回镜头

## Tools

| 主工具 | 备用 |
|---|---|
| TanStack Query + `<video>` | WebSocket（P1 可选） |
