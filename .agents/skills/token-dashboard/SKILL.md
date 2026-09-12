---
name: token-dashboard
description: 生成 Token 消耗看板（单文件离线 HTML，含 KPI / 日历热力图 / 模型分布 / 工作空间-会话-请求三级下钻）。当用户想查看自己的 token 用量、消耗统计、成本审计时使用，例如「看看我的 token 用量」「token 审计」「生成本月消耗看板」。
---

# Token 消耗看板

为 **Linkin 計費庫**（或本机 WorkBuddy 日志）生成请求级真实 usage 的 Token 消耗看板（单文件自包含 HTML，离线可看）。

## Linkin 环境（推荐）

1. **控制台 UI**：`#/monitor/credits` → 点击「打開 Token 看板」，或 `#/monitor/skills` 技能页同名按钮。
2. **HTTP API**：
   - `GET /billing/token-dashboard` — 直接返回 HTML
   - `POST /billing/token-dashboard/generate` — 返回 stats + HTML
3. **命令行**（仓库根目录）：

   ```bash
   python .agents/skills/token-dashboard/scripts/gen_dashboard.py --source linkin --out token-dashboard.html
   python -m backend.scripts.gen_token_dashboard --user <user_id> --out /tmp/token-dashboard.html
   ```

数据来自 `billing.sqlite3` 的 `pool_usage_events` / `usage_events`（请求级真实 metering，无估算）。无数据时看板显示诚实空状态。

## WorkBuddy 本机日志（可选）

若 `~/.workbuddy/projects/**/*.jsonl` 存在，仍可用上游 WorkBuddy 模式：

```bash
python .agents/skills/token-dashboard/scripts/gen_dashboard.py --out token-dashboard.html
python .agents/skills/token-dashboard/scripts/gen_dashboard.py --projects ~/.workbuddy/projects
```

## 看板能力

- KPI：合计 Token / 日均 / 会话 / 轮次 / 输入输出比 / 缓存命中率 / 预估金额（元）
- 日活热力图、0–24 时模型山脊图、每日模型用量堆叠柱、单次请求大小分布
- 工作空间 → 会话 → 单次请求三级下钻（散点 + 明细表）
- 深浅色主题、1/3/7/30 天窗口 + 自定义日期区间

## 注意

- Linkin 工作空间按 `source` / `event_type` 分组（对话、公司运行时、RAHO 等）；会话对应 `task_id`。
- 预估金额基于脚本内 `PRICE` 表，仅供参考；Linkin 实际扣款以积分计费为准。
- 看板数据来自本机/服务器计费库，不会外发。
